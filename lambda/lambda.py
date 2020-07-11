import re, os, shutil, subprocess, tempfile
from cfnlint import decode, core

yamlfiles  = []
keywords   = []

# initialize the cfn-lint ruleset to be applied 
rules = core.get_rules([], [], [], [], False, [])

# load yaml keywords from keywords.txt
def load_keywords():
    r 	= {}
    f 	= 'keywords.txt'
    c   = 0

	# open the feeds file and read line by line
    for line in open(f):
        keywords.append(line)

load_keywords()


# clone the given git repo to local disk, search for interesting yaml files
def get_repo(giturl):
    
    # create a temporary directory on /tmp to clone the repo
    with tempfile.TemporaryDirectory() as tmppath:

        # clone the git repo 
        gitc = subprocess.Popen("git clone " + giturl + " " + tmppath, shell = True)

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
                    check_yaml(fname, giturl)

                    run_lint(fname)


# run cfn-lint
def run_lint(yamlfile):
    template, matches = decode.decode(yamlfile, False)

    # process all the rules 
    matches = core.run_checks(
        yamlfile,
        template,
        rules,
        ["eu-west-1"]
    )

    print(yamlfile)
    for x in matches:
        print(x)


# check the yaml file for serverless lines
def check_yaml(yamlfile, giturl):
    for line in open(yamlfile):
        for keyw in keywords:
            if re.search(keyw, line):
                print(keyw.strip(), yamlfile.strip())


# lambda handler
def handler(event, context):
    eventurl   = event['Records'][0]['body']

    gitbase    = eventurl[:19]
    gitpath    = eventurl[19:]

    # get the git repo
    get_repo(eventurl)

    # print matched yaml files
    print(yamlfiles)

    return "completed"
