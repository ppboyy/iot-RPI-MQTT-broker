#!/usr/bin/env python3
import paho.mqtt.client as mqtt
import ssl
import json
import time
import logging
from datetime import datetime
from enum import Enum
from threading import Lock

# ---- Logging Setup ----
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---- AWS IoT Core Configuration ----
AWS_IOT_BROKER = "a5916n61elm51-ats.iot.ap-southeast-1.amazonaws.com"
AWS_IOT_PORT = 8883

CA_PATH = "/home/andrea/aws-iot/certs/AmazonRootCA1.pem"
CERT_PATH = "/home/andrea/aws-iot/certs/device.pem.crt"
KEY_PATH = "/home/andrea/aws-iot/certs/private.pem.key"

# ---- Local MQTT Broker Configuration (for Shelly plugs) ----
LOCAL_MQTT_BROKER = "localhost"  # or your broker IP
LOCAL_MQTT_PORT = 1883

# ---- Machine Configuration ----
MACHINES = {
    "WM-01": {
        "name": "Washing Machine 1",
        "shelly_topic": "shellypluspluguk-3c8a1fec7d44/status/switch:0",
        "current_threshold": 8.0  # Watts
    },
    "WM-02": {
        "name": "Washing Machine 2",
        "shelly_topic": "simulator/WM-02/shelly",
        "current_threshold": 8.0
    },
    "WM-03": {
        "name": "Washing Machine 3",
        "shelly_topic": "simulator/WM-03/shelly",
        "current_threshold": 8.0
    },
    "WM-04": {
        "name": "Washing Machine 4",
        "shelly_topic": "simulator/WM-04/shelly",
        "current_threshold": 8.0
    }
}

# ---- Constants ----
DOOR_OPEN_DURATION = 10  # seconds
CYCLE_COUNT_FILE = "machine_cycles.json"
PUBLISH_INTERVAL = 30

