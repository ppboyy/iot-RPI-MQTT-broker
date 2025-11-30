# IoT Raspberry Pi MQTT Broker

Raspberry Pi monitoring scripts for IoT laundry system. Monitors washing machines via Shelly plugs and ESP32 hall sensors, then publishes aggregated data to AWS IoT Core.

## System Architecture

```
ESP32 (Hall Sensor) ──┐
                      ├──> Local MQTT Broker (localhost:1883) 
Shelly Plug (Power) ──┘         │
                                ├──> washing_machine_monitor_v2.py (aggregates data)
                                │         │
                                │         └──> AWS IoT Core (port 8883, TLS)
                                │                    │
                                │                    └──> EC2 Backend → PostgreSQL RDS
                                │
                      washing_machine_simulator.py (for testing 3 additional machines)
```

## Components

### 1. washing_machine_monitor_v2.py (Main Script)
**Purpose**: Monitors real washing machines and publishes to AWS IoT Core

**Features**:
- Dual MQTT clients (local broker + AWS IoT Core)
- State machine: `IDLE` → `RUNNING` → `OCCUPIED` → `IDLE`
- Power averaging over 30-second intervals
- Publishes every 30 seconds
- State transitions checked every 1 second
- Cycle counting with persistent storage

**Monitors**:
- **WM-01**: Real washing machine with Shelly plug and ESP32 hall sensor

**Data Flow**:
1. Subscribes to local broker for:
   - Shelly plug power data: `shellypluspluguk-3c8a1fec7d44/status/switch:0`
   - ESP32 hall sensor: `WM-01/hall_sensor/state`
2. Aggregates data over 30 seconds
3. Publishes to AWS IoT Core: `washer/WM-01/data`

**State Machine Logic**:
```
IDLE (door_is_open=true)
  └──> RUNNING (power > 9.6W for 1 second)
         └──> OCCUPIED (power < 6.4W)
                └──> IDLE (door open for 10 consecutive seconds)
```

### 2. washing_machine_simulator.py (Testing)
**Purpose**: Simulates 3 additional washing machines for testing

**Simulates**:
- **WM-02, WM-03, WM-04**: Fake machines with realistic behavior

**Features**:
- Realistic power consumption patterns (idle: 0-2W, running: 100-700W)
- Random cycle durations (3-5 minutes)
- Automatic door opening after cycle completion
- Publishes to AWS IoT Core every 30 seconds

**Topics**:
- Power: `simulator/WM-02/shelly`, `simulator/WM-03/shelly`, `simulator/WM-04/shelly`
- Door: `WM-02/hall_sensor/state`, `WM-03/hall_sensor/state`, `WM-04/hall_sensor/state`

### 3. Legacy Scripts (Reference Only)
- `washing_machine_monitor.py`: Original single-machine version
- `MQTT_Power_log.py`: Power logging script
- `aws_mqtt_test.py`: AWS IoT Core connection test

## Prerequisites

- Raspberry Pi (any model with network connectivity)
- Python 3.7+
- Local MQTT broker (Mosquitto)
- AWS IoT Core credentials and certificates
- Shelly Plus Plug UK for power monitoring
- ESP32 with hall sensor for door detection

## Installation

### 1. Install System Dependencies
```bash
sudo apt-get update
sudo apt-get install -y python3-pip mosquitto mosquitto-clients
```

### 2. Install Python Dependencies
```bash
pip3 install paho-mqtt
```

### 3. Setup AWS IoT Core Certificates
```bash
mkdir -p ~/aws-iot/certs
cd ~/aws-iot/certs

# Copy your AWS IoT Core certificates here:
# - AmazonRootCA1.pem
# - device.pem.crt
# - private.pem.key

chmod 644 AmazonRootCA1.pem
chmod 644 device.pem.crt
chmod 600 private.pem.key
```

### 4. Configure Scripts

Edit `washing_machine_monitor_v2.py`:
```python
# AWS IoT Core Configuration
AWS_IOT_BROKER = "a5916n61elm51-ats.iot.ap-southeast-1.amazonaws.com"
AWS_IOT_PORT = 8883

CA_PATH = "/home/andrea/aws-iot/certs/AmazonRootCA1.pem"
CERT_PATH = "/home/andrea/aws-iot/certs/device.pem.crt"
KEY_PATH = "/home/andrea/aws-iot/certs/private.pem.key"

# Local MQTT Broker
LOCAL_MQTT_BROKER = "localhost"
LOCAL_MQTT_PORT = 1883

# Machine Configuration
MACHINES = {
    "WM-01": {
        "name": "Washing Machine 1",
        "shelly_topic": "shellypluspluguk-3c8a1fec7d44/status/switch:0",
        "current_threshold": 8.0  # Watts
    }
}
```

## Running the Scripts

### Option 1: Direct Python (Testing)
```bash
# Main monitoring script
python3 washing_machine_monitor_v2.py

# Simulator (in another terminal)
python3 washing_machine_simulator.py
```

### Option 2: systemd Service (Production)

Create service file for main monitor:
```bash
sudo nano /etc/systemd/system/washing-machine-monitor.service
```

