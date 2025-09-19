## End-to-End MQTT-Based Image Classification Pipeline on AWS IoT Core

This repository demonstrates an end-to-end, MQTT-only image classification workflow on AWS using AWS IoT Core. Embedded/edge clients publish base64-encoded images over MQTT; an AWS IoT Rule invokes a Lambda function which forwards the image to a SageMaker endpoint (MobileNet V2) for inference and republishes the result back to MQTT.

### Architecture
- **Publisher (Device/Client)**: Publishes JSON with base64 image to an MQTT request topic.
- **AWS IoT Core**: Secures device connectivity and routes messages.
- **IoT Rule**: Triggers a **Lambda** on the request topic.
- **Lambda**: Decodes `image_data`, calls **SageMaker** (MobileNet V2) for inference, republishes `{label, confidence}` to a response topic.
- **Subscriber (Client/Tooling)**: Subscribes to the response topic and prints results.

### Repository layout (relevant paths)
- `connect_device_package/aws-iot-device-sdk-python-v2/samples/pubsub-image.py`: Publisher script for images.
- `connect_device_package/aws-iot-device-sdk-python-v2/samples/subscribe_response.py`: Subscriber script for inference results.
- `lamba_function/`: Example Lambda source and template (adjust to your account/endpoint names).

Note: The AWS IoT Python SDK v2 is included as a git submodule in `connect_device_package/aws-iot-device-sdk-python-v2`.

## Demo videos
- **Video demo 1**: [End-to-end pipeline demo 1](https://iith-my.sharepoint.com/:v:/g/personal/cs23mtech12009_iith_ac_in/ESx4uJiuJ1hOr7YgNt5EJzUBDUxfrPzX4XNwUnbMIg5O7A?e=Px3AXO)
- **Video demo 2**: [End-to-end pipeline demo 2](https://iith-my.sharepoint.com/:v:/g/personal/cs23mtech12009_iith_ac_in/EaaNO33SMK9FrlA0ZyNRDLcBS-JOft0Dp7QoSlZ8fYe4Gw?e=evmhLA)

These videos show the publisher sending an image, Lambda invoking SageMaker, and the subscriber printing `{label, confidence}`.

## Prerequisites
- Python 3.8+
- AWS account with permissions for IoT Core, Lambda, and SageMaker
- Device certificates (X.509) and IoT policy allowing MQTT publish/subscribe to your topics
- SageMaker endpoint deployed with a MobileNet V2 model (or compatible image classifier)

### Install Python dependencies
It's recommended to use a virtual environment.

```bash
pip install --upgrade pip
pip install awsiotsdk
```

If you cloned this repository fresh, also initialize submodules:

```bash
git submodule update --init --recursive
```

## MQTT Topics (example)
- **Request topic**: `device/image/request`
- **Response topic**: `device/image/response`

You can choose different topic names; pass them via `--topic` to the scripts and update the IoT Rule accordingly.

## IoT Core setup (high level)
1) Create an IoT Thing (optional but recommended) and generate/download a certificate pair.
2) Attach an IoT Policy allowing connect, publish, subscribe, and receive on your chosen topics.
3) Note your account-specific IoT endpoint: it looks like `xxxxxxxxxxxxx-ats.iot.<region>.amazonaws.com`.

Example minimal policy (tighten as needed):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": ["iot:Connect"], "Resource": "*" },
    { "Effect": "Allow", "Action": ["iot:Publish"], "Resource": ["arn:aws:iot:<region>:<account-id>:topic/device/image/request"] },
    { "Effect": "Allow", "Action": ["iot:Subscribe"], "Resource": ["arn:aws:iot:<region>:<account-id>:topicfilter/device/image/response"] },
    { "Effect": "Allow", "Action": ["iot:Receive"], "Resource": ["arn:aws:iot:<region>:<account-id>:topic/device/image/response"] }
  ]
}
```

## IoT Rule → Lambda → SageMaker
- Create an IoT Rule that triggers on the request topic (e.g., `device/image/request`). Rule SQL:

```sql
SELECT * FROM 'device/image/request'
```

- Set the action to invoke your Lambda function.
- Lambda should:
  - Parse JSON payload containing `image_data` (base64 string)
  - Decode to bytes
  - Invoke your SageMaker endpoint (e.g., via `boto3.client('sagemaker-runtime').invoke_endpoint`)
  - Extract `{label, confidence}` from the model output
  - Publish the result JSON to the response topic (`device/image/response`) using the IoT Data Plane (`boto3.client('iot-data')`)

The included `lamba_function/` directory shows a minimal starting point; adapt it to your endpoint name and pre/post-processing.

## Running locally
Below commands assume you are in the repository root and have cert files handy. Replace placeholders with your actual paths and endpoint.

### 1) Start the response subscriber
Prints any JSON messages published to the response topic.

```bash
python connect_device_package/aws-iot-device-sdk-python-v2/samples/subscribe_response.py \
  --endpoint xxxxxxxxxxxxx-ats.iot.<region>.amazonaws.com \
  --cert path/to/your/device-certificate.pem.crt \
  --key path/to/your/private.pem.key \
  --ca_file path/to/AmazonRootCA1.pem \
  --client_id response_subscriber_1 \
  --topic device/image/response
```

Optional flags supported: `--port` (default 8883), `--proxy_host`, `--proxy_port`, `--verbosity`.

### 2) Publish an image to the request topic
Reads the image file, base64-encodes it into JSON, and publishes to the request topic.

```bash
python connect_device_package/aws-iot-device-sdk-python-v2/samples/pubsub-image.py \
  --endpoint xxxxxxxxxxxxx-ats.iot.<region>.amazonaws.com \
  --cert path/to/your/device-certificate.pem.crt \
  --key path/to/your/private.pem.key \
  --ca_file path/to/AmazonRootCA1.pem \
  --client_id image_publisher_1 \
  --topic device/image/request \
  --image_file connect_device_package/Chihuahua.jpg
```

Optional flags supported: `--port` (default 8883), `--proxy_host`, `--proxy_port`, `--verbosity`.

### Payloads
- Request JSON (published by `pubsub-image.py`):

```json
{ "image_data": "<base64-encoded-bytes>" }
```

- Response JSON (republished by Lambda):

```json
{ "label": "Chihuahua", "confidence": 0.97 }
```

## Notes & limits
- MQTT payload practical limit is ~128KB by default; the publisher script warns if exceeded.
- Ensure your device policy allows the exact topics you use.
- If using git clone elsewhere, run `git submodule update --init --recursive` before running samples.

## Quick start (GitHub)

```bash
git clone https://github.com/Shreesh-Coder/aws-iotcore-mqtt-image-classification.git
cd aws-iotcore-mqtt-image-classification
git submodule update --init --recursive
pip install awsiotsdk
```

Then follow the steps in "Running locally".

## License
Sample code under `connect_device_package/aws-iot-device-sdk-python-v2` follows its respective license (Apache-2.0). This repository’s additional content is provided under the same unless otherwise noted.