class MachineState(Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    OCCUPIED = "OCCUPIED"

class MachineMonitor:
    """Monitors a single machine's state and aggregates power readings for averaging."""

    def __init__(self, machine_id, config):
        self.machine_id = machine_id
        self.name = config["name"]
        self.current_threshold = config["current_threshold"]

        self.state = MachineState.IDLE
        self.current_power = 0.0

        # Power averaging fields
        self.power_readings_sum = 0.0
        self.power_readings_count = 0

        self.door_is_open = False
        self.door_open_start_time = None
        self.cycle_count = 0
        self.last_state_change = datetime.now()

        self.power_lock = Lock()
    def update_power(self, power):
        with self.power_lock:
            if power is not None:
                self.power_readings_sum += power
                self.power_readings_count += 1

    def calculate_and_reset_average(self):
        with self.power_lock:
            if self.power_readings_count > 0:
                avg_power = self.power_readings_sum / self.power_readings_count
                self.current_power = avg_power
                self.power_readings_sum = 0
                self.power_readings_count = 0
                return avg_power

            # No new readings were recorded, DO NOT update self.power
            return self.current_power

    def update_door(self, is_open):
        self.door_is_open = is_open
        if not is_open:
            self.door_open_start_time = None

    def check_transitions(self):
        new_state = None
        cycle_completed = False

        if self.state == MachineState.IDLE:
            if self.current_power > self.current_threshold * 1.2:  # 20% hysteresis
                new_state = MachineState.RUNNING
                self.door_open_start_time = None

        elif self.state == MachineState.RUNNING:
            if self.current_power <= self.current_threshold * 0.8:  # 20% hysteresis
                new_state = MachineState.OCCUPIED

        elif self.state == MachineState.OCCUPIED:
            if self.door_is_open:
                if self.door_open_start_time is None:
                    self.door_open_start_time = time.time()
                elif time.time() - self.door_open_start_time >= DOOR_OPEN_DURATION:
                    new_state = MachineState.IDLE
                    self.door_open_start_time = None
                    cycle_completed = True
                    self.cycle_count += 1
            else:
                self.door_open_start_time = None

        if new_state and new_state != self.state:
            self.state = new_state
            self.last_state_change = datetime.now()
            return True, cycle_completed

        return False, False

    def get_status(self):
        """Get current status as dictionary"""
        return {
            "machine_id": self.machine_id,
            "name": self.name,
            "state": self.state.value,
            "power": round(self.current_power, 2),
            "door_open": self.door_is_open,
            "cycle_count": self.cycle_count,
            "last_change": self.last_state_change.isoformat()
        }

class MultiMachineMonitor:
    """Manages multiple machine monitors"""

    def __init__(self, machines_config):
        self.monitors = {
            machine_id: MachineMonitor(machine_id, config)
            for machine_id, config in machines_config.items()
        }
        self.load_cycle_counts()

    def load_cycle_counts(self):
        """Load saved cycle counts from file"""
        try:
            with open(CYCLE_COUNT_FILE, 'r') as f:
                counts = json.load(f)
                for machine_id, count in counts.items():
                    if machine_id in self.monitors:
                        self.monitors[machine_id].cycle_count = count
                print(f"Loaded cycle counts: {counts}")
        except FileNotFoundError:
            print("No previous cycle counts found, starting fresh")
        except Exception as e:
            print(f"Error loading cycle counts: {e}")

    def save_cycle_counts(self):
        """Save cycle counts to file"""
        try:
            counts = {
                machine_id: monitor.cycle_count
                for machine_id, monitor in self.monitors.items()
            }
            with open(CYCLE_COUNT_FILE, 'w') as f:
                json.dump(counts, f, indent=2)
        except Exception as e:
            print(f"Error saving cycle counts: {e}")

    def get_monitor(self, machine_id):
        """Get monitor for a specific machine"""
        return self.monitors.get(machine_id)

    def get_all_status(self):
        """Get status of all machines"""
        return {
            machine_id: monitor.get_status()
            for machine_id, monitor in self.monitors.items()
        }

# Global monitor manager
monitor_manager = None

def publish_machine_data(client):
    """
    Publish machine data to AWS IoT Core in the format expected by the backend API.
    Format matches the database schema: {timestamp, MachineID, cycle_number, current, state, door_opened}
    """
    timestamp = datetime.now().isoformat()

    for machine_id, monitor in monitor_manager.monitors.items():
        average_power = monitor.calculate_and_reset_average()
        
        # Check for state transitions BEFORE publishing
        state_changed, cycle_completed = monitor.check_transitions()
        
        if state_changed:
            logger.info(f"{monitor.name}: {monitor.state.value}")
        
        if cycle_completed:
            monitor_manager.save_cycle_counts()
            logger.info(f"✅ Cycle completed! Total cycles: {monitor.cycle_count}")
        
        # Create payload matching backend API format with UPDATED state
        payload = {
            "timestamp": timestamp,
            "MachineID": machine_id,
            "cycle_number": monitor.cycle_count,
            "current": round(average_power, 2),
            "state": monitor.state.value,
            "door_opened": monitor.door_is_open
        }

        # Publish to AWS IoT Core topic
        topic = f"washer/{machine_id}/data"
        client.publish(topic, json.dumps(payload), qos=1)

        logger.info(f"Published to {topic}: {payload}")

def on_connect(client, userdata, flags, rc):
    """Callback for when the client connects to AWS IoT Core"""
    if rc == 0:
        logger.info("✅ Connected to AWS IoT Core!")
        logger.info("Subscribing to topics:")

        # Subscribe to all hall sensors
        for machine_id in MACHINES.keys():
            hall_topic = f"{machine_id}/hall_sensor/state"
            client.subscribe(hall_topic, qos=1)
            logger.info(f"  - {hall_topic}")

        # Subscribe to all Shelly plugs
        for machine_id, config in MACHINES.items():
            shelly_topic = config["shelly_topic"]
            client.subscribe(shelly_topic, qos=1)
            logger.info(f"  - {shelly_topic}")

        logger.info(f"Data will be published every {PUBLISH_INTERVAL} seconds")
    else:
        logger.error(f"❌ Failed to connect to AWS IoT Core, return code {rc}")

def on_message(client, userdata, msg):
    """Callback for when a message is received from MQTT subscriptions"""
    try:
        # Check if it's a hall sensor message
        if "/hall_sensor/state" in msg.topic:
            machine_id = msg.topic.split("/")[0]
            monitor = monitor_manager.get_monitor(machine_id)

            if monitor:
                door_state = int(msg.payload.decode())
                monitor.update_door(door_state == 1)

                state_changed, cycle_completed = monitor.check_transitions()

                if state_changed:
                    logger.info(f"{monitor.name}: {monitor.state.value}")

                if cycle_completed:
                    monitor_manager.save_cycle_counts()
                    logger.info(f"✅ Cycle completed! Total cycles: {monitor.cycle_count}")

        # If not hall sensor, check if it's a Shelly plug
        else:
            for machine_id, config in MACHINES.items():
                if msg.topic == config["shelly_topic"]:
                    monitor = monitor_manager.get_monitor(machine_id)
                    if monitor:
                        data = json.loads(msg.payload.decode())
                        power = data.get("apower", 0.0)
                        monitor.update_power(power)
                        state_changed, _ = monitor.check_transitions()
                        if state_changed:
                            logger.info(f"{monitor.name}: {monitor.state.value}")
                    break

    except Exception as e:
        logger.error(f"Error processing message: {e}")
        logger.debug(f"Topic: {msg.topic}, Payload: {msg.payload}")

def on_disconnect(client, userdata, rc):
    if rc != 0:
        logger.warning(f"⚠️ Unexpected disconnect, attempting reconnect...")
        try:
            client.reconnect()
        except Exception as e:
            logger.error(f"Reconnect failed: {e}")
    else:
        logger.info("🔴 Disconnected from AWS IoT Core")

def on_publish(client, userdata, mid):
    """Callback for when a message is published"""
    logger.debug(f"📤 Message published, mid: {mid}")

def on_connect_local(client, userdata, flags, rc):
    """Callback for local MQTT broker connection"""
    if rc == 0:
        logger.info("✅ Connected to local MQTT broker!")
        logger.info("Subscribing to Shelly plug topics:")
        
        for machine_id, config in MACHINES.items():
            shelly_topic = config["shelly_topic"]
            client.subscribe(shelly_topic, qos=1)
            logger.info(f"  - {shelly_topic}")
    else:
        logger.error(f"❌ Failed to connect to local broker, return code {rc}")

def on_message_local(client, userdata, msg):
    """Callback for messages from local MQTT broker (Shelly plugs)"""
    try:
        for machine_id, config in MACHINES.items():
            if msg.topic == config["shelly_topic"]:
                monitor = monitor_manager.get_monitor(machine_id)
                if monitor:
                    data = json.loads(msg.payload.decode())
                    power = data.get("apower", 0.0)
                    monitor.update_power(power)
                    logger.debug(f"{monitor.name}: Power = {power}W")
                    state_changed, _ = monitor.check_transitions()
                    if state_changed:
                        logger.info(f"{monitor.name}: {monitor.state.value}")
                break
    except Exception as e:
        logger.error(f"Error processing local message: {e}")
        logger.debug(f"Topic: {msg.topic}, Payload: {msg.payload}")

def main():
    """Main function to start the MQTT clients"""
    global monitor_manager

    logger.info("=" * 70)
    logger.info(f"IoT Laundry Monitor - Monitoring {len(MACHINES)} machine(s)")
    for machine_id, config in MACHINES.items():
        logger.info(f"  - {config['name']} (ID: {machine_id})")
    logger.info("=" * 70)

    # Initialize monitor manager
    monitor_manager = MultiMachineMonitor(MACHINES)

    # Create MQTT client for LOCAL broker (Shelly plugs)
    local_client = mqtt.Client(client_id="raspi-washer-local")
    local_client.on_connect = on_connect_local
    local_client.on_message = on_message_local

    # Create MQTT client for AWS IoT Core (publishing data)
    aws_client = mqtt.Client(client_id="raspi-washer-aws")
    aws_client.on_connect = on_connect
    aws_client.on_disconnect = on_disconnect
    aws_client.on_message = on_message
    aws_client.on_publish = on_publish

    # Connect to LOCAL MQTT broker (for Shelly plugs)
    try:
        logger.info(f"🌐 Connecting to local MQTT broker: {LOCAL_MQTT_BROKER}:{LOCAL_MQTT_PORT}")
        local_client.connect(LOCAL_MQTT_BROKER, LOCAL_MQTT_PORT, keepalive=60)
        local_client.loop_start()
        logger.info("✅ Local broker connection initiated")
    except Exception as e:
        logger.error(f"❌ Failed to connect to local broker: {e}")
        return

    # Configure TLS for AWS IoT Core
    try:
        logger.info("🔧 Configuring TLS for AWS IoT Core...")
        aws_client.tls_set(
            ca_certs=CA_PATH,
            certfile=CERT_PATH,
            keyfile=KEY_PATH,
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS
        )
        aws_client.tls_insecure_set(False)
        logger.info("✅ TLS configured successfully")
    except Exception as e:
        logger.error(f"❌ Failed to configure TLS: {e}")
        return

    # Connect to AWS IoT Core
    try:
        logger.info(f"🌐 Connecting to AWS IoT Core: {AWS_IOT_BROKER}:{AWS_IOT_PORT}")
        aws_client.connect(AWS_IOT_BROKER, AWS_IOT_PORT, keepalive=60)
        aws_client.loop_start()
        logger.info("✅ AWS IoT Core connection initiated")
    except Exception as e:
        logger.error(f"❌ Failed to connect to AWS IoT Core: {e}")
        return

    # Main monitoring loop
    logger.info("\n🔄 Monitoring started (Press Ctrl+C to exit)\n")
    last_publish_time = time.time()

    try:
        while True:
            current_time = time.time()
            if current_time - last_publish_time >= PUBLISH_INTERVAL:
                publish_machine_data(aws_client)
                last_publish_time = current_time
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("\n⏹️  Shutting down gracefully...")
        monitor_manager.save_cycle_counts()
        local_client.loop_stop()
        local_client.disconnect()
        aws_client.loop_stop()
        aws_client.disconnect()
        logger.info("👋 Shutdown complete")

if __name__ == "__main__":
    main()
