import boto3, re, os, requests, shutil, tempfile, time
from cfnlint import decode, core
from aws_xray_sdk.core import xray_recorder
from zipfile import ZipFile
from aws_xray_sdk.core import patch_all

patch_all()


# initialize the cfn-lint ruleset to be applied
rules = core.get_rules([], [], ['I', 'E', 'W'], [], True, [])

# retrieve aws region where the lambda runs
region = [os.environ['AWS_REGION']]


# load cfnfile keywords from keywords.txt
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


# clone the given git repo to local disk, search for interesting cfnfiles
@xray_recorder.capture("get_repo")
def get_repo(giturl, gitpath, srcuuid, keywords):

    cfnfiles = []

    # create a temporary directory on /tmp to clone the repo
    with tempfile.TemporaryDirectory(dir = "/tmp") as tmppath:

        # clone the git repo 
        print("git http download " + giturl)
        resp = requests.get(giturl)
        zname = tmppath + "/master.zip"

        # write zip file to temp disk
        zfile = open(zname, 'wb')
        zfile.write(resp.content)
        zfile.close()

        zipfiles = []

        # iterate of the zipfile content
        with ZipFile(zname, 'r') as zipObj:
            zlist = zipObj.namelist()

            # extract only .yml, .yaml, .json or .template files from zip file listing
            for zfile in zlist:
                if zfile.endswith('.yml') or zfile.endswith('.yaml') or zfile.endswith('.json') or zfile.endswith('.template'):
                    zipfiles.append(zfile)

            # extract all cfnfiles
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

                    # create counter and validfile boolean
                    count = 0
                    validfile = False

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

                            print("??? getting file " + giturl + " " + gitpath + " " + filename)
                            # store cfnfiles in list
                            cfnfiles.append(filename)
                            validfile = True

                            # scan the cfnfile and check for keywords, add the output count 
                            count += run_lint(cfnfile, gitpath, giturl, filename, disk_used, tmppath, srcuuid)
                            count += check_cfnfile(cfnfile, gitpath, giturl, filename, disk_used, tmppath, srcuuid, keywords)

                        else:

                            print("### skipping file " + filename)

                    # print found messages count if validfile
                    if validfile:

                        print("&&& found " + str(count) + " matches in " + cfnfile)
                     
    # return discovered cfnfiles
    return cfnfiles


# put ddb record
@xray_recorder.capture("put_ddb")
def put_ddb(gitrepo, gitpath, check_id, check_full, check_line_id, check_line_str, filename, disk_used, tmppath, srcuuid):

    # get current time
    timest = int(time.time())

    # get gitprofile and gitrepo
    gitprofile, gitrepo = gitpath.split('/')

    # construct the dynamodb record
    ddbitem = {
        'gitfile' : gitpath + "/" + filename + ":" + check_line_id,
        'gitprofile' : gitprofile,
        'gitrepo' : gitrepo,
        'file_url' : "https://github.com/" + gitpath + "/blob/master/" + filename + "#L" + check_line_id,
        'file_name' : filename,
        'check_line_id' : check_line_id,
        'check_line_full' : check_line_str, 
        'timest': timest,
        'check_text': check_full,
        'check_id': check_id,
        'disk_used': disk_used,
        'scan_uuid': srcuuid
    }

    # put the item into dynamodb
    ddb.put_item(
        TableName = os.environ['dynamo_table'], 
        Item = ddbitem
    )


# check the yaml file for serverless lines
@xray_recorder.capture("check_cfnfile")
def check_cfnfile(cfnfile, gitpath, gitrepo, filename, disk_used, tmppath, srcuuid, keywords):
    linec = 0
    count = 0

    # check the cfnfile for keywords
    for line in open(cfnfile):

        linec += 1

        for keyw in keywords:

            # check if the keyword exists in line
            if re.search(keyw, line):
                kw = keyw.strip()

                # put a dynamodb record for the found keyword
                put_ddb(gitrepo, gitpath, kw, '.', str(linec), line, filename, disk_used, tmppath, srcuuid)

                # increase count by 1
                count += 1

        # if the string contains an s3 code uri, try to retrieve the s3 artifact
        if re.search("CodeUri: s3://", line):
            print("$$$ " + line.strip() + " " + gitrepo + " " + gitpath)

    # return the found count of checks
    return count


# run cfn-lint
@xray_recorder.capture("run_lint")
def run_lint(cfnfile, gitpath, gitrepo, filename, disk_used, tmppath, srcuuid):

    # load the cfnfile
    template, matches = decode.decode(cfnfile, False)

    with open(cfnfile) as f:
        cfncontent = f.readlines()

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
            check_line_id = str(check_full).split(":")[-1]
            check_line_str = str(cfncontent[int(check_line_id)])

            put_ddb(gitrepo, gitpath, check_id, str(check_full), check_line_id, check_line_str, filename, disk_used, tmppath, srcuuid)
            count += 1
            
    except Exception as e:
        print('!!! error reading ' + gitpath + " " + filename + " " + str(e))

    return count


# lambda handler
@xray_recorder.capture("handler")
def handler(event, context):

    # retrieve step function message
    msg = str(event['message'])
    print('*** received step function message ' + msg)

    # load cfnfile keywords    
    keywords = load_keywords()

    reponame, branch, srcuuid = msg.split(',')
    giturl = 'https://github.com/' + reponame + "/archive/" + branch + ".zip"

    # get the git repo
    cfnfiles = get_repo(giturl, reponame, srcuuid, keywords)

    # return matched yaml files
    print(cfnfiles)
    print("^^^ ddbscan uuid " + str(srcuuid))

    return srcuuid
