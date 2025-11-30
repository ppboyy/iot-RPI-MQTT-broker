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
from datetime import datetime
from enum import Enum

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

class SimulatedMachineState(Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    OCCUPIED = "OCCUPIED"

class SimulatedMachine:
    """Simulates a washing machine with realistic behavior based on real power data"""
    
    def __init__(self, machine_id, name):
        self.machine_id = machine_id
        self.name = name
        self.state = SimulatedMachineState.IDLE
        self.door_open = True  # Start with door open in IDLE
        self.power = 0.0
        self.cycle_start_time = None
        self.cycle_duration = 2760  # ~46 minutes (based on real data)
        self.time_in_state = 0
        
    def update(self, delta_time):
        """Update machine state based on realistic patterns"""
        self.time_in_state += delta_time
        
        if self.state == SimulatedMachineState.IDLE:
            # Small chance to start a cycle (2% per update)
            if random.random() < 0.02:
                self._start_cycle()
            else:
                self.power = random.uniform(6.0, 7.0)  # Standby power from real data
                self.door_open = True
        
        elif self.state == SimulatedMachineState.RUNNING:
            # Use realistic power pattern based on actual washing machine data
            progress = self.time_in_state / self.cycle_duration
            
            if progress < 0.05:  # 0-2.3 min: Initial fill and start (6-82W)
                self.power = random.uniform(6, 35) + random.uniform(-5, 20)
                if random.random() < 0.1:  # Occasional spike
                    self.power = random.uniform(60, 85)
            
            elif progress < 0.15:  # 2.3-6.9 min: Heating and initial agitation (30-110W)
                base_power = 30 + (progress - 0.05) * 700
                self.power = base_power + random.uniform(-10, 20)
            
            elif progress < 0.30:  # 6.9-13.8 min: Main wash cycle (90-230W)
                base_power = random.uniform(90, 150)
                self.power = base_power + random.uniform(-15, 80)
                if random.random() < 0.15:  # Occasional high power moments
                    self.power = random.uniform(180, 230)
            
            elif progress < 0.50:  # 13.8-23 min: Continued washing (80-200W)
                base_power = random.uniform(80, 140)
                self.power = base_power + random.uniform(-20, 60)
            
            elif progress < 0.70:  # 23-32.2 min: Rinse cycles (30-180W)
                # Intermittent power with drain/fill cycles
                if random.random() < 0.3:
                    self.power = random.uniform(6, 10)  # Drain phase
                else:
                    self.power = random.uniform(30, 90) + random.uniform(-10, 90)
            
            elif progress < 0.95:  # 32.2-43.7 min: Final spin cycle (300-380W)
                base_power = 330 + random.uniform(-20, 40)
                self.power = base_power
                # Simulate spin fluctuations
                if random.random() < 0.2:
                    self.power = random.uniform(300, 380)
            
            else:  # 43.7-46 min: Final drain and cooldown (6-60W)
                if random.random() < 0.5:
                    self.power = random.uniform(20, 40)
                else:
                    self.power = random.uniform(6, 10)
            
            # Ensure power doesn't go negative
            self.power = max(6.0, self.power)
            self.door_open = False  # Door locked during cycle
            
            # Check if cycle complete
            if self.time_in_state >= self.cycle_duration:
                self._complete_cycle()
        
        elif self.state == SimulatedMachineState.OCCUPIED:
            self.power = random.uniform(6, 8)  # Standby power
            
            # Simulate someone opening door after some time
            if self.time_in_state > random.uniform(30, 120):  # 30-120 seconds
                self.door_open = True
                
                # If door open for >10 seconds, return to idle
                if self.time_in_state > random.uniform(40, 130):
                    self._return_to_idle()
    
    def _start_cycle(self):
        """Start a washing cycle"""
        self.state = SimulatedMachineState.RUNNING
        # Add some variation to cycle duration (±5%)
        self.cycle_duration = 2760 + random.uniform(-138, 138)  # ~44-48 minutes
        self.time_in_state = 0
        self.door_open = False
        logger.info(f"🟢 {self.name} starting cycle (duration: {self.cycle_duration/60:.1f} min)")
    
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
        """Generate hall sensor data (open/closed string format)"""
        return "open" if self.door_open else "closed"

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
