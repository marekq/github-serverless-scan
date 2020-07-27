import boto3, os

ddb = boto3.resource('dynamodb', region_name = os.environ['AWS_REGION']).Table(os.environ['dynamo_table'])

def handler(event, context):
    print(event)
    print(context)

    x = ddb.scan()
    print(x)
