import botocore, boto3, re, os, requests, shutil, subprocess, tempfile, time
from cfnlint import decode, core
from aws_xray_sdk.core import xray_recorder
from zipfile import ZipFile
from aws_xray_sdk.core import patch_all
patch_all()


# initialize the cfn-lint ruleset to be applied 
rules = core.get_rules([], [], ['I', 'E', 'W'], [], True, [])


# connect to dynamodb
ddb = boto3.resource('dynamodb', region_name = os.environ['AWS_REGION'], config = botocore.client.Config(max_pool_connections = 25)).Table(os.environ['dynamo_table'])


# clone the given git repo to local disk, search for interesting yaml files
@xray_recorder.capture("get_repo")
def get_repo(giturl, gitpath, srcuuid):

    yamlfiles   = []

    # create a temporary directory on /tmp to clone the repo
    with tempfile.TemporaryDirectory() as tmppath:

        # clone the git repo 
        print("git download " + giturl)
        resp    = requests.get(giturl)
        zname   = "master.zip"
        zfile   = open(tmppath + "/" + zname, 'wb')
        zfile.write(resp.content)
        zfile.close()

        with ZipFile(zname, 'r') as zipObj:
            zipObj.extractall()

        total, used, free = shutil.disk_usage(tmppath)
        disk_used = str(round(used / (1024.0 ** 2), 2))
        print(gitpath + " disk used - " + disk_used + " MB")

        xray_recorder.current_subsegment().put_annotation('disk_usage', disk_used)
        xray_recorder.current_subsegment().put_annotation('gitrepo', giturl)

        # check content of yaml files
        for root, dirs, files in os.walk(tmppath, topdown = True):
            for dirn in dirs:
                for filen in files:
                    if re.search('.yml', filen) or re.search('.yaml', filen):

                        # create variable with file name
                        fname   = os.path.join(root, filen)
                        lname   = fname.replace(tmppath, '')
                        gname   = giturl + lname

                        f       = open(fname).read()
                        pat     = re.compile("AWSTemplateFormatVersion", re.IGNORECASE)

                        if pat.search(f) != None:
                            
                            # store yaml files in list
                            yamlfiles.append(lname)

                            # scan the yaml file
                            run_lint(fname, gitpath, gname, giturl, disk_used, tmppath, srcuuid)

                        else:
                            print("skipping file " + gitpath + " " + lname)
                     
    return yamlfiles


# put ddb record
@xray_recorder.capture("put_ddb")
def put_ddb(gitrepo, fname, check_id, check_full, check_line, disk_used, tmppath, srcuuid):
    timest 		= int(time.time())

    ddb.put_item(TableName = os.environ['dynamo_table'], 
        Item = {
            'gitrepo'	    : gitrepo + "/" + fname.replace(tmppath, '') + ":" + check_line,
            'file_url'      : gitrepo + "/blob/master" + fname.replace(tmppath, '') + "#L" + check_line,
            'file_name'     : fname,
            'check_line'    : check_line,
            'timest'        : timest,
            'check_full'    : check_full,
            'check_id'	    : check_id,
            'disk_used'     : disk_used,
            'src_uuid'      : srcuuid
        }
    )

    print("wrote ddb record for " + gitrepo + "/" + fname + ":" + check_line + " " + check_id)


# run cfn-lint
@xray_recorder.capture("run_lint")
def run_lint(yamlfile, gitpath, name, gitrepo, disk_used, tmppath, srcuuid):
    template, matches = decode.decode(yamlfile, False)
    region = [os.environ['AWS_REGION']]
    count = 0

    # process all the rules 
    try:
        matches = core.run_checks(
            yamlfile,
            template,
            rules,
            region
        )
    
        for check_full in matches:
            check_id    = str(check_full)[1:6]
            check_line  = str(check_full).split(":")[-1]

            put_ddb(gitrepo, name, check_id, str(check_full), check_line, disk_used, tmppath, srcuuid)
            count += 1
            
    except Exception as e:
        print('error reading ' + gitpath + " " + name)
        print(e)

    print("found " + str(count) + " checks in " + gitpath + " " + name)


# lambda handler
@xray_recorder.capture("handler")
def handler(event, context):

    sqsmsg              = event['Records'][0]['body']
    eventurl, srcuuid   = sqsmsg.split(',')
    gitbase             = eventurl[:19]
    gitpath             = eventurl[19:]

    # get the git repo
    yamlfiles           = get_repo(eventurl, gitpath, srcuuid)

    # return matched yaml files
    print(yamlfiles)
    return yamlfiles
