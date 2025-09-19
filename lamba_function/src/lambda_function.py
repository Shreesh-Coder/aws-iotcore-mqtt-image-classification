import base64
import boto3
import json
from io import BytesIO
from PIL import Image

def lambda_handler(event, context):
    """
    Lambda function to perform inference using a pre-built SageMaker MobileNet endpoint.
    
    This function expects the incoming event to have an "image_data" field containing a 
    base64-encoded string of the JPEG image.
    
    Expected event format:
    {
      "image_data": "<base64-encoded image string>"
    }
    """
    # Create a SageMaker runtime client.
    sagemaker_runtime = boto3.client('runtime.sagemaker')
    
    # Extract the base64 image data from the event.
    try:
        image_b64 = event.get("image_data")
        if not image_b64:
            raise ValueError("Missing 'image_data' in event")
    except Exception as e:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': f"Error parsing event data: {e}"})
        }
    
    # Decode the base64 image data.
    try:
        image_bytes = base64.b64decode(image_b64)
    except Exception as e:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': f"Error decoding image: {e}"})
        }
    
    # Preprocess the image: convert to RGB and resize to 224x224 pixels.
    try:
        image = Image.open(BytesIO(image_bytes)).convert('RGB')
        image = image.resize((224, 224))
        buffer = BytesIO()
        image.save(buffer, format="JPEG")
        processed_image = buffer.getvalue()
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f"Image preprocessing failed: {e}"})
        }
    
    # Invoke the pre-built SageMaker endpoint.
    try:
        endpoint_name = "jumpstart-dft-mobilenet-v2-100-224-20250413-142241"  # Use your actual endpoint name.
        response = sagemaker_runtime.invoke_endpoint(
            EndpointName=endpoint_name,
            ContentType='application/x-image',
            Body=processed_image
        )
        # Assume the endpoint returns JSON formatted inference results.
        result = json.loads(response['Body'].read().decode())
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f"Error invoking SageMaker endpoint: {e}"})
        }
    
    return {
        'statusCode': 200,
        'body': json.dumps(result),
        'response' : result
    }
