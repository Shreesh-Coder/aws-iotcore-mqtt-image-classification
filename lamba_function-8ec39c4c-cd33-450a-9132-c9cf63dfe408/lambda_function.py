# --- Keep imports, configuration, label loading, and publish_response the same ---
import base64
import boto3
import json
from io import BytesIO
from PIL import Image
import logging
import os
import csv
import traceback

# --- Configuration ---
logger = logging.getLogger()
logger.setLevel(logging.INFO)
SAGEMAKER_ENDPOINT_NAME = os.environ.get("SAGEMAKER_ENDPOINT_NAME", "jumpstart-dft-mobilenet-v2-100-224-20250423-113843")
RESPONSE_TOPIC = os.environ.get("RESPONSE_TOPIC", "device/image/response")
LABELS_FILENAME = "imagenet_labels.csv"

# Initialize AWS clients
sagemaker_runtime = boto3.client('runtime.sagemaker')
iot_data_client = boto3.client('iot-data')

# --- Global variable for labels ---
IMAGENET_LABELS = []
LABELS_LOADED_SUCCESSFULLY = False

# --- Function to Load Labels from CSV (Keep As Is) ---
def load_labels_from_csv(filename):
    global IMAGENET_LABELS, LABELS_LOADED_SUCCESSFULLY
    logger.info(f"Attempting to load ImageNet labels from local file: {filename}")
    labels_temp = [None] * 1000
    count = 0
    try:
        with open(filename, mode='r', encoding='utf-8') as infile:
            reader = csv.reader(infile)
            for row in reader:
                try:
                    if len(row) == 2:
                        index = int(row[0])
                        label = row[1]
                        if 0 <= index < 1000:
                            if labels_temp[index] is None:
                                labels_temp[index] = label
                                count += 1
                            else:
                                logger.warning(f"Duplicate index {index} found in {filename}. Using first occurrence.")
                        else:
                            logger.warning(f"Index {index} out of bounds (0-999) in {filename}.")
                    else:
                        logger.warning(f"Skipping malformed row in {filename}: {row}")
                except (ValueError, IndexError) as row_err:
                     logger.warning(f"Error processing row in {filename}: {row} - {row_err}")

        if count == 1000 and all(label is not None for label in labels_temp):
            IMAGENET_LABELS = labels_temp
            LABELS_LOADED_SUCCESSFULLY = True
            logger.info(f"Successfully loaded {len(IMAGENET_LABELS)} labels from {filename}. Start: {IMAGENET_LABELS[:3]}")
        else:
            logger.error(f"Failed to load all 1000 labels correctly from {filename}. Found {count} valid labels.")
            IMAGENET_LABELS = []
            LABELS_LOADED_SUCCESSFULLY = False
    except FileNotFoundError:
        logger.error(f"CRITICAL ERROR: Label file '{filename}' not found in Lambda deployment package.")
        IMAGENET_LABELS = []
        LABELS_LOADED_SUCCESSFULLY = False
    except Exception as e:
        logger.error(f"Exception during label loading from {filename}: {e}")
        logger.error(traceback.format_exc())
        IMAGENET_LABELS = []
        LABELS_LOADED_SUCCESSFULLY = False

# --- Load labels during Lambda initialization ---
load_labels_from_csv(LABELS_FILENAME)

# --- Helper function to publish (Keep As Is) ---
def publish_response(payload_dict):
    global iot_data_client, RESPONSE_TOPIC
    if not RESPONSE_TOPIC:
        logger.error("RESPONSE_TOPIC not configured. Cannot publish to MQTT.")
        return
    if not iot_data_client:
         logger.error("IoT Data Client not initialized. Cannot publish.")
         return
    try:
        payload_json = json.dumps(payload_dict)
        logger.info(f"Attempting to publish to MQTT topic '{RESPONSE_TOPIC}': {payload_json}")
        iot_data_client.publish( topic=RESPONSE_TOPIC, qos=1, payload=payload_json )
        logger.info("Successfully published response to MQTT.")
    except Exception as e:
        logger.error(f"Failed to publish response to MQTT topic '{RESPONSE_TOPIC}': {e}")

