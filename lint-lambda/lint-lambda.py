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

    cfnfiles = []
    keywords = load_keywords()

    # create a temporary directory on /tmp to clone the repo
    with tempfile.TemporaryDirectory(dir = "/tmp") as tmppath:

        # clone the git repo 
        print("git http download " + giturl)
        resp = requests.get(giturl)
        zname = tmppath + "/master.zip"

        zfile = open(zname, 'wb')
        zfile.write(resp.content)
        zfile.close()

        zipfiles = []

        # extract only .yml, .yaml, .json or .template files from zip
        with ZipFile(zname, 'r') as zipObj:
            zlist = zipObj.namelist()

            for zfile in zlist:
                if zfile.endswith('.yml') or zfile.endswith('.yaml') or zfile.endswith('.json') or zfile.endswith('.template'):
                    zipfiles.append(zfile)

            zipObj.extractall(path = tmppath, members = zipfiles)

        # check local /tmp disk used
        total, used, free = shutil.disk_usage(tmppath)
        disk_used = str(round(used / (1024.0 ** 2), 2))
        print(gitpath + " disk used - " + disk_used + " MB")

        # delete the zip file from /tmp
        os.remove(zname)

        xray_recorder.current_subsegment().put_annotation('disk_usage', disk_used)
        xray_recorder.current_subsegment().put_annotation('gitrepo', giturl)

        # check content of cloudformation files
        for root, dirs, files in os.walk(tmppath, topdown = True):
            for dirn in dirs:
                for filen in files:
                    if re.search('.yml', filen) or re.search('.yaml', filen) or re.search('.json', filen) or re.search('.template'):

                        # create variable with file name
                        fname = os.path.join(root, filen)
                        lname = fname.replace(tmppath, '')
                        gname = giturl + lname

                        f = open(fname).read()

                        # Detect whether the file is likely a CloudFormation file based on the "Resources" field. 
                        # The "AWSTemplateFormatVersion" field would be a better candidate, but only the "Resources" field is formally required; https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/template-anatomy.html
                        pat = re.compile("Resources:", re.IGNORECASE)

                        if pat.search(f) != None:
                            
                            # store yaml files in list
                            cfnfiles.append(lname)

                            # scan the yaml file and check for keywords
                            run_lint(fname, gitpath, gname, giturl, lname, disk_used, tmppath, srcuuid)
                            check_yaml(fname, gitpath, gname, giturl, lname, disk_used, tmppath, srcuuid, keywords)

                        else:
                            print("skipping file " + lname)
                     
    return cfnfiles


# put ddb record
@xray_recorder.capture("put_ddb")
def put_ddb(gitrepo, fname, check_id, check_full, check_line, lname, disk_used, tmppath, srcuuid):
    timest 		= int(time.time())

    ddbitem     = {
        'gitrepo' : gitrepo + "/" + lname + ":" + check_line,
        'file_url' : gitrepo[:-18] + "blob/master" + lname + "#L" + check_line,
        'file_name' : fname,
        'check_line' : check_line,
        'timest': timest,
        'check_full': check_full,
        'check_id': check_id,
        'disk_used': disk_used,
        'scan_uuid': srcuuid
    }

    ddb.put_item(
        TableName = os.environ['dynamo_table'], 
        Item = ddbitem
    )


# check the yaml file for serverless lines
@xray_recorder.capture("check_yaml")
def check_yaml(fname, gitrepo, gname, giturl, lname, disk_used, tmppath, srcuuid, keywords):
    linec = 0

    for line in open(fname):
        linec += 1

        for keyw in keywords:
            if re.search(keyw, line):
                kw = keyw.strip()
                put_ddb(gitrepo, fname, kw, '.', str(linec), lname, disk_used, tmppath, srcuuid)


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
            check_id = str(check_full)[1:6]
            check_line = str(check_full).split(":")[-1]

            put_ddb(gitrepo, name, check_id, str(check_full), check_line, lname, disk_used, tmppath, srcuuid)
            count += 1
            
    except Exception as e:
        print('error reading ' + gitpath + " " + name)
        print(e)

    print("found " + str(count) + " checks in " + gitpath[:-19] + lname)


# lambda handler
@xray_recorder.capture("handler")
def handler(event, context):

    sqsmsg = event['Records'][0]['body']
    print('received sqsmsg '+(str(sqsmsg))
    
    reponame, branch, srcuuid = sqsmsg.split(',')
    giturl = 'https://github.com/' + reponame + "/archive/" + branch + ".zip"

    # get the git repo
    cfnfiles = get_repo(giturl, reponame, srcuuid)

    # return matched yaml files
    print(cfnfiles)
    print("ddbscan uuid " + str(srcuuid))

    return srcuuid
