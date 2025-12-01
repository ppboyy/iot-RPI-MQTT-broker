import paho.mqtt.client as mqtt
import json
import csv
import datetime
import os
import time

# --- Configuration ---
# Replace 'localhost' with the IP or hostname of your MQTT broker if it's different.
MQTT_BROKER = 'localhost'
MQTT_PORT = 1883
# Use the exact topic you provided.
MQTT_TOPIC = "shellypluspluguk-3c8a1fec7d44/status/switch:0"
CSV_FILE_PATH = "power_log_gus.csv"
# The JSON key containing the power value.
POWER_KEY = "apower"
# Time in seconds between attempts to reconnect to the MQTT broker.
RECONNECT_DELAY_S = 5

def initialize_csv(filepath):
    """Creates the CSV file with headers if it doesn't already exist."""
    file_exists = os.path.exists(filepath)
    with open(filepath, 'a', newline='') as csvfile:
        fieldnames = ['timestamp', 'power_w']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        if not file_exists or os.stat(filepath).st_size == 0:
            writer.writeheader()
            print(f"[{datetime.datetime.now().isoformat()}] Created new CSV file: {filepath}")

def on_connect(client, userdata, flags, rc):
    """The callback for when the client receives a CONNACK response from the server."""
    if rc == 0:
        print(f"[{datetime.datetime.now().isoformat()}] Connected to MQTT Broker successfully.")
        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect, the subscriptions will be renewed.
        client.subscribe(MQTT_TOPIC)
        print(f"[{datetime.datetime.now().isoformat()}] Subscribed to topic: {MQTT_TOPIC}")
    else:
        print(f"[{datetime.datetime.now().isoformat()}] Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    """The callback for when a PUBLISH message is received from the server."""
    try:
        # 1. Parse the payload from bytes to a JSON object
        payload = msg.payload.decode('utf-8')
        data = json.loads(payload)
        
        # 2. Extract the power value
        power_value = data.get(POWER_KEY)

        if power_value is not None:
            # 3. Get the current timestamp
            current_time = datetime.datetime.now().isoformat()
            
            # 4. Log the data
            log_data = {'timestamp': current_time, 'power_w': power_value}
            
            with open(CSV_FILE_PATH, 'a', newline='') as csvfile:
                fieldnames = ['timestamp', 'power_w']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writerow(log_data)
            
            print(f"[{current_time}] LOGGED: Power={power_value} W")
        else:
            print(f"[{datetime.datetime.now().isoformat()}] WARNING: '{POWER_KEY}' key not found in payload: {payload[:50]}...")

    except json.JSONDecodeError:
        print(f"[{datetime.datetime.now().isoformat()}] ERROR: Could not decode JSON payload: {msg.payload.decode('utf-8')}")
    except Exception as e:
        print(f"[{datetime.datetime.now().isoformat()}] UNEXPECTED ERROR: {e}")

def main():
    # Ensure the CSV file is ready
    initialize_csv(CSV_FILE_PATH)
    
    client = mqtt.Client(client_id="ShellyPowerLogger")
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"[{datetime.datetime.now().isoformat()}] Connecting to broker: {MQTT_BROKER}:{MQTT_PORT}")
    
    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 5)
            # Blocking call that processes network traffic, dispatches callbacks and
            # handles reconnecting. Loops forever.
            client.loop_forever()
        except ConnectionRefusedError:
            print(f"[{datetime.datetime.now().isoformat()}] ERROR: Connection refused by broker. Retrying in {RECONNECT_DELAY_S} seconds...")
        except TimeoutError:
            print(f"[{datetime.datetime.now().isoformat()}] ERROR: Connection attempt timed out. Retrying in {RECONNECT_DELAY_S} seconds...")
        except KeyboardInterrupt:
            print(f"[{datetime.datetime.now().isoformat()}] Logger stopped by user.")
            break
        except Exception as e:
            print(f"[{datetime.datetime.now().isoformat()}] An unexpected network error occurred: {e}. Retrying in {RECONNECT_DELAY_S} seconds...")
        
        # Wait before retrying connection
        time.sleep(RECONNECT_DELAY_S)

if __name__ == "__main__":
    main()
