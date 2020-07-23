from github import Github
import boto3, os, requests, uuid

from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all

patch_all()


sqs = boto3.client("sqs")
sqsqueue = os.environ["sqsqueue"] 
githubuser = os.environ["githubuser"]


# send message to sqs
@xray_recorder.capture("send_msg")
def send_msg(x):
    sqs.send_message(QueueUrl = sqsqueue, MessageBody = x)


# lambda handler
@xray_recorder.capture("handler")
def handler(event, context):

    # create results list
    res = []

    # open file for writing
    srcuuid = uuid.uuid4().hex

    # get all repos
    for repo in Github().get_user(githubuser).get_repos():

        # construct sqs message (repo name, repo branch, scan uuid)
        msg = repo.full_name + "," + repo.default_branch + "," + srcuuid

        # retrieve zip url if not already downloaded
        if msg not in res:

            res.append(msg)
            print("sending " + msg)

            # send the github url's to sqs
            send_msg(msg)

    # write to file and print result path
    f = open("/tmp/out.csv", "w")

    for x in res:
        f.write(x+"\n")

    f.close()

    print("results in /tmp/out.csv")

    # print end message and return scan uuid
    print("sent " + str(len(res)) + " messages to sqs queue")
    return srcuuid
