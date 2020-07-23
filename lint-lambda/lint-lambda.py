import boto3, re, os, pprint, requests, shutil, tempfile, time
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

                    count = 0

                    if re.search('.yml', filen) or re.search('.yaml', filen) or re.search('.json', filen) or re.search('.template', filen):

                        # create variable with file name
                        cfnfile = os.path.join(root, filen)
                        filename = '/'.join(cfnfile.split('/')[4:])

                        f = open(cfnfile).read()

                        # Detect whether the file is likely a CloudFormation file based on the "Resources" field. 
                        # The "AWSTemplateFormatVersion" field would be a better candidate, but only the "Resources" field is formally required; https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/template-anatomy.html
                        pat = re.compile("Resources:", re.IGNORECASE)

                        # if pattern is found
                        if pat.search(f) != None:
                            
                            # store yaml files in list
                            cfnfiles.append(filename)

                            # scan the yaml file and check for keywords
                            count += run_lint(cfnfile, gitpath, giturl, filename, disk_used, tmppath, srcuuid)
                            count += check_yaml(cfnfile, gitpath, giturl, filename, disk_used, tmppath, srcuuid, keywords)

                        else:
                            # print error message
                            print("skipping file " + filename)

                    # print found messages count if more than 0
                    if count != 0:
                        print("found " + str(count) + " matches in " + cfnfile)
                     
    return cfnfiles


# put ddb record
@xray_recorder.capture("put_ddb")
def put_ddb(gitrepo, gitpath, check_id, check_full, check_line, filename, disk_used, tmppath, srcuuid):

    # get current time
    timest = int(time.time())

    # get gitprofile and gitrepo
    gitprofile, gitrepo = gitpath.split('/')

    # construct the dynamodb record
    ddbitem = {
        'gitfile' : gitpath + "/" + filename + ":" + check_line,
        'gitprofile' : gitprofile,
        'gitrepo' : gitrepo,
        'file_url' : "https://github.com/" + gitpath + "/blob/master/" + filename + "#L" + check_line,
        'file_name' : filename,
        'check_line' : check_line,
        'timest': timest,
        'check_full': check_full,
        'check_id': check_id,
        'disk_used': disk_used,
        'scan_uuid': srcuuid
    }

    # pretty print results
    pp = pprint.PrettyPrinter(indent = 2)
    pp.pprint(ddbitem)

    # put the item into dynamodb
    ddb.put_item(
        TableName = os.environ['dynamo_table'], 
        Item = ddbitem
    )


# check the yaml file for serverless lines
@xray_recorder.capture("check_yaml")
def check_yaml(cfnfile, gitpath, gitrepo, lname, disk_used, tmppath, srcuuid, keywords):
    linec = 0
    count = 0

    # check
    for line in open(cfnfile):
        linec += 1

        for keyw in keywords:
            if re.search(keyw, line):
                kw = keyw.strip()
                put_ddb(gitrepo, gitpath, kw, '.', str(linec), lname, disk_used, tmppath, srcuuid)
                count += 1

    return count


# run cfn-lint
@xray_recorder.capture("run_lint")
def run_lint(cfnfile, gitpath, gitrepo, filename, disk_used, tmppath, srcuuid):
    template, matches = decode.decode(cfnfile, False)
    region = [os.environ['AWS_REGION']]
    count = 0

    # process all the rules 
    try:
        matches = core.run_checks(
            cfnfile,
            template,
            rules,
            region
        )
    
        for check_full in matches:
            check_id = str(check_full)[1:6]
            check_line = str(check_full).split(":")[-1]

            put_ddb(gitrepo, gitpath, check_id, str(check_full), check_line, filename, disk_used, tmppath, srcuuid)
            count += 1
            
    except Exception as e:
        print('error reading ' + gitpath + " " + filename)
        print(e)

    return count


# lambda handler
@xray_recorder.capture("handler")
def handler(event, context):

    sqsmsg = str(event['Records'][0]['body'])
    print('received sqsmsg ' + sqsmsg)

    reponame, branch, srcuuid = sqsmsg.split(',')
    giturl = 'https://github.com/' + reponame + "/archive/" + branch + ".zip"

    # get the git repo
    cfnfiles = get_repo(giturl, reponame, srcuuid)

    # return matched yaml files
    print(cfnfiles)
    print("ddbscan uuid " + str(srcuuid))

    return srcuuid
