import boto3, csv, os, re
from boto3.dynamodb.conditions import Key, Attr
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all

patch_all()


# create connection to s3, dynamodb and ses
ddb_scan = boto3.resource('dynamodb', region_name = os.environ['AWS_REGION']).Table(os.environ['dynamo_scan_table'])
ddb_meta = boto3.resource('dynamodb', region_name = os.environ['AWS_REGION']).Table(os.environ['dynamo_meta_table'])
ses = boto3.client('ses')
s3 = boto3.client('s3')


# get s3 bucket name and ses destination email from env var
s3_bucket = os.environ['s3_bucket']
dest_email = os.environ['dest_email']
from_email = os.environ['from_email']


# set the s3 signed url expiry to one day
s3_link_expiry = 86400


# optional - send email to receiver
@xray_recorder.capture("send_email")
def send_email(githubuser, scanuuid, dest_email, res, s3signed):

		# create a simple html body for the email
		mailmsg = '<html><body><h2>report for ' + githubuser + '</h2><br>'

		# add the link to s3 signed url file 
		mailmsg += '<a href = ' + s3signed + '>link to csv file</a><br><table><br>'

		# create the table header row
		mailmsg += '<tr><th>repo</th><th>gituser</th><th>findings</th></tr>'

		# create a table row per dynamodb row
		for x in res:
			mailmsg += '<tr><td>' + '</td><td>'.join(map(str, x.values())) + '</td></tr>'

		mailmsg += '</table></body></html>'

		# create the email subject
		mailsubj = 'GitHub scan report for ' + githubuser + ' - ' + scanuuid


		# send the email using SES
		r = ses.send_email(
			Source = from_email,
			Destination = {'ToAddresses': [dest_email]},
			Message = {
				'Subject': {
					'Data': mailsubj
				},
				'Body': {
					'Html': {
						'Data': mailmsg
					}
				}
			}
		)
		
		print('sent email with subject ' + mailsubj + ' to ' + dest_email)


# retrieve the dynamodb scan data
@xray_recorder.capture("get_ddb_scan")
def get_ddb_scan(scanuuid):

	scan_res = []
	queryres = ddb_scan.query(IndexName = 'scantable_uuid', KeyConditionExpression = Key('scan_uuid').eq(scanuuid))

	for x in queryres['Items']:
		scan_res.append(x)

	# paginate through scan data results
	while 'LastEvaluatedKey' in queryres:
		lastkey = queryres['LastEvaluatedKey']
		queryres = ddb_scan.query(IndexName = 'scantable_uuid', KeyConditionExpression = Key('scan_uuid').eq(scanuuid), ExclusiveStartKey = lastkey)

		for x in queryres['Items']:
			scan_res.append(x)

	return scan_res

# retrieve the dynamodb metadata data
@xray_recorder.capture("get_ddb_meta")
def get_ddb_meta(scanuuid):

	meta_res = []
	queryres = ddb_meta.query(IndexName = 'metatable_scan_uuid', KeyConditionExpression = Key('scan_uuid').eq(scanuuid) & Key('count_finding').gte(0), ProjectionExpression = 'count_finding, gituser, gitrepo')

	for x in queryres['Items']:
		meta_res.append(x)

	# paginate through scan data results
	while 'LastEvaluatedKey' in queryres:
		lastkey = queryres['LastEvaluatedKey']
		queryres = ddb_meta.query(IndexName = 'metatable_scan_uuid', KeyConditionExpression = Key('scan_uuid').eq(scanuuid) & Key('count_finding').gte(0), ProjectionExpression = 'count_finding, gituser, gitrepo', ExclusiveStartKey = lastkey)

		for x in queryres['Items']:
			meta_res.append(x)

	return meta_res


# write the csv file to /tmp
@xray_recorder.capture("write_file")
def write_file(scan_res):
	
	# open the file for writing 
	filen = open('/tmp/out.csv', 'w') 
	
	# create the csv writer object 
	csv_writer = csv.writer(filen) 
	
	# set count to 0 
	count = 0

	# iterate over results
	for x in scan_res: 
		if count == 0: 
	
			# write the csv header
			csv_writer.writerow(x.keys())
			count += 1
	
		# write the csv record
		csv_writer.writerow(x.values())
	
	# close the file
	filen.close() 


# lambda handler
@xray_recorder.capture("handler")
def handler(event, context):

	# retrieve the scan id from step functions input
	scanuuid = str(event['Data'][0]['ScanID'])

	# retrieve the github user name from step function input
	githubuser = str(event['Data'][0]['GithubRepo'])

	# get scan and metadata data from dynamodb
	meta_res = get_ddb_meta(scanuuid)
	scan_res = get_ddb_scan(scanuuid)

	# write file
	write_file(scan_res)

	# create s3 filename
	s3filename = githubuser + "_" + scanuuid + ".csv"

	# upload the report file to s3
	s3.put_object(Bucket = s3_bucket, Body = open('/tmp/out.csv', 'rb'), Key = s3filename, ContentType = 'text/csv', ACL = 'private')

	# generate a presigned url for the file	
	s3signed = s3.generate_presigned_url(ClientMethod = 'get_object', Params = {'Bucket': s3_bucket, 'Key': s3filename}, ExpiresIn = s3_link_expiry)

	# check if an email was submitted to env variables, else skip
	if re.search('@', dest_email):
		send_email(githubuser, scanuuid, dest_email, meta_res, s3signed)

	# return bucket name and file path
	print(s3signed)
	return str(s3signed)
