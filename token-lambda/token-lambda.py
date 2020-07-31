import uuid

def handler(event, context):
        
    # generate scan uuid
    srcuuid = uuid.uuid4().hex

    return {
        'GithubRepo' : event['GithubRepo'], 
        'ScanID' : srcuuid
    }