```ini
[Unit]
Description=Washing Machine Monitor
After=network.target mosquitto.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/iot-RPI-MQTT-broker
ExecStart=/usr/bin/python3 /home/pi/iot-RPI-MQTT-broker/washing_machine_monitor_v2.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Create service file for simulator:
```bash
sudo nano /etc/systemd/system/washing-machine-simulator.service
```

```ini
[Unit]
Description=Washing Machine Simulator
After=network.target mosquitto.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/iot-RPI-MQTT-broker
ExecStart=/usr/bin/python3 /home/pi/iot-RPI-MQTT-broker/washing_machine_simulator.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start services:
```bash
sudo systemctl daemon-reload
sudo systemctl enable washing-machine-monitor
sudo systemctl enable washing-machine-simulator
sudo systemctl start washing-machine-monitor
sudo systemctl start washing-machine-simulator

# Check status
sudo systemctl status washing-machine-monitor
sudo systemctl status washing-machine-simulator

# View logs
sudo journalctl -u washing-machine-monitor -f
sudo journalctl -u washing-machine-simulator -f
```

## Manual Testing

### Test Door Sensor
```bash
# Close door
mosquitto_pub -h localhost -t "WM-01/hall_sensor/state" -m "closed"

# Open door
mosquitto_pub -h localhost -t "WM-01/hall_sensor/state" -m "open"
```

Accepted values: `"open"`, `"closed"`, `"true"`, `"false"`, `"1"`, `"0"`

### Monitor Local MQTT Traffic
```bash
# Monitor all topics
mosquitto_sub -h localhost -t '#' -v

# Monitor Shelly plug
mosquitto_sub -h localhost -t 'shellypluspluguk-3c8a1fec7d44/status/switch:0'

# Monitor hall sensor
mosquitto_sub -h localhost -t 'WM-01/hall_sensor/state'
```

## Data Format

### Published to AWS IoT Core
**Topic**: `washer/{MachineID}/data`

**Payload**:
```json
{
  "timestamp": "2025-11-30T12:00:00.000Z",
  "MachineID": "WM-01",
  "cycle_number": 5,
  "current": 250.5,
  "state": "RUNNING",
  "door_opened": false
}
```

**States**:
- `IDLE`: Machine available, door open
- `RUNNING`: Wash cycle in progress, power > 8W
- `OCCUPIED`: Cycle complete, clothes inside, door closed

## Configuration

### Power Threshold
```python
"current_threshold": 8.0  # Watts
```
- Power > threshold * 1.2 (9.6W) → Transition to RUNNING
- Power < threshold * 0.8 (6.4W) → Transition to OCCUPIED

### Publish Interval
```python
PUBLISH_INTERVAL = 30  # seconds
```

### Door Open Duration
```python
DOOR_OPEN_DURATION = 10  # seconds
```
Door must remain open for 10 consecutive seconds to return to IDLE.

### Cycle Persistence
Cycle counts are saved to `machine_cycles.json` and persist across restarts.

## Hardware Setup

### Shelly Plus Plug UK
1. Connect to your WiFi network
2. Configure MQTT settings:
   - Server: `192.168.x.x` (Raspberry Pi IP)
   - Port: `1883`
   - Topic: `shellypluspluguk-<deviceid>/status/switch:0`

### ESP32 Hall Sensor
1. Flash ESP32 with MQTT client code
2. Configure:
   - MQTT Broker: Raspberry Pi IP
   - Port: `1883`
   - Topic: `WM-01/hall_sensor/state`
   - Payload: `"open"` or `"closed"`

## Troubleshooting

**Script Won't Start:**
```bash
# Check Python version
python3 --version  # Should be 3.7+

# Check dependencies
pip3 list | grep paho-mqtt

# Test local broker
mosquitto_pub -h localhost -t "test" -m "hello"
mosquitto_sub -h localhost -t "test"
```

**No Data to AWS IoT Core:**
```bash
# Test AWS IoT connection
python3 aws_mqtt_test.py

# Check certificates
ls -la ~/aws-iot/certs/

# Verify certificate permissions
# AmazonRootCA1.pem and device.pem.crt should be 644
# private.pem.key should be 600
```

**State Not Transitioning:**
- Check power threshold in configuration
- Monitor power values: `mosquitto_sub -h localhost -t 'shellypluspluguk-+/status/switch:0'`
- Door sensor must send boolean values (`"open"`, `"closed"`, `"true"`, `"false"`, `"1"`, `"0"`)

**Cycle Count Reset:**
- Cycle counts stored in `machine_cycles.json`
- Backup this file to preserve counts
- Format: `{"WM-01": 5, "WM-02": 3, ...}`

## Files Structure

```
iot-RPI-MQTT-broker/
├── washing_machine_monitor_v2.py   # Main monitoring script
├── washing_machine_simulator.py    # Test simulator for 3 machines
├── machine_cycles.json              # Persistent cycle counts
├── aws_mqtt_test.py                 # AWS IoT connection test
├── washing_machine_monitor.py       # Legacy single-machine version
├── MQTT_Power_log.py                # Power logging utility
├── power_log*.csv                   # Historical power data
└── README.md                        # This file
```

## Related Repositories

- **iot-laundry-server**: EC2 backend API server (Node.js)
- **iot-laundry-frontend**: Vercel dashboard (https://www.iotwasher.com)

## Future Enhancements

- [ ] Add more machines (WM-05, WM-06, etc.)
- [ ] Implement predictive maintenance based on power patterns
- [ ] Add temperature sensors
- [ ] Vibration monitoring for unbalanced loads
- [ ] Mobile push notifications for cycle completion
- [ ] Energy consumption analytics

## License

ISC
