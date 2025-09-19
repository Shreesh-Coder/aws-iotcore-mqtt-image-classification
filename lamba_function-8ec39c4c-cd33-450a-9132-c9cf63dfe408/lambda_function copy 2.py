import base64
import boto3
import json
#import os # To read environment variables
from io import BytesIO
from PIL import Image
import logging # Optional: for more structured logging

# Configure logging (optional, print works too)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Get config from environment variables
# jumpstart-dft-mobilenet-v2-100-224-20250423-113843
SAGEMAKER_ENDPOINT_NAME = "jumpstart-dft-mobilenet-v2-100-224-20250423-113843"
RESPONSE_TOPIC = "device/image/response" # e.g., 'device/image/response'


# Initialize clients outside the handler for potential reuse
sagemaker_runtime = boto3.client('runtime.sagemaker')
iot_data_client = boto3.client('iot-data')

def lambda_handler(event, context):
    """
    Lambda function to:
    1. Receive base64 image data via event (triggered by IoT rule).
    2. Decode and preprocess the image.
    3. Invoke a SageMaker endpoint for inference.
    4. Publish the inference result (or error) to a specific MQTT topic.
    5. Log the final return payload (for CloudWatch).
    6. Return the payload to the invoking service (AWS IoT).
    """
    logger.info(f"Received event: {json.dumps(event)}") # Log incoming event

    # Ensure required environment variables are set
    if not SAGEMAKER_ENDPOINT_NAME:
        error_message = "Error: SAGEMAKER_ENDPOINT_NAME environment variable not set."
        logger.error(error_message)
        # Cannot publish error if topic is unknown, just return
        return {'statusCode': 500, 'body': json.dumps({'error': error_message})}
    if not RESPONSE_TOPIC:
        error_message = "Error: RESPONSE_TOPIC environment variable not set."
        logger.error(error_message)
        # Cannot publish error if topic is unknown, just return
        return {'statusCode': 500, 'body': json.dumps({'error': error_message})}

    # --- 1. Extract Image Data ---
    try:
        # Assuming the event *is* the JSON payload from the device script
        # If IoT Rule wraps it, adjust access (e.g., event['image_data'])
        if isinstance(event, str): # Sometimes IoT Rule might pass it as a string
             event_data = json.loads(event)
        else:
             event_data = event # Assume it's already a dict

        image_b64 = event_data.get("image_data")
        if not image_b64:
            raise ValueError("Missing 'image_data' in event data")
    except Exception as e:
        error_message = f"Error parsing event data: {e}"
        logger.error(error_message)
        # Prepare payload to publish and return
        error_payload_dict = {'error': error_message}
        error_return_dict = {'statusCode': 400, 'body': json.dumps(error_payload_dict)}
        # Attempt to publish error to MQTT topic
        publish_response(error_payload_dict)
        # Log what will be returned
        logger.info(f"Returning error payload: {json.dumps(error_return_dict)}")
        return error_return_dict

    # --- 2. Decode Image ---
    try:
        image_bytes = base64.b64decode(image_b64)
    except Exception as e:
        error_message = f"Error decoding base64 image: {e}"
        logger.error(error_message)
        error_payload_dict = {'error': error_message}
        error_return_dict = {'statusCode': 400, 'body': json.dumps(error_payload_dict)}
        publish_response(error_payload_dict)
        logger.info(f"Returning error payload: {json.dumps(error_return_dict)}")
        return error_return_dict

    # --- 3. Preprocess Image ---
    try:
        image = Image.open(BytesIO(image_bytes)).convert('RGB')
        image = image.resize((224, 224))
        buffer = BytesIO()
        image.save(buffer, format="JPEG")
        processed_image = buffer.getvalue()
        logger.info(f"Image preprocessed successfully. Size: {len(processed_image)} bytes.")
    except Exception as e:
        error_message = f"Image preprocessing failed: {e}"
        logger.error(error_message)
        error_payload_dict = {'error': error_message}
        error_return_dict = {'statusCode': 500, 'body': json.dumps(error_payload_dict)}
        publish_response(error_payload_dict)
        logger.info(f"Returning error payload: {json.dumps(error_return_dict)}")
        return error_return_dict

    # --- 4. Invoke SageMaker Endpoint ---
    try:
        logger.info(f"Invoking SageMaker endpoint: {SAGEMAKER_ENDPOINT_NAME}")
        response = sagemaker_runtime.invoke_endpoint(
            EndpointName=SAGEMAKER_ENDPOINT_NAME,
            ContentType='application/x-image',
            Body=processed_image
        )
        # Decode the response body (assuming endpoint returns JSON)
        sagemaker_result_str = response['Body'].read().decode('utf-8')
        sagemaker_result = json.loads(sagemaker_result_str)
        logger.info(f"SageMaker endpoint response received: {sagemaker_result_str}")

        # --- 5. Publish Success Result to MQTT ---
        # Publish the actual SageMaker result
        publish_response(sagemaker_result)

        # --- 6. Prepare & Log Success Return Payload ---
        # The payload returned to IoT Service
        success_return_dict = {
            'statusCode': 200,
            # The body returned to IoT typically contains the SM result too
            'body': json.dumps(sagemaker_result)
        }
        logger.info(f"Returning success payload: {json.dumps(success_return_dict)}")
        return success_return_dict

    except Exception as e:
        # Handle errors during SageMaker invocation or response processing
        error_message = f"Error invoking SageMaker endpoint or processing response: {e}"
        logger.exception(error_message) # Use logger.exception to include traceback
        error_payload_dict = {'error': error_message}
        error_return_dict = {'statusCode': 500, 'body': json.dumps(error_payload_dict)}
        # Attempt to publish the error message
        publish_response(error_payload_dict)
        # Log what will be returned
        logger.info(f"Returning error payload: {json.dumps(error_return_dict)}")
        return error_return_dict


def publish_response(payload_dict):
    """Helper function to publish a dictionary payload to the configured MQTT topic."""
    global iot_data_client, RESPONSE_TOPIC # Access global variables
    try:
        logger.info(f"Attempting to publish to MQTT topic '{RESPONSE_TOPIC}': {json.dumps(payload_dict)}")
        iot_data_client.publish(
            topic=RESPONSE_TOPIC,
            qos=1, # Quality of Service 1 (At least once)
            payload=json.dumps(payload_dict)
        )
        logger.info("Successfully published response to MQTT.")
    except Exception as e:
        # Log the error but don't stop the Lambda return path
        logger.error(f"Failed to publish response to MQTT topic '{RESPONSE_TOPIC}': {e}")