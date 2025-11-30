#!/usr/bin/env python3
"""
Washing Machine Simulator - Simulates multiple washing machines for testing
Publishes fake hall sensor and Shelly plug data to AWS IoT Core
"""
import paho.mqtt.client as mqtt
import ssl
import json
import time
import random
import logging
from datetime import datetime
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---- AWS IoT Core Configuration ----
MQTT_BROKER = "a5916n61elm51-ats.iot.ap-southeast-1.amazonaws.com"
MQTT_PORT = 8883

CA_PATH = "/home/andrea/aws-iot/certs/AmazonRootCA1.pem"
CERT_PATH = "/home/andrea/aws-iot/certs/device.pem.crt"
KEY_PATH = "/home/andrea/aws-iot/certs/private.pem.key"

# ---- Simulated Machines Configuration ----
SIMULATED_MACHINES = {
    "WM-02": {"name": "Washing Machine 2"},
    "WM-03": {"name": "Washing Machine 3"},
    "WM-04": {"name": "Washing Machine 4"},
}

# Update frequency in seconds
SENSOR_UPDATE_INTERVAL = 30  # How often to publish sensor data

class SimulatedMachineState(Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    OCCUPIED = "OCCUPIED"

class SimulatedMachine:
    """Simulates a washing machine with realistic behavior"""
    
    def __init__(self, machine_id, name):
        self.machine_id = machine_id
        self.name = name
        self.state = SimulatedMachineState.IDLE
        self.door_open = False
        self.power = 0.0
        self.cycle_start_time = None
        self.cycle_duration = 0
        self.time_in_state = 0
        
    def update(self, delta_time):
        """Update machine state based on realistic patterns"""
        self.time_in_state += delta_time
        
        if self.state == SimulatedMachineState.IDLE:
            # 10% chance per update to start a cycle
            if random.random() < 0.02:
                self._start_cycle()
            else:
                self.power = random.uniform(0, 2)  # Standby power
                self.door_open = random.choice([True, False])
        
        elif self.state == SimulatedMachineState.RUNNING:
            # Simulate washing cycle power patterns
            progress = self.time_in_state / self.cycle_duration
            
            if progress < 0.2:  # Initial fill/agitate
                self.power = random.uniform(300, 500)
            elif progress < 0.5:  # Main wash
                self.power = random.uniform(150, 300)
            elif progress < 0.7:  # Spin cycle
                self.power = random.uniform(400, 600)
            elif progress < 0.9:  # Rinse
                self.power = random.uniform(100, 250)
            else:  # Final spin
                self.power = random.uniform(500, 700)
            
            # Add some noise
            self.power += random.uniform(-20, 20)
            self.door_open = False  # Door locked during cycle
            
            # Check if cycle complete
            if self.time_in_state >= self.cycle_duration:
                self._complete_cycle()
        
        elif self.state == SimulatedMachineState.OCCUPIED:
            self.power = random.uniform(0, 3)  # Very low power
            
            # Simulate someone opening door after some time
            if self.time_in_state > random.uniform(30, 120):  # 30-120 seconds
                self.door_open = True
                
                # If door open for >10 seconds, return to idle
                if self.time_in_state > random.uniform(40, 130):
                    self._return_to_idle()
    
    def _start_cycle(self):
        """Start a washing cycle"""
        self.state = SimulatedMachineState.RUNNING
        self.cycle_duration = random.uniform(180, 300)  # 3-5 minutes for testing
        self.time_in_state = 0
        self.door_open = False
        logger.info(f"🟢 {self.name} starting cycle (duration: {self.cycle_duration:.0f}s)")
    
    def _complete_cycle(self):
        """Complete washing cycle"""
        self.state = SimulatedMachineState.OCCUPIED
        self.time_in_state = 0
        logger.info(f"✅ {self.name} cycle complete, now OCCUPIED")
    
    def _return_to_idle(self):
        """Return to idle state"""
        self.state = SimulatedMachineState.IDLE
        self.time_in_state = 0
        self.door_open = False
        logger.info(f"🔵 {self.name} returned to IDLE")
    
    def get_shelly_data(self):
        """Generate Shelly plug data format"""
        return {
            "id": 0,
            "source": "init",
            "output": self.power > 5,
            "apower": round(self.power, 2),
            "voltage": round(random.uniform(230, 240), 1),
            "current": round(self.power / 230, 3),
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
        """Generate hall sensor data (0=closed, 1=open)"""
        return 1 if self.door_open else 0

def on_connect(client, userdata, flags, rc):
    """Callback for when the client connects to AWS IoT Core"""
    if rc == 0:
        logger.info("✅ Simulator connected to AWS IoT Core!")
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
        client.publish(hall_topic, str(hall_state), qos=1)
        
        logger.info(f"{machine.name}: State={machine.state.value}, Power={machine.power:.1f}W, Door={'OPEN' if machine.door_open else 'CLOSED'}")

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
    
    # Configure TLS for AWS IoT Core
    try:
        logger.info("🔧 Configuring TLS for AWS IoT Core...")
        client.tls_set(
            ca_certs=CA_PATH,
            certfile=CERT_PATH,
            keyfile=KEY_PATH,
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS
        )
        client.tls_insecure_set(False)
        logger.info("✅ TLS configured successfully")
    except Exception as e:
        logger.error(f"❌ Failed to configure TLS: {e}")
        return
    
    # Connect to AWS IoT Core
    try:
        logger.info(f"🌐 Connecting to AWS IoT Core: {MQTT_BROKER}:{MQTT_PORT}")
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        logger.info("✅ Connection initiated")
    except Exception as e:
        logger.error(f"❌ Failed to connect to AWS IoT Core: {e}")
        return
    
    # Start network loop
    client.loop_start()
    
    # Give connection time to establish
    time.sleep(2)
    
    # Main simulation loop
    logger.info("\n🔄 Simulation started (Press Ctrl+C to exit)\n")
    last_update = time.time()
    
    try:
        while True:
            current_time = time.time()
            delta_time = current_time - last_update
            
            # Update all machines
            for machine in machines.values():
                machine.update(delta_time)
            
            # Publish sensor data
            if delta_time >= SENSOR_UPDATE_INTERVAL:
                publish_sensor_data(client, machines)
                last_update = current_time
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("\n⏹️  Shutting down simulator...")
        client.loop_stop()
        client.disconnect()
        logger.info("👋 Simulator stopped")

if __name__ == "__main__":
    main()
