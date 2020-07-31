from github import Github
import os, uuid

from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all

patch_all()


# lambda handler
@xray_recorder.capture("handler")
def handler(event, context):

    print(event)

    # get github user account to scan
    githubuser = event["GithubRepo"]
    srcuuid = event["ScanID"]

    # create results list
    res = []

    # get all repos
    for repo in Github().get_user(githubuser).get_repos():

        # construct output message (repo name, repo branch, scan uuid)
        msg = repo.full_name + "," + repo.default_branch + "," + srcuuid

        # add url if not already downloaded
        if msg not in res:

            res.append(msg)
            print("adding " + msg)

    # print end message and return cfnfiles to step function
    print("returning " + str(len(res)) + " repos")
    return res
