import boto3, json, math, requests, os, uuid
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all

patch_all()

sqs         = boto3.client("sqs")
sqsqueue    = os.environ["sqsqueue"] 
githubrepo  = os.environ["githubrepo"]
githuburl   = "https://api.github.com/users/" + githubrepo

# send message to sqs
@xray_recorder.capture("send_msg")
def send_msg(x):
    sqs.send_message(QueueUrl = sqsqueue, MessageBody = x)


# get repo count
@xray_recorder.capture("get_repo")
def get_repo():
    x       = requests.get(githuburl)
    z       = json.loads(x.text)
    pages   = math.ceil(z["public_repos"] / 100) + 1
    return pages

@xray_recorder.capture("handler")
def handler(event, context):

    # create results list
    global res
    res     = []
    pages   = get_repo()

    # open file for writing
    f       = open("/tmp/out.csv", "w")
    srcuuid = uuid.uuid4().hex

    # get all repos
    for x in range(int(pages)):

        print("getting page " + str(x))
        x   = requests.get(githuburl + "/repos?page=" + str(x) + "&per_page=100")
        y   = json.loads(x.text)

        # add repo url to results and file
        for a in y:
            curl = str(a["html_url"]) + "/archive/master.zip"
            if curl not in res:
                res.append(curl)
                print("sending " + curl)
                f.write(curl+"\n")

    #close file and print result path
    f.close()
    print("results in /tmp/out.csv")

    for x in res:
        send_msg(x + "," + str(srcuuid))

    print("sent " + str(len(res)) + " messages to sqs queue")
