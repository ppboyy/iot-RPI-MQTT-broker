#!/usr/bin/env python3
"""
Washing Machine Simulator - Simulates multiple washing machines for testing
Publishes fake hall sensor and Shelly plug data to local MQTT broker
The data is then picked up by washing_machine_monitor_v2.py and forwarded to AWS IoT Core
"""
import paho.mqtt.client as mqtt
import json
import time
import random
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---- Local MQTT Broker Configuration ----
MQTT_BROKER = "localhost"
MQTT_PORT = 1883

# ---- Simulated Machines Configuration ----
SIMULATED_MACHINES = {
    "WM-02": {"name": "Washing Machine 2"},
    "WM-03": {"name": "Washing Machine 3"},
    "WM-04": {"name": "Washing Machine 4"},
}

# Update frequency in seconds
SENSOR_UPDATE_INTERVAL = 30  # How often to publish sensor data

class SimulatedMachine:
    """Generates random realistic power and door data with state-based rules"""
    
    def __init__(self, machine_id, name):
        self.machine_id = machine_id
        self.name = name
        self.current_power = random.uniform(6, 8)  # Start at idle
        self.previous_power = self.current_power
        self.was_washing = False  # Track if machine was recently washing
        self.just_finished = False  # Track if machine just finished a cycle
    
    def get_shelly_data(self):
        """Generate random Shelly plug data with realistic power patterns"""
        # Store previous power to detect transitions
        self.previous_power = self.current_power
        
        # Random power based on typical washing machine cycle
        self.current_power = random.choice([
            random.uniform(6, 8),      # Standby/Idle
            random.uniform(20, 100),   # Washing/Filling
            random.uniform(100, 250),  # Heating/Agitation
            random.uniform(300, 380),  # Spinning
        ])
        
        # Detect state transitions
        if self.current_power > 20:
            self.was_washing = True
            self.just_finished = False
        elif self.current_power <= 8 and self.was_washing:
            # Transition from washing to idle - machine just finished
            self.just_finished = True
            self.was_washing = False
        
        return {
            "id": 0,
            "source": "init",
            "output": self.current_power > 5,
            "apower": round(self.current_power, 2),
            "voltage": round(random.uniform(230, 240), 1),
            "current": round(self.current_power / 230, 3),
            "aenergy": {
                "total": round(random.uniform(1000, 2000), 2),
                "by_minute": [0.0, 0.0, 0.0]
            },
            "temperature": {
                "tC": round(random.uniform(20, 35), 1),
                "tF": round(random.uniform(68, 95), 1)
            }
        }
    
    def get_hall_sensor_state(self):
        """Generate door state based on power consumption rules:
        1. Idle (6-8W, never washed): Door is open
        2. Washing (>20W): Door is always closed
        3. Just finished (6-8W after being >20W): 80% chance closed, 20% chance open
        """
        if self.current_power > 20:
            # Washing phase - door always closed
            return "closed"
        elif self.current_power <= 8 and self.just_finished:
            # Just finished washing - 80% chance door still closed, 20% chance opened
            if random.random() < 0.8:
                return "closed"
            else:
                # User opened the door to collect laundry
                self.just_finished = False  # Reset state after door is opened
                return "open"
        else:
            # Idle/waiting to start - door is open
            return "open"

def on_connect(client, userdata, flags, rc):
    """Callback for when the client connects to local MQTT broker"""
    if rc == 0:
        logger.info("✅ Simulator connected to local MQTT broker!")
    else:
        logger.error(f"❌ Failed to connect, return code {rc}")

def on_disconnect(client, userdata, rc):
    """Callback for when the client disconnects"""
    if rc != 0:
        logger.warning(f"⚠️ Unexpected disconnect, attempting reconnect...")
        try:
            client.reconnect()
        except Exception as e:
            logger.error(f"Reconnect failed: {e}")

def on_publish(client, userdata, mid):
    """Callback for when a message is published"""
    logger.debug(f"📤 Published message, mid: {mid}")

def publish_sensor_data(client, machines):
    """Publish simulated sensor data for all machines"""
    for machine_id, machine in machines.items():
        # Publish Shelly plug data (power consumption)
        shelly_topic = f"simulator/{machine_id}/shelly"
        shelly_data = machine.get_shelly_data()
        client.publish(shelly_topic, json.dumps(shelly_data), qos=1)
        
        # Publish hall sensor data (door state)
        hall_topic = f"{machine_id}/hall_sensor/state"
        hall_state = machine.get_hall_sensor_state()
        client.publish(hall_topic, hall_state, qos=1)
        
        logger.info(f"{machine.name}: Power={shelly_data['apower']}W, Door={hall_state}")

def main():
    """Main simulator function"""
    logger.info("=" * 70)
    logger.info(f"Washing Machine Simulator - Simulating {len(SIMULATED_MACHINES)} machines")
    
    # Initialize simulated machines
    machines = {
        machine_id: SimulatedMachine(machine_id, config["name"])
        for machine_id, config in SIMULATED_MACHINES.items()
    }
    
    for machine_id, machine in machines.items():
        logger.info(f"  - {machine.name} (ID: {machine_id})")
    logger.info("=" * 70)
    
    # Create MQTT client
    client = mqtt.Client(client_id="washing-machine-simulator")
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_publish = on_publish
    
    # Connect to local MQTT broker
    try:
        logger.info(f"🌐 Connecting to local MQTT broker: {MQTT_BROKER}:{MQTT_PORT}")
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        logger.info("✅ Connection initiated")
    except Exception as e:
        logger.error(f"❌ Failed to connect to local MQTT broker: {e}")
        return
    
    # Start network loop
    client.loop_start()
    
    # Give connection time to establish
    time.sleep(2)
    
    # Main simulation loop
    logger.info("\n🔄 Simulation started (Press Ctrl+C to exit)\n")
    
    try:
        while True:
            # Publish sensor data every interval
            publish_sensor_data(client, machines)
            time.sleep(SENSOR_UPDATE_INTERVAL)
            
    except KeyboardInterrupt:
        logger.info("\n⏹️  Shutting down simulator...")
        client.loop_stop()
        client.disconnect()
        logger.info("👋 Simulator stopped")

if __name__ == "__main__":
    main()
