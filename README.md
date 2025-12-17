# IoT Raspberry Pi MQTT Broker

Raspberry Pi monitoring system for IoT laundry machines. Monitors washing machines via Shelly plugs and ESP32 hall sensors with **ML-powered phase detection**, then publishes aggregated data to AWS IoT Core.

## System Architecture

```
ESP32 (Hall Sensor) ──┐
                      ├──> Local MQTT Broker (localhost:1883) 
Shelly Plug (Power) ──┘         │
                                ├──> washing_machine_monitor_v3.py (aggregates + ML)
                                │         │
                                │         ├──> Random Forest Model (phase detection)
                                │         │
                                │         └──> AWS IoT Core (port 8883, TLS)
                                │                    │
                                │                    └──> EC2 Backend → PostgreSQL RDS
                                │
                      washing_machine_simulator.py (replays real power data)
```

## Components

### 1. washing_machine_monitor_v3.py (Production)
**Purpose**: Monitors real washing machines with ML-powered phase detection

**Features**:
- **ML Phase Detection**: Random Forest classifier identifies wash phases (WASHING, RINSE, SPIN, IDLE)
- **Dual State Tracking**: Rule-based state machine + ML predictions
- Dual MQTT clients (local broker + AWS IoT Core)
- State machine: `IDLE` → `RUNNING` → `OCCUPIED` → `IDLE`
- Power averaging over 30-second intervals
- Publishes every 30 seconds with ML confidence scores
- Cycle counting with persistent storage
- Graceful fallback if ML model unavailable

**Monitors**:
- **WM-01**: Real washing machine with Shelly plug and ESP32 hall sensor

**Data Flow**:
1. Subscribes to local broker for:
   - Shelly plug power data: `shellypluspluguk-3c8a1fec7d44/status/switch:0`
   - ESP32 hall sensor: `WM-01/hall_sensor/state`
2. Feeds power readings to ML model (18-sample rolling window)
3. Aggregates data over 30 seconds
4. Publishes to AWS IoT Core: `washer/WM-01/data` (includes `ml_phase` and `ml_confidence`)

**State Machine Logic**:
```
IDLE (door_is_open=true)
  └──> RUNNING (power > 9.6W for 1 second)
         └──> OCCUPIED (power < 6.4W)
                └──> IDLE (door open for 10 consecutive seconds)
```

**ML Model**:
- Algorithm: Random Forest (300 trees, depth 25)
- Features: 11 per sample × 18 window = 198 features
- Phases: WASHING, RINSE, SPIN, IDLE
- Training: 2459 samples from real washing machine data


## Prerequisites

- Raspberry Pi (any model with network connectivity)
- Python 3.12+
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
### 4. Setup ML Model Files
```bash
# Copy ML model and detector to Raspberry Pi
```

### 5. Configure Scripts

Edit `washing_machine_monitor_v3.py` if needed:
```python
# AWS IoT Core Configuration
AWS_IOT_BROKER = "your aws endpoint"
AWS_IOT_PORT = "Replace this"

CA_PATH = "Replace this"
CERT_PATH = "Replace this"
KEY_PATH = "Replace this"

# Local MQTT Broker
LOCAL_MQTT_BROKER = "Replace this"
LOCAL_MQTT_PORT = "Replace this"

# Machine Configuration
MACHINES = {
    "WM-01": {
        "name": "Washing Machine 1",
        "shelly_topic": "shellypluspluguk-3c8a1fec7d44/status/switch:0",
    }
}
## Running the Scripts

### Option 1: Direct Python (Testing)
```bash
# Main monitoring script
python3 washing_machine_monitor_v3.py
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

## Related Repositories

- **iot-laundry-server**: EC2 backend API server (Node.js)