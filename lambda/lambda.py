import re, os, shutil, subprocess

yamlfiles  = []
keywords   = []


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
def get_repo(giturl, tmppath):

    # create the git output dir or clean the /tmp dir
    if os.path.isdir(tmppath):
        shutil.rmtree(tmppath)
    
    os.makedirs(tmppath)

    # clone the git repo 
    gitc = subprocess.Popen("git clone " + giturl + " " + tmppath, shell = True)

    # await for git command to complete
    gitc.communicate()

    # find yaml files
    files = os.listdir(tmppath)

    # check content of yaml files
    for root, dirs, files in os.walk(tmppath, topdown=False):
        for name in files:
            if re.search('.yml', name) or re.search('.yaml', name):

                # create variable with file name
                fname = os.path.join(root, name)

                # store yaml files in list
                yamlfiles.append(fname)

                # scan the yaml file
                check_yaml(fname, giturl)




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

    tmppath    = "/tmp/" + gitpath

    # get the git repo
    get_repo(eventurl, tmppath)

    # print matched yaml files
    print(yamlfiles)

    return "completed"
