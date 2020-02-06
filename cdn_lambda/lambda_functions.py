def lambda_handler(event, context):
    _ = event, context

    return {
        "status": "501",
        "statusDescription": "Not Implemented",
    }
