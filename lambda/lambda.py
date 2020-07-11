import re, os, shutil, subprocess, tempfile
from cfnlint import decode, core


# initialize the cfn-lint ruleset to be applied 
rules = core.get_rules([], [], ['I', 'E', 'W'], [], True, [])


# clone the given git repo to local disk, search for interesting yaml files
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
                    fname = os.path.join(root, name)

                    # store yaml files in list
                    yamlfiles.append(fname)

                    # scan the yaml file
                    run_lint(fname, gitpath, name)
                    
        total, used, free = shutil.disk_usage(tmppath)
        print(gitpath + " disk used - %d MB" % (used / (1024.0 ** 2)))

    return yamlfiles

# run cfn-lint
def run_lint(yamlfile, gitpath, name):
    template, matches = decode.decode(yamlfile, False)
    region = [os.environ['AWS_REGION']]

    # process all the rules 
    try:
        matches = core.run_checks(
            yamlfile,
            template,
            rules,
            region
        )
    
        for x in matches:
            print(gitpath, name, x)

    except:
        print('error reading ' + gitpath + " " + name)


# lambda handler
def handler(event, context):

    eventurl   = event['Records'][0]['body']
    gitbase    = eventurl[:19]
    gitpath    = eventurl[19:]

    # get the git repo
    yamlfiles  = get_repo(eventurl, gitpath)

    # return matched yaml files
    print(yamlfiles)
    return yamlfiles