# --- Main Lambda Handler (Corrected) ---
def lambda_handler(event, context):
    logger.info(f"Received event: {json.dumps(event)}")
    logger.info(f"Label loading status during handler execution: {'Success' if LABELS_LOADED_SUCCESSFULLY else 'Failed/Incomplete'}. Label count: {len(IMAGENET_LABELS)}")

    if not LABELS_LOADED_SUCCESSFULLY:
        error_message = "Error: ImageNet labels could not be loaded from the local CSV file during initialization. Cannot map probabilities to labels."
        logger.error(error_message)
        error_payload_dict = {'error': error_message}
        publish_response(error_payload_dict)
        return {'statusCode': 500, 'body': json.dumps(error_payload_dict)}

    if not SAGEMAKER_ENDPOINT_NAME:
        return {'statusCode': 500, 'body': json.dumps({'error': "Error: SAGEMAKER_ENDPOINT_NAME configuration missing."})}

    # --- 1. Extract Image Data ---
    try:
        if isinstance(event, str): event_data = json.loads(event)
        else: event_data = event
        image_b64 = event_data.get("image_data")
        if not image_b64: raise ValueError("Missing 'image_data' in event data")
    except Exception as e:
        error_message = f"Error parsing event data: {e}"
        error_payload_dict = {'error': error_message}
        publish_response(error_payload_dict)
        return {'statusCode': 400, 'body': json.dumps(error_payload_dict)}

    # --- 2. Decode Image ---
    try:
        image_bytes = base64.b64decode(image_b64)
    except Exception as e:
        error_message = f"Error decoding base64 image: {e}"
        error_payload_dict = {'error': error_message}
        publish_response(error_payload_dict)
        return {'statusCode': 400, 'body': json.dumps(error_payload_dict)}

    # --- 3. Preprocess Image ---
    try:
        image = Image.open(BytesIO(image_bytes)).convert('RGB')
        image = image.resize((224, 224))
        buffer = BytesIO()
        image.save(buffer, format="JPEG")
        processed_image = buffer.getvalue()
        logger.info(f"Image preprocessed successfully.")
    except Exception as e:
        error_message = f"Image preprocessing failed: {e}"
        error_payload_dict = {'error': error_message}
        publish_response(error_payload_dict)
        return {'statusCode': 500, 'body': json.dumps(error_payload_dict)}

    # --- 4. Invoke SageMaker Endpoint ---
    try:
        logger.info(f"Invoking SageMaker endpoint: {SAGEMAKER_ENDPOINT_NAME}")
        response = sagemaker_runtime.invoke_endpoint(
            EndpointName=SAGEMAKER_ENDPOINT_NAME,
            ContentType='application/x-image',
            Body=processed_image
        )
        sagemaker_result_str = response['Body'].read().decode('utf-8')
        logger.info(f"RAW SageMaker response string: {sagemaker_result_str[:500]}...")

        # --- Process SageMaker Response ---
        sagemaker_parsed_data = json.loads(sagemaker_result_str) # Parse the JSON
        logger.info(f"Parsed SageMaker response TYPE: {type(sagemaker_parsed_data)}")

        # *** CORRECTED PART ***
        # Check if it's a dictionary and has the 'probabilities' key
        if isinstance(sagemaker_parsed_data, dict) and "probabilities" in sagemaker_parsed_data:
            sagemaker_probabilities = sagemaker_parsed_data["probabilities"] # <-- Access the list here
            logger.info(f"Successfully extracted 'probabilities' list. Length: {len(sagemaker_probabilities)}")

            # Now we are sure sagemaker_probabilities is a list (or should be)
            if not isinstance(sagemaker_probabilities, list):
                 # This case should be rare now, but good for safety
                 raise TypeError(f"Value under 'probabilities' key is not a list, type: {type(sagemaker_probabilities)}")

        # --- Handle case where the response format is totally wrong ---
        else:
            error_message = "Error: Unexpected SageMaker response format. Expected a JSON object with a 'probabilities' key containing a list."
            logger.error(error_message + f" Got: {sagemaker_parsed_data}")
            output_payload = {'error': error_message}
            error_return_dict = {'statusCode': 502, 'body': json.dumps(output_payload)} # 502 Bad Gateway is appropriate
            publish_response(output_payload)
            return error_return_dict

        # --- 5. Map Probabilities to Label ---
        # (This part remains the same as it now operates on the correct list)
        if len(sagemaker_probabilities) != len(IMAGENET_LABELS):
             logger.warning(f"Model output size ({len(sagemaker_probabilities)}) != Label list size ({len(IMAGENET_LABELS)}). Mapping may fail.")

        max_prob = max(sagemaker_probabilities)
        predicted_index = sagemaker_probabilities.index(max_prob)
        logger.info(f"Calculated max probability: {max_prob:.4f} at index: {predicted_index}")

        predicted_label = "Error: Label index out of bounds or mapping failed" # Default
        if 0 <= predicted_index < len(IMAGENET_LABELS):
            predicted_label = IMAGENET_LABELS[predicted_index]
            logger.info(f"Successfully looked up label for index {predicted_index}: '{predicted_label}'")
        else:
            logger.error(f"Predicted index {predicted_index} is out of bounds for labels list (length {len(IMAGENET_LABELS)}).")

        # --- 6. Construct Final Output Payload ---
        output_payload = {
            'prediction': predicted_label,
            'confidence': round(max_prob, 4)
        }

        # --- 7. Publish Result to MQTT ---
        logger.info(f"Payload to be published/returned: {json.dumps(output_payload)}")
        publish_response(output_payload)

        # --- 8. Prepare & Log Success Return Payload ---
        success_return_dict = {
            'statusCode': 200,
            'body': json.dumps(output_payload)
        }
        logger.info(f"Returning success payload: {json.dumps(success_return_dict)}")
        return success_return_dict

    except Exception as e:
        error_message = f"Unhandled exception during SageMaker interaction or result processing: {e}"
        logger.exception(error_message)
        error_payload_dict = {'error': error_message, 'traceback': traceback.format_exc()}
        error_return_dict = {'statusCode': 500, 'body': json.dumps(error_payload_dict)}
        publish_response(error_payload_dict)
        logger.info(f"Returning error payload: {json.dumps(error_return_dict)}")
        return error_return_dict