import boto3, re, os, requests, shutil, tempfile, time
from cfnlint import decode, core
from aws_xray_sdk.core import xray_recorder
from zipfile import ZipFile
from github import Github
from aws_xray_sdk.core import patch_all

patch_all()


# initialize the cfn-lint ruleset to be applied
rules = core.get_rules([], [], ['I', 'E', 'W'], [], True, [])


# retrieve the dynamodb tables from env vars
dynamo_table_metadata = os.environ['dynamo_table_metadata']
dynamo_table_scan = os.environ['dynamo_table_scan']
region = str(os.environ['AWS_REGION'])

# connect to dynamodb
ddb_scan = boto3.resource('dynamodb', region_name = region).Table(dynamo_table_scan)
ddb_meta = boto3.resource('dynamodb', region_name = region).Table(dynamo_table_metadata)


# load cfnfile keywords from keywords.txt
@xray_recorder.capture("load_keywords")
def load_keywords():
    kw 	= []
    f 	= 'keywords.txt'

	# open the feeds file and read line by line
    for line in open(f):
        kw.append(line)

    return kw


# clone the given git repo to local disk, search for interesting cfnfiles
@xray_recorder.capture("get_repo")
def get_repo(repoid, scan_uuid, keywords, githubtoken):

    # create check count
    count = 0
    
    # get the github repo details
    githubres = Github(githubtoken).get_repo(int(repoid))

    gitpath = githubres.full_name
    giturl = 'https://github.com/' + gitpath + "/archive/" + githubres.default_branch + ".zip"
    gitsize = int(githubres.size)

    # add url if size is more than 0kb but less than 400mb
    if gitsize > 0 and gitsize < 400000:

        # create a temporary directory on /tmp to clone the repo
        with tempfile.TemporaryDirectory(dir = "/tmp") as tmppath:

            # clone the git repo 
            print("git http download " + giturl)
            resp = requests.get(giturl)

            # write zip file to temp disk
            zname = tmppath + "/main.zip"
            zfile = open(zname, 'wb')
            zfile.write(resp.content)
            zfile.close()

            # iterate of the zipfile content
            with ZipFile(zname, 'r') as zipObj:
                zipfiles = []
                zlist = zipObj.namelist()

                # extract only .yml, .yaml, .json or .template files from zip file listing
                for filename in zlist:
                    if filename.endswith('.yml') or filename.endswith('.yaml') or filename.endswith('.json') or filename.endswith('.template'):
                        zipfiles.append(filename)
                        zipObj.extract(path = tmppath, member = filename)

                        # get the location of the unzipped file
                        tmpfile = tmppath + '/' + filename

                        # read the template, replace invalid chars
                        f = open(tmpfile, errors = 'replace').read()

                        # detect whether the file is likely a CloudFormation file based on the "AWSTemplateFormatVersion" field. 
                        pat = re.compile("AWSTemplateFormatVersion", re.IGNORECASE)

                        # if cloudformation pattern is found in file
                        if pat.search(f) != None:

                            print("??? scanning file " + giturl + " " + gitpath + " " + filename)
                            
                            # scan the cfnfile and check for keywords, add the output count 
                            count += run_lint(tmpfile, gitpath, giturl, filename, tmppath, scan_uuid, githubres)
                            count += check_cfnfile(tmpfile, gitpath, giturl, filename, tmppath, scan_uuid, keywords, githubres)

                        else:

                            print("### skipping file " + filename)

    else:
        print("--- error - " + gitpath + " size " + str(gitsize))

    # return count and gitpath
    return int(count), gitpath


