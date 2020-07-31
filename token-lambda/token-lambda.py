import time

def handler(event, context):
        
    # generate scan uuid
    srcuuid = str(hex(int(time.time())))

    return {
        'GithubRepo' : event['GithubRepo'], 
        'ScanID' : srcuuid
    }
