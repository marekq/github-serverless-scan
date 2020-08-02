from github import Github
import os, uuid

from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all

patch_all()


# lambda handler
@xray_recorder.capture("handler")
def handler(event, context):

    print(event)

    # get github user account, github token and scan id
    githubuser = event["GithubRepo"]
    githubtoken = os.environ["github_token"]
    srcuuid = event["ScanID"]

    # create results list
    res = []

    # get all repos
    for repo in Github(githubtoken).get_user(githubuser).get_repos():

        # construct output message (repo name, repo branch, scan uuid)
        msg = repo.full_name + "," + repo.default_branch + "," + srcuuid
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
