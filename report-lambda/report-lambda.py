import boto3

ddb = boto3.resource('dynamodb', region_name = os.environ['AWS_REGION']).Table(os.environ['dynamo_table'])

def handler(event, context):
    print(event)

    scanuuid = event['Data'][0]['ScanID']
    print(scanuuid)

    queryres = ddb.query(IndexName = 'scanguid', KeyConditionExpression = Key('scan_uuid').eq(scanuuid))
    print(queryres)
    return scanuuid
