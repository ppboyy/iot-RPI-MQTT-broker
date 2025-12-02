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

### 2. washing_machine_simulator.py (Testing)
**Purpose**: Replays real washing machine power data for testing

**Simulates**:
- **WM-02, WM-03, WM-04**: Uses actual power data from `power_log_gus.csv`

**Features**:
- Replays 46 minutes of real washing machine data
- Time offsets for each machine (WM-02: 0min, WM-03: 10min, WM-04: 20min)
- Realistic power patterns (WASHING: 200-220W, RINSE: 100-150W, SPIN: 300-700W)
- Publishes to AWS IoT Core every 10 seconds
- Cycles through data continuously
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
# For production monitor (with ML support)
pip3 install --break-system-packages paho-mqtt joblib scikit-learn numpy scipy

# For simulator
pip3 install --break-system-packages paho-mqtt pandas
```
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
### 4. Setup ML Model Files
```bash
# Copy ML model and detector to Raspberry Pi
cd /home/andrea/iot-broker
# Ensure these files exist:
# - phase_detector.py
# - random_forest_phase_classifier.pkl
```

### 5. Configure Scripts

Edit `washing_machine_monitor_v3.py` if needed:
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
## Running the Scripts

### Option 1: Direct Python (Testing)
```bash
# Main monitoring script
python3 washing_machine_monitor_v3.py

# Simulator (in another terminal)
python3 washing_machine_simulator.py
```

### Option 2: systemd Service (Production - Recommended)

**Quick Setup:**
```bash
cd /home/andrea/iot-broker
chmod +x setup-services.sh
./setup-services.sh
```

This will:
- Install both service files to `/etc/systemd/system/`
- Enable auto-start on boot
- Start services immediately

**Manual Setup:**

Service files are provided:
- `washing-machine-monitor.service` - Main monitor with ML
- `washing-machine-simulator.service` - Simulator

Copy to systemd:
```bash
sudo cp washing-machine-monitor.service /etc/systemd/system/
sudo cp washing-machine-simulator.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable washing-machine-monitor washing-machine-simulator
sudo systemctl start washing-machine-monitor washing-machine-simulator
```

**Service Management:**
```bash
# Check status
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
sudo systemctl status washing-machine-monitor
sudo systemctl status washing-machine-simulator

# View logs
journalctl -u washing-machine-monitor -f
journalctl -u washing-machine-simulator -f

# Restart services
sudo systemctl restart washing-machine-monitor
sudo systemctl restart washing-machine-simulator

# Stop services
sudo systemctl stop washing-machine-monitor
sudo systemctl stop washing-machine-simulator
```onitor hall sensor
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
## Data Format

### Published to AWS IoT Core
**Topic**: `washer/{MachineID}/data`

**Payload (v3 with ML)**:
```json
{
  "timestamp": "2025-12-02T12:00:00.000Z",
  "MachineID": "WM-01",
  "cycle_number": 5,
  "current": 250.5,
  "state": "RUNNING",
  "door_opened": false,
  "ml_phase": "WASHING",
  "ml_confidence": 0.87
}
```

**Rule-Based States**:
- `IDLE`: Machine available, door open
- `RUNNING`: Wash cycle in progress, power > 8W
- `OCCUPIED`: Cycle complete, clothes inside, door closed

**ML Phases**:
- `WASHING`: Main wash cycle (200-220W, predictable oscillations)
- `RINSE`: Rinse cycle (100-150W, irregular patterns)
- `SPIN`: Spin/drain cycle (300-700W, high power)
- `IDLE`: No activity (< 10W)

**ML Confidence**: 0.0 to 1.0 (predictions filtered at 0.0 confidence are ignored)
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

## File Structure

```
iot-RPI-MQTT-broker/
├── washing_machine_monitor_v3.py           # Production monitor with ML
├── washing_machine_simulator.py            # Simulator using real power data
├── phase_detector.py                       # ML inference module
├── random_forest_phase_classifier.pkl      # Trained ML model
├── machine_cycles.json                     # Persistent cycle counts
├── washing-machine-monitor.service         # systemd service file (monitor)
├── washing-machine-simulator.service       # systemd service file (simulator)
├── setup-services.sh                       # Automated service setup script
├── power_log_gus.csv                       # Real power data for simulator
├── power_log*.csv                          # Historical power data
├── washing_machine_monitor_v1.py           # Legacy version 1
├── washing_machine_monitor_v2.py           # Legacy version 2
├── MQTT_Power_log_test.py                  # Power logging test
└── README.md                               # This file
```
**Cycle Count Reset:**
- Cycle counts stored in `machine_cycles.json`
- Backup this file to preserve counts
- Format: `{"WM-01": 5, "WM-02": 3, ...}`

## Files Structure

```
## ML Model Training

The ML model is trained separately in the `iot-laundry-server/ml/` repository:

1. **Data Preparation**: `training/prepare_data.py` - Extracts features from power data
2. **Model Training**: `training/train_random_forest.py` - Trains Random Forest classifier
3. **Deployment**: Copy `random_forest_phase_classifier.pkl` and `phase_detector.py` to RPi

For model improvement details, see `iot-laundry-server/ml/WASHING_IMPROVEMENTS.md`

## Future Enhancements

- [ ] Retrain model with 5 new features for better WASHING detection
- [ ] Add more machines (WM-05, WM-06, etc.)
- [ ] Implement predictive maintenance based on power patterns
- [ ] Add temperature sensors
- [ ] Vibration monitoring for unbalanced loads
- [ ] Mobile push notifications for cycle completion
- [ ] Energy consumption analytics
- [ ] CNN model for improved phase classification   # Historical power data
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
