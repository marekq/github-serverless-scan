import boto3, os
from boto3.dynamodb.conditions import Key, Attr

s3 = boto3.client('s3')
ddb = boto3.resource('dynamodb', region_name = os.environ['AWS_REGION']).Table(os.environ['dynamo_table'])

s3_bucket = os.environ['s3_bucket']

def handler(event, context):
	res = []

	# retrieve the scan id from step functions input
	scanuuid = event['Data'][0]['ScanID']

	# retrieve the scan data
	queryres = ddb.query(IndexName = 'scanguid', KeyConditionExpression = Key('scan_uuid').eq(scanuuid))

	for x in queryres['Items']:
		res.append(x)

	# paginate through scan data results
	while 'LastEvaluatedKey' in queryres:
		queryres = ddb.query(IndexName = 'scanguid', KeyConditionExpression = Key('scan_uuid').eq(scanuuid), ExclusiveStartKey = queryres['LastEvaluatedKey'])

		for x in queryres['Items']:
			res.append(x)

	# print resolved results
	for x in res:
		print(x)

	# warning - public upload of report file
	s3.put_object(Bucket = s3_bucket, Body = str(res), Key = scanuuid, ContentType = 'application/json', ACL = 'public-read')

	# return bucket name and file path
	return s3_bucket + "/" + str(scanuuid)
