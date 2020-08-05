import time
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all

patch_all()


# lambda handler
@xray_recorder.capture("handler")
def handler(event, context):
        
    # get the submitted github repo
    githubrepo = event['GithubRepo']
    
    # check if scanid was submitted in step function input
    if 'ScanID' in event.keys():
        scan_uuid = str(event['ScanID'])
        print('received ' + scan_uuid + ' as ScanID input')

    # if scanid not submitted, generate a new scan uuid
    else:
        scan_uuid = str(hex(int(time.time())))
        print('generated ' + scan_uuid)

    # return the githubrepo and scan id
    return {
        'GithubRepo' : githubrepo, 
        'ScanID' : scan_uuid
    }
