import paho.mqtt.client as mqtt
import ssl
import time

# Callback when connection is established.
def on_connect(client, userdata, flags, rc):
    print("Connected with result code " + str(rc))

# File paths for certificates
CA_CERT = r"root-CA.crt"
CERT_FILE = r"pub_sub.cert.pem"
KEY_FILE = r"pub_sub.private.key"

# AWS IoT endpoint and port details
AWS_IOT_ENDPOINT = "a12vk58hg73akk-ats.iot.ap-south-1.amazonaws.com"
MQTT_PORT = 8883
MQTT_TOPIC = "sdk/test/python"

# Initialize the MQTT client and configure callbacks.
client = mqtt.Client()
client.on_connect = on_connect

# Set up TLS with the necessary certificate files.
client.tls_set(ca_certs=CA_CERT,
               certfile=CERT_FILE,
               keyfile=KEY_FILE,
               tls_version=ssl.PROTOCOL_TLSv1_2)

# Connect to AWS IoT.
client.connect(AWS_IOT_ENDPOINT, MQTT_PORT, keepalive=60)
client.loop_start()

# Message to publish
MESSAGE = "hello shreesh"

# Continuously publish the message.
try:
    while True:
        client.publish(MQTT_TOPIC, MESSAGE)
        print("Published message to topic:", MQTT_TOPIC)
        time.sleep(1)  # Publish every second
except Exception as e:
    print("Error sending message:", e)

# Cleanly disconnect (this part may not be reached if loop runs indefinitely).
time.sleep(2)
client.loop_stop()
client.disconnect()
