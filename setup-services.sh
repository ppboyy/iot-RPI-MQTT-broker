#!/bin/bash

# Setup script for washing machine services
# Run this on your Raspberry Pi as the user (not root)

echo "Setting up washing machine services..."

# Copy service files to systemd directory
sudo cp washing-machine-monitor.service /etc/systemd/system/
sudo cp washing-machine-simulator.service /etc/systemd/system/

# Reload systemd to recognize new services
sudo systemctl daemon-reload

# Enable services to start at boot
sudo systemctl enable washing-machine-monitor.service
sudo systemctl enable washing-machine-simulator.service

# Start services now
sudo systemctl start washing-machine-monitor.service
sudo systemctl start washing-machine-simulator.service

echo ""
echo "✅ Services installed and started!"
echo ""
echo "Check status with:"
echo "  sudo systemctl status washing-machine-monitor"
echo "  sudo systemctl status washing-machine-simulator"
echo ""
echo "View logs with:"
echo "  journalctl -u washing-machine-monitor -f"
echo "  journalctl -u washing-machine-simulator -f"
echo ""
echo "Stop services with:"
echo "  sudo systemctl stop washing-machine-monitor"
echo "  sudo systemctl stop washing-machine-simulator"
echo ""
echo "Restart services with:"
echo "  sudo systemctl restart washing-machine-monitor"
echo "  sudo systemctl restart washing-machine-simulator"
