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
        gitc = subprocess.Popen("git clone " + giturl + " " + tmppath + " --depth 2", shell = True, stdout = subprocess.PIPE)

        # await for git command to complete
        gitc.communicate()

        # find yaml files
        files = os.listdir(tmppath)

        # check content of yaml files
        for root, dirs, files in os.walk(tmppath, topdown = False):
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
                        run_lint(fname, gitpath, name, giturl)

                    else:
                        print("skipping file " + gitpath + " " + fname)
                    
        total, used, free = shutil.disk_usage(tmppath)
        df = str(used / (1024.0 ** 2))
        print(gitpath + " disk used - " + df + " MB")
        xray_recorder.current_subsegment().put_annotation('disk_usage', df)
        xray_recorder.current_subsegment().put_annotation('gitrepo', giturl)
        
    return yamlfiles


# put ddb record
@xray_recorder.capture("put_ddb")
def put_ddb(gitrepo, check_id, check_full):
    timest 		= int(time.time())

    ddb.put_item(TableName = os.environ['dynamo_table'], 
		Item = {
			'gitrepo'	    : gitrepo,
            'timest'        : timest,
			'check_full'    : check_full,
			'check_id'	    : check_id
		})

    print("wrote ddb record " + gitrepo + " " + file)

# run cfn-lint
@xray_recorder.capture("run_lint")
def run_lint(yamlfile, gitpath, name, gitrepo):
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

            gitfull = gitrepo + "/" + name
            put_ddb(gitfull, check_id, check_full)
            count += 1
            
            print(gitpath, name, str(check_full))

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