# put dynamodb metadata record
@xray_recorder.capture("put_ddb_metadata")
def put_ddb_metadata(scan_uuid, gitpath, count_finding):

    # get current time
    timest = int(time.time())

    # get gitprofile and gitrepo
    gituser, gitrepo = gitpath.split('/')

    # construct the dynamodb record
    ddbitem = {
        'gituser' : gituser,
        'gitrepo' : gitrepo,
        'timest': int(timest),
        'scan_uuid': scan_uuid,
        'count_finding': int(count_finding)
    }

    # put the item into dynamodb
    ddb_meta.put_item(
        TableName = dynamo_table_metadata, 
        Item = ddbitem
    )

# put dynamodb scan result record
@xray_recorder.capture("put_ddb_result")
def put_ddb_result(gitrepo, gitpath, check_id, check_full, check_line_id, check_type, filename, tmppath, scan_uuid, githubres):

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
        'check_line_id' : int(check_line_id),
        'timest': timest,
        'check_text': check_full.strip(),
        'check_id': check_id,
        'check_type': check_type,
        'scan_uuid': scan_uuid,
        'language': githubres.language,
        'repo_created_at': str(githubres.created_at),
        'repo_updated_at': str(githubres.updated_at),
        'repo_stars': int(githubres.stargazers_count),
        'repo_size': int(githubres.size),
        'repo_desc': githubres.description,
        'repo_forks': int(githubres.forks)
    }

    # put the item into dynamodb
    ddb_scan.put_item(
        TableName = dynamo_table_scan, 
        Item = ddbitem
    )


# check the yaml file for serverless lines
@xray_recorder.capture("check_cfnfile")
def check_cfnfile(cfnfile, gitpath, gitrepo, filename, tmppath, scan_uuid, keywords, githubres):
    check_line_id = 0
    check_count = 0

    # check the cfnfile line by line for keywords
    for line in open(cfnfile):

        check_line_id += 1

        for keyword in keywords:

            # check if the keyword exists in line
            if re.search(keyword, line):
                found_keyword = keyword.strip()
                check_type = 'check_keyword'

                # put a dynamodb record for the found keyword
                put_ddb_result(gitrepo, gitpath, found_keyword, found_keyword, str(check_line_id), check_type, filename, tmppath, scan_uuid, githubres)

                # increase count by 1
                check_count += 1

        # if the string contains an s3 code uri, try to retrieve the s3 artifact
        if re.search("CodeUri: s3://", line):
            print("$$$ " + line.strip() + " " + gitrepo + " " + gitpath)

    # return the found count of checks
    return check_count


# run cfn-lint
@xray_recorder.capture("run_lint")
def run_lint(cfnfile, gitpath, gitrepo, filename, tmppath, scan_uuid, githubres):

    # load the cfnfile
    template, matches = decode.decode(cfnfile, False)

    # set counter to 0
    count = 0

    # process all the rules 
    try:
        matches = core.run_checks(
            cfnfile,
            template,
            rules,
            [region]
        )
    
        check_type = 'cfn_lint'

        for check_full in matches:
            check_id = str(check_full)[1:6]
            check_line_id = str(check_full).split(":")[-1]
            count += 1

            put_ddb_result(gitrepo, gitpath, check_id, str(check_full), check_line_id, check_type, filename, tmppath, scan_uuid, githubres)

    except Exception as e:
        print('!!! error reading ' + gitpath + " " + filename + " " + str(e))

    return count


# lambda handler
@xray_recorder.capture("handler")
def handler(event, context):

    # retrieve step function message
    msg = str(event['message'])
    print('*** received step function message ' + msg)

    # retrieve the github token from env variable
    githubtoken = os.environ["github_token"]

    # load cfnfile keywords    
    keywords = load_keywords()

    repoid, scan_uuid = msg.split(',')

    # get the git repo, return the amount of detections for the repo
    count_finding, gitpath = get_repo(repoid, scan_uuid, keywords, githubtoken)

    # return dynamodb scan id and write metadata record
    print("^^^ ddbscan uuid " + str(scan_uuid))
    put_ddb_metadata(scan_uuid, gitpath, count_finding)

    return {str(gitpath): str(count_finding)}
