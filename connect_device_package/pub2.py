import time
import ssl
import json
import paho.mqtt.client as mqtt
# Import the CallbackAPIVersion enum (needed for paho-mqtt v2.0.0+)
from paho.mqtt.client import CallbackAPIVersion
import sys # Import sys for exiting cleanly on connection failure

# --- AWS IoT Core Configuration (Using your values) ---
AWS_IOT_ENDPOINT = "a12vk58hg73akk-ats.iot.ap-south-1.amazonaws.com"
PORT = 8883
CLIENT_ID = "mySimpleIotDevice"
TOPIC = "sdk/test/python"
PATH_TO_AMAZON_ROOT_CA = "root-CA.crt"
PATH_TO_PRIVATE_KEY = "pub_sub.private.key"
PATH_TO_CERTIFICATE = "pub_sub.cert.pem"
# ----------------------------------------------------------

# --- Global flag to signal connection status ---
connection_established = False
connection_error_code = None

# --- Callback function for when the client connects to AWS IoT Core ---
def on_connect(client, userdata, flags, rc, properties=None):
    """Callback executed when the MQTT client connection attempt completes."""
    global connection_established, connection_error_code # Use global variables
    if rc == 0:
        print(f"Connected successfully to AWS IoT Core! (Return Code: {rc})")
        connection_established = True
        connection_error_code = None # Reset error code on success
    else:
        print(f"Connection failed. Return Code: {rc} - {mqtt.error_string(rc)}")
        # Handle specific error codes if necessary
        if rc == 5:
            print("Error Detail: Not authorized. Check your IoT policy and certificate attachment.")
        elif rc == 4:
             print("Error Detail: Connection refused - incorrect broker address/port?")
        elif rc == 3:
             print("Error Detail: Connection refused - server unavailable?")
        # Add more specific error handling based on rc codes if needed
        connection_established = False # Ensure flag is False on failure
        connection_error_code = rc   # Store the error code

# --- Callback function for when a message is published ---
def on_publish(client, userdata, mid, rc, properties=None):
    """Callback executed when a message acknowledgment is received from the broker."""
    # Note: In paho-mqtt v2, on_publish gets rc and properties args.
    print(f"Message {mid} published successfully.")


# --- Main execution ---
if __name__ == '__main__':

    # --- Initialize MQTT Client ---
    # Using VERSION1 still, but acknowledge the DeprecationWarning.
    # Consider updating callbacks to VERSION2 signature later for better practice.
    try:
        # Explicitly use VERSION1 for compatibility with current callbacks
        # Note: You will still see the DeprecationWarning until callbacks are updated
        print("Initializing MQTT Client (using deprecated Callback API V1)...")
        mqtt_client = mqtt.Client(
            client_id=CLIENT_ID,
            callback_api_version=CallbackAPIVersion.VERSION1
        )
    except TypeError as e:
         print(f"Error initializing MQTT Client: {e}")
         exit()
    except Exception as e:
        print(f"An unexpected error occurred during client initialization: {e}")
        exit()

    # --- Assign callback functions ---
    mqtt_client.on_connect = on_connect
    mqtt_client.on_publish = on_publish

    # --- Configure TLS/SSL connection ---
    print("Setting up TLS/SSL...")
    try:
        mqtt_client.tls_set(
            ca_certs=PATH_TO_AMAZON_ROOT_CA,
            certfile=PATH_TO_CERTIFICATE,
            keyfile=PATH_TO_PRIVATE_KEY,
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLSv1_2,
            ciphers=None
        )
        print("TLS/SSL configuration successful.")
    except FileNotFoundError as e:
        print(f"Error: Certificate or key file not found: {e}")
        print("Please ensure the paths to your certificate files are correct.")
        exit()
    except ssl.SSLError as e:
        print(f"SSL Error during TLS setup: {e}")
        print("Check certificate validity, paths, and permissions.")
        exit()
    except Exception as e:
        print(f"An error occurred during TLS setup: {e}")
        exit()

    # --- Connect to AWS IoT Core ---
    print(f"Connecting to AWS IoT Core endpoint: {AWS_IOT_ENDPOINT} on port {PORT}...")
    try:
        mqtt_client.connect(AWS_IOT_ENDPOINT, PORT, keepalive=60)
    except Exception as e:
        # Catch errors during the *initial* connect call (e.g., DNS resolution)
        print(f"Error initiating connection to AWS IoT Core: {e}")
        exit()

    # --- Start the MQTT network loop ---
    # This runs in a background thread
    mqtt_client.loop_start()

    # --- Wait for the connection to be established ---
    print("Waiting for connection confirmation...")
    connection_start_time = time.time()
    connection_timeout = 30 # Wait max 30 seconds for connection

    while not connection_established:
        time.sleep(0.1) # Wait briefly
        if connection_error_code is not None:
            print(f"Failed to connect (Error Code: {connection_error_code}). Exiting.")
            mqtt_client.loop_stop() # Stop the background thread cleanly
            sys.exit(1) # Exit with an error status
        if time.time() - connection_start_time > connection_timeout:
             print("Connection attempt timed out. Exiting.")
             mqtt_client.loop_stop()
             sys.exit(1)

    # --- If we reach here, connection is established ---
    print("Connection confirmed. Starting publishing loop...")

    # --- Publish messages in a loop ---
    message_count = 0
    try:
        while True:
            message_count += 1
            # --- Prepare your text data ---
            text_data = f"Hello from device {CLIENT_ID}! Message number: {message_count}"
            payload = json.dumps({
                "deviceId": CLIENT_ID,
                "timestamp": time.time(), # Use current timestamp
                "message": text_data
            })

            # --- Publish the message ---
            print(f"\nPublishing message {message_count} to topic '{TOPIC}':")
            print(f"Payload: {payload}")
            result = mqtt_client.publish(TOPIC, payload, qos=1)
            result.wait_for_publish() # Wait for PUBACK for QoS 1

            # Check if publish was successful (result.is_published() is True after wait_for_publish)
            if result.is_published():
                 # on_publish callback will also be triggered
                 pass # No need to print success here again as on_publish handles it
            else:
                 # This case is less likely with wait_for_publish but good practice
                print(f"Failed to publish message {message_count}. Error code: {result.rc} - {mqtt.error_string(result.rc)}")


            # --- Wait before sending the next message ---
            time.sleep(5) # Send a message every 5 seconds

    except KeyboardInterrupt:
        print("\nReceived KeyboardInterrupt. Shutting down...")
    except Exception as e:
        print(f"\nAn unexpected error occurred during publishing loop: {e}")
    finally:
        # --- Stop the network loop and disconnect ---
        print("Stopping MQTT loop...")
        mqtt_client.loop_stop()
        print("Disconnecting from AWS IoT Core...")
        mqtt_client.disconnect()
        print("Client disconnected.")