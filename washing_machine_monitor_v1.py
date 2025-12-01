#!/usr/bin/env python3
import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime
from enum import Enum
from collections import defaultdict

# Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883

# Machine Configuration
MACHINES = {
    "washing_machine_1": {
        "name": "Washing Machine 1",
        "shelly_topic": "shellypluspluguk-3c8a1fec7d44/status/switch:0",
        "current_threshold": 8.0  # Watts
    }
}

# Constants
DOOR_OPEN_DURATION = 10  # seconds
CYCLE_COUNT_FILE = "machine_cycles.json"
PUBLISH_INTERVAL = 60 

class MachineState(Enum):
    AVAILABLE = "available"
    RUNNING = "running"
    OCCUPIED = "occupied"

class MachineMonitor:
    """Monitors a single machine's state and aggregates power readings for averaging."""
    
    def __init__(self, machine_id, config):
        self.machine_id = machine_id
        self.name = config["name"]
        self.current_threshold = config["current_threshold"]
        
        self.state = MachineState.AVAILABLE
        self.current_power = 0.0
        
        # Power averaging fields
        self.power_readings_sum = 0.0
        self.power_readings_count = 0
        
        self.door_is_open = False
        self.door_open_start_time = None
        self.cycle_count = 0
        self.last_state_change = datetime.now()
        
    def update_power(self, power):
        if power is not None:
            self.power_readings_sum += power
            self.power_readings_count += 1
        
    def calculate_and_reset_average(self):
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
        
        if self.state == MachineState.AVAILABLE:
            if self.current_power > self.current_threshold:
                new_state = MachineState.RUNNING
                self.door_open_start_time = None
                
        elif self.state == MachineState.RUNNING:
            if self.current_power <= self.current_threshold:
                new_state = MachineState.OCCUPIED
                
        elif self.state == MachineState.OCCUPIED:
            if self.door_is_open:
                if self.door_open_start_time is None:
                    self.door_open_start_time = time.time()
                elif time.time() - self.door_open_start_time >= DOOR_OPEN_DURATION:
                    new_state = MachineState.AVAILABLE
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
    Publish all machine data periodically. 
    The power value sent is the calculated average from the last interval.
    """
    timestamp = datetime.now().isoformat()
    
    for machine_id, monitor in monitor_manager.monitors.items():
        average_power = monitor.calculate_and_reset_average()
        # Format: [timestamp, MachineID, cycle_number, current, state]
        data_row = [
            timestamp,
            machine_id,
            monitor.cycle_count,
            round(average_power, 2),  # Use the calculated average here
            monitor.state.value
        ]
        
        # Publish as JSON array
        topic = f"{machine_id}/data"
        payload = json.dumps(data_row)
        client.publish(topic, payload, retain=False)
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Published (Avg): {data_row}")

def on_connect(client, userdata, flags, rc):
    """Callback for when the client connects to the broker"""
    if rc == 0:
        print("Connected to MQTT Broker!")
        print("\nSubscribing to topics:")
        
        # Subscribe to all hall sensors
        for machine_id in MACHINES.keys():
            hall_topic = f"{machine_id}/hall_sensor/state"
            client.subscribe(hall_topic)
            print(f"  - {hall_topic}")
        
        # Subscribe to all Shelly plugs
        for machine_id, config in MACHINES.items():
            shelly_topic = config["shelly_topic"]
            client.subscribe(shelly_topic)
            print(f"  - {shelly_topic}")
        
        print(f"\nData will be published every {PUBLISH_INTERVAL} seconds")
        
    else:
        print(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    """Callback for when a message is received"""
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
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {monitor.name}: {monitor.state.value}")
                    
                if cycle_completed:
                    monitor_manager.save_cycle_counts()
                    print(f"Cycle completed; Total cycles: {monitor.cycle_count}")
        
        # If not hall sensor then is plug
        else:
            # Find which machine this Shelly belongs to
            for machine_id, config in MACHINES.items():
                if msg.topic == config["shelly_topic"]:
                    monitor = monitor_manager.get_monitor(machine_id)
                    if monitor:
                        data = json.loads(msg.payload.decode())
                        power = data.get("apower", 0.0)
                        monitor.update_power(power)
                        state_changed, _ = monitor.check_transitions()
                        if state_changed:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] {monitor.name}: {monitor.state.value}")
                    break
            
    except Exception as e:
        print(f"Error processing message: {e}")
        print(f"Topic: {msg.topic}, Payload: {msg.payload}")

def main():
    """Main function to start the MQTT client"""
    global monitor_manager
    
    print("=" * 70)
    print(f"Monitoring {len(MACHINES)} machines:")
    for machine_id, config in MACHINES.items():
        print(f"  - {config['name']} (ID: {machine_id})")
    print("=" * 70)
    
    # Initialize monitor manager
    monitor_manager = MultiMachineMonitor(MACHINES)
    
    # Create MQTT client
    client = mqtt.Client(client_id="multi_machine_monitor")
    client.on_connect = on_connect
    client.on_message = on_message
    
    # Connect to broker
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
    except Exception as e:
        print(f"Failed to connect to MQTT broker: {e}")
        return
    
    # Start non-blocking loop
    client.loop_start()
    
    # Start the loop with periodic checks and publishing
    print("\nMonitoring... (Press Ctrl+C to exit)\n")
    last_publish_time = time.time()
    
    try:
        while True:
            # Check if it's time to publish data
            current_time = time.time()
            if current_time - last_publish_time >= PUBLISH_INTERVAL:
                publish_machine_data(client)
                last_publish_time = current_time
            time.sleep(1)  # Check every second
    except KeyboardInterrupt:
        print("\nShutting down...")
        monitor_manager.save_cycle_counts()
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
