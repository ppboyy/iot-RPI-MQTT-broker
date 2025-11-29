import ssl
import time
import logging
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.DEBUG)

# ---- CONFIG ----
MQTT_BROKER = "a5916n61elm51-ats.iot.ap-southeast-1.amazonaws.com"  # from AWS IoT > Settings
MQTT_PORT   = 8883
MQTT_TOPIC  = "washer/pi/test"

CA_PATH   = "/home/andrea/aws-iot/certs/AmazonRootCA1.pem"
CERT_PATH = "/home/andrea/aws-iot/certs/device.pem.crt"
KEY_PATH  = "/home/andrea/aws-iot/certs/private.pem.key"

print("🔥 Script started")

# ---- CALLBACKS ----
def on_connect(client, userdata, flags, rc):
    print("🟢 on_connect called, rc =", rc)

def on_disconnect(client, userdata, rc):
    print("🔴 on_disconnect called, rc =", rc)

def on_publish(client, userdata, mid):
    print("📤 on_publish called, mid =", mid)

# ---- CLIENT SETUP ----
client = mqtt.Client(client_id="raspi-washer-01")
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_publish = on_publish

client.enable_logger()

print("🔧 Setting TLS…")
client.tls_set(
    ca_certs=CA_PATH,
    certfile=CERT_PATH,
    keyfile=KEY_PATH,
    cert_reqs=ssl.CERT_REQUIRED,
    tls_version=ssl.PROTOCOL_TLS,
    ciphers=None,
)
client.tls_insecure_set(False)

print("🌐 Calling connect() to", MQTT_BROKER, MQTT_PORT)
try:
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    print("✅ connect() returned without exception")
except Exception as e:
    print("💥 connect() raised exception:", repr(e))
    raise

print("🔁 Starting network loop…")
client.loop_start()

# ---- MAIN LOOP ----
try:
    while True:
        payload = '{"message": "hello from Raspberry Pi", "power": 123}'
        print("Publishing:", payload, "| is_connected:", client.is_connected())
        result = client.publish(MQTT_TOPIC, payload, qos=1)
        # result is (rc, mid)
        print("    publish() rc =", result[0], "mid =", result[1])
        time.sleep(5)
except KeyboardInterrupt:
    print("Exiting…")
finally:
    client.loop_stop()
    client.disconnect()
