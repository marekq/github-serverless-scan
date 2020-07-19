import boto3, re, os, requests, shutil, tempfile, time
from cfnlint import decode, core
from aws_xray_sdk.core import xray_recorder
from zipfile import ZipFile
from aws_xray_sdk.core import patch_all
patch_all()


# initialize the cfn-lint ruleset to be applied 
rules = core.get_rules([], [], ['I', 'E', 'W'], [], True, [])


# load yaml keywords from keywords.txt
@xray_recorder.capture("load_keywords")
def load_keywords():
    kw 	= []
    f 	= 'keywords.txt'

	# open the feeds file and read line by line
    for line in open(f):
        kw.append(line)

    return kw


# connect to dynamodb
ddb = boto3.resource('dynamodb', region_name = os.environ['AWS_REGION']).Table(os.environ['dynamo_table'])


# clone the given git repo to local disk, search for interesting yaml files
@xray_recorder.capture("get_repo")
def get_repo(giturl, gitpath, srcuuid):

    yamlfiles   = []
    keywords    = load_keywords()

    # create a temporary directory on /tmp to clone the repo
    with tempfile.TemporaryDirectory(dir = "/tmp") as tmppath:

        # clone the git repo 
        print("git http download " + giturl[:-19])
        resp    = requests.get(giturl)
        zname   = tmppath + "/master.zip"

        zfile   = open(zname, 'wb')
        zfile.write(resp.content)
        zfile.close()

        with ZipFile(zname, 'r') as zipObj:
            zipObj.extractall(path = tmppath)

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

                            # scan the yaml file and check for keywords
                            run_lint(fname, gitpath, gname, giturl, lname, disk_used, tmppath, srcuuid)
                            check_yaml(fname, keywords)

                        else:
                            print("skipping file " + lname)
                     
    return yamlfiles


# put ddb record
@xray_recorder.capture("put_ddb")
def put_ddb(gitrepo, fname, check_id, check_full, check_line, lname, disk_used, tmppath, srcuuid):
    timest 		= int(time.time())

    ddbitem     = {
        'gitrepo'	    : gitrepo + "/" + lname + ":" + check_line,
        'file_url'      : gitrepo[:-18] + "/blob/master" + lname + "#L" + check_line,
        'file_name'     : fname,
        'check_line'    : check_line,
        'timest'        : timest,
        'check_full'    : check_full,
        'check_id'	    : check_id,
        'disk_used'     : disk_used,
        'scan_uuid'     : srcuuid
    }

    ddb.put_item(
        TableName = os.environ['dynamo_table'], 
        Item = ddbitem
    )


# check the yaml file for serverless lines
@xray_recorder.capture("check_yaml")
def check_yaml(yamlfile, keywords):
    for line in open(yamlfile):
        for keyw in keywords:
            if re.search(keyw, line):
                print('@@@', keyw.strip(), yamlfile.strip())


# run cfn-lint
@xray_recorder.capture("run_lint")
def run_lint(yamlfile, gitpath, name, gitrepo, lname, disk_used, tmppath, srcuuid):
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

            put_ddb(gitrepo, name, check_id, str(check_full), check_line, lname, disk_used, tmppath, srcuuid)
            count += 1
            
    except Exception as e:
        print('error reading ' + gitpath + " " + name)
        print(e)

    print("found " + str(count) + " checks in " + gitpath[:-19] + lname)


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
    print("ddbscan uuid " + str(srcuuid))

    return srcuuid
