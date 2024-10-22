import json
import logging
from atlan_challenge1_2 import execute_atlan_script



def lambda_handler(event, context):
    connection_name = "aws-s3-connection-tech-challenge-sv"
    bucket_name_atlan = "atlan-tech-challenge-sv"
    
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.info("Lambda function started")
    
    # Your processing logic here
    logger.info("Processing event: %s", event)
    message = execute_atlan_script(connection_name, bucket_name_atlan)

    return {
        'statusCode': 200,
        'body': json.dumps({"message":message})
    }