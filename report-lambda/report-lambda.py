import boto3, csv, os
from boto3.dynamodb.conditions import Key, Attr
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all

patch_all()


# create connection to s3 and dynamodb
s3 = boto3.client('s3')
ddb = boto3.resource('dynamodb', region_name = os.environ['AWS_REGION']).Table(os.environ['dynamo_table'])


# get s3 bucket name from env var
s3_bucket = os.environ['s3_bucket']


# lambda handler
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

	# open the file for writing 
	filen = open('/tmp/out.csv', 'w') 
	
	# create the csv writer object 
	csv_writer = csv.writer(filen) 
	
	# set count to 0 
	count = 0
	
	# iterate over results
	for x in res: 
		if count == 0: 
	
			# write the csv header
			csv_writer.writerow(x.keys())
			count += 1
	
		# write the csv record
		csv_writer.writerow(x.values())
	
	# close the file
	filen.close() 

	# warning - public upload of report file
	s3.put_object(Bucket = s3_bucket, Body = open('/tmp/out.csv', 'rb'), Key = scanuuid + '.csv', ContentType = 'text/csv', ACL = 'public-read')

	# return bucket name and file path
	return s3_bucket + "/" + str(scanuuid)
