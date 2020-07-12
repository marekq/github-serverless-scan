import botocore, boto3, re, os, shutil, subprocess, tempfile, time
from cfnlint import decode, core
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all

patch_all()

# initialize the cfn-lint ruleset to be applied 
rules = core.get_rules([], [], ['I', 'E', 'W'], [], True, [])

# connect to dynamodb
ddb = boto3.resource('dynamodb', region_name = os.environ['AWS_REGION'], config = botocore.client.Config(max_pool_connections = 25)).Table(os.environ['dynamo_table'])

# clone the given git repo to local disk, search for interesting yaml files
@xray_recorder.capture("get_repo")
def get_repo(giturl, gitpath):

    yamlfiles   = []

    # create a temporary directory on /tmp to clone the repo
    with tempfile.TemporaryDirectory() as tmppath:

        # clone the git repo 
        print("git clone " + giturl)
        gitc = subprocess.Popen("git clone " + giturl + " " + tmppath, shell = True, stdout = subprocess.PIPE)

        # await for git command to complete
        gitc.communicate()

        total, used, free = shutil.disk_usage(tmppath)
        disk_free = str(used / (1024.0 ** 2))
        print(gitpath + " disk used - " + disk_free + " MB")
        xray_recorder.current_subsegment().put_annotation('disk_usage', disk_free)
        xray_recorder.current_subsegment().put_annotation('gitrepo', giturl)

        # find yaml files
        files = os.listdir(tmppath)

        # check content of yaml files
        for root, dirs, files in os.walk(tmppath, topdown = True):
            for name in files:
                if re.search('.yml', name) or re.search('.yaml', name):

                    # create variable with file name
                    fname   = os.path.join(root, name)
                    f       = open(fname).read()
                    pat     = re.compile("AWSTemplateFormatVersion", re.IGNORECASE)

                    if pat.search(f) != None:
                        # store yaml files in list
                        yamlfiles.append(fname)

                        # scan the yaml file
                        run_lint(fname, gitpath, name, giturl, disk_free)

                    else:
                        print("skipping file " + gitpath + " " + fname)
                     
    return yamlfiles


# put ddb record
@xray_recorder.capture("put_ddb")
def put_ddb(gitrepo, fname, check_id, check_full, check_line, disk_free):
    timest 		= int(time.time())

ddb.put_item(TableName = os.environ['dynamo_table'], 
    Item = {
        'gitrepo'	    : gitrepo + "/" + fname + ":" + check_line,
        'fname'         : fname,
        'check_line'    : check_line,
        'timest'        : timest,
        'check_full'    : check_full,
        'check_id'	    : check_id,
        'disk_free'     : disk_free
    }
)

    print("wrote ddb record for " + gitrepo + " " + check_id)

# run cfn-lint
@xray_recorder.capture("run_lint")
def run_lint(yamlfile, gitpath, name, gitrepo, disk_free):
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

            put_ddb(gitrepo, name, check_id, str(check_full), check_line, disk_free)
            count += 1
            
            print(gitrepo + "/" + name + ":" + check_line, name, str(check_full))

    except Exception as e:
        print('error reading ' + gitpath + " " + name)
        print(e)

    print("found " + str(count) + " checks in " + gitpath + " " + name)

# lambda handler
@xray_recorder.capture("handler")
def handler(event, context):

    eventurl   = event['Records'][0]['body']
    gitbase    = eventurl[:19]
    gitpath    = eventurl[19:]

    # get the git repo
    yamlfiles  = get_repo(eventurl, gitpath)

    # return matched yaml files
    print(yamlfiles)
    return yamlfiles
