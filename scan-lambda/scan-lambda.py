from github import Github
import os, uuid

from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all

patch_all()


# lambda handler
@xray_recorder.capture("handler")
def handler(event, context):

    # get github user account, github token and scan id
    githubuser = event["GithubRepo"]
    githubtoken = os.environ["github_token"]
    srcuuid = event["ScanID"]

    # create results list
    res = []

    # get all github repos for the profile
    for repo in Github(githubtoken).get_user(githubuser).get_repos():

        # construct output message (repo id, repo branch (if not master), scan uuid)
        # as the map state can only have 32.768 characters as its input, the github id is used to save on the amount of characters needed per map iteration
        msg = str(repo.id) + "," + srcuuid
        gitsize = int(repo.size)

        # add url if size is more than 0kb but less than 400mb
        if gitsize > 0 and gitsize < 400000:

            res.append(msg)
            print("adding " + msg)

        else:

            print("error - " + repo.full_name + " size " + str(gitsize))

    # print end message and return cfnfiles to step function
    print("returning " + str(len(res)) + " repos")
    return res
