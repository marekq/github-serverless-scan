from github import Github
import boto3, os, requests, uuid

from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all

patch_all()


githubuser = os.environ["githubuser"]


# lambda handler
@xray_recorder.capture("handler")
def handler(event, context):

    # create results list
    res = []

    # open file for writing
    srcuuid = uuid.uuid4().hex

    # get all repos
    for repo in Github().get_user(githubuser).get_repos():

        # construct output message (repo name, repo branch, scan uuid)
        msg = repo.full_name + "," + repo.default_branch + "," + srcuuid

        # retrieve zip url if not already downloaded
        if msg not in res:

            res.append(msg)
            print("sending " + msg)

    # write to file and print result path
    f = open("/tmp/out.csv", "w")

    for x in res:
        f.write(x+"\n")

    f.close()

    print("results in /tmp/out.csv")

    # print end message and return cfnfiles to step function
    print("returning " + str(len(res)) + " repos")
    return res
