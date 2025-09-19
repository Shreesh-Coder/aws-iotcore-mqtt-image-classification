#This should run with your default unzipping of aws sdk
#Make sure to replace caPath, certPath, awshost and keypath with your own certificates. Make sure you place this file inside the extracted aws-sdk folder
#Refer to the start.sh file to check your awshost form the command line arguments being passed there

import paho.mqtt.client as mqttClient
import time
import ast
import random
import ssl

def location_generator():
    corr={'x':random.randrange(0,250,1),
          'y':random.randrange(0,250,1)}
    return corr

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to broker")
        global Connected  # Use global variable
        Connected = True  # Signal connection
    else:
        print("Connection failed Return Code : ",rc)


Connected = False  # global variable for the state of the connection
client_name="basicPubSub" #This is the client name by default allowed in the policy
curr=location_generator()


#AWS_PART
MQTT_TOPIC = "sdk/test/python"
client = mqttClient.Client(mqttClient.CallbackAPIVersion.VERSION2, client_name)  # create new instance
# mqtt.CallbackAPIVersion.VERSION2
# client = mqttClient.Client(client_name)
client.on_connect = on_connect  # attach function to callback

awshost = "a12vk58hg73akk-ats.iot.ap-south-1.amazonaws.com" #replace
awsport = 8883

caPath = "root-CA.crt" # Root certificate authority, comes from AWS (Replace)
certPath = "pub_sub.cert.pem" #Replace
keyPath = "pub_sub.private.key" #Replace

client.tls_set(caPath, 
    certfile=certPath, 
    keyfile=keyPath, 
    cert_reqs=ssl.CERT_REQUIRED, 
    tls_version=ssl.PROTOCOL_TLSv1_2, ciphers=None)

client.connect(awshost, port = awsport)  # connect to broker
#AWS PART ENDS

client.loop_start()  # start the loop


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

except KeyboardInterrupt:
    print("exiting")
    client.disconnect()
    client.loop_stop()
