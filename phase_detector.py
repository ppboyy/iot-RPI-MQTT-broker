#!/usr/bin/env python3
"""
ML Phase Detector for Washing Machine Monitoring
Uses trained Random Forest model to predict washing machine phases
"""

import joblib
import numpy as np
from collections import deque
from scipy.signal import savgol_filter

class MLPhaseDetector:
    def __init__(self, model_path='/home/andrea/iot-broker/random_forest_phase_classifier.pkl'):
        """Initialize ML phase detector"""
        print(f"Loading ML model from {model_path}...")
        self.model = joblib.load(model_path)
        print(f"✅ Model loaded successfully")
        
        # Buffers for feature extraction
        self.power_buffer = deque(maxlen=120)  # Store 2 hours of history
        self.window_size = 12  # Must match training window size (currently trained with 12)
        
    def add_power_reading(self, power):
        """Add new power reading"""
        self.power_buffer.append(power)
    
    def extract_features(self):
        """Extract features from power buffer (same as training)"""
        if len(self.power_buffer) < self.window_size:
            return None
        
        # Get recent power readings
        recent_power = list(self.power_buffer)[-self.window_size:]
        
        # Apply Savitzky-Golay smoothing
        if len(recent_power) >= 11:
            power_smooth = savgol_filter(recent_power, window_length=11, polyorder=3)
        else:
            power_smooth = np.array(recent_power)
        
        # Extract features for each sample in window
        features = []
        for i in range(len(recent_power)):
            # Rolling statistics
            window_data = power_smooth[max(0, i-3):i+1]
            
            # Basic features (11 features)
            feat = [
                power_smooth[i],                          # power_smooth
                np.mean(window_data[-2:]) if len(window_data) >= 2 else power_smooth[i],  # power_avg_30s
                np.mean(window_data),                     # power_avg_60s
                np.std(window_data[-2:]) if len(window_data) >= 2 else 0,  # power_std_30s
                np.std(window_data),                      # power_std_60s
                np.min(window_data[-2:]) if len(window_data) >= 2 else power_smooth[i],  # power_min_30s
                np.max(window_data[-2:]) if len(window_data) >= 2 else power_smooth[i],  # power_max_30s
                (np.max(window_data[-2:]) - np.min(window_data[-2:])) if len(window_data) >= 2 else 0,  # power_range_30s
                np.gradient(power_smooth)[i] if i > 0 else 0,  # power_derivative
                len(window_data),                         # time_in_range
                (np.max(window_data) - np.min(window_data)) / (np.mean(window_data) + 1e-6) if len(window_data) > 1 else 0  # power_oscillation
            ]
            
            # NEW FEATURES for better WASHING detection (5 features)
            # Peak count
            if len(window_data) >= 3:
                peaks = sum((window_data[1:-1] > window_data[:-2]) & (window_data[1:-1] > window_data[2:]))
            else:
                peaks = 0
            
            # Regularity score
            if len(window_data) > 1:
                regularity = 1.0 / (1.0 + np.std(np.diff(window_data)))
            else:
                regularity = 0
            
            # High power ratio
            high_power_ratio = sum(window_data > 200) / len(window_data) if len(window_data) > 0 else 0
            
            # Power stability
            if len(window_data) > 1:
                stability = 1.0 - (np.std(np.diff(window_data)) / (np.mean(window_data) + 1e-6))
            else:
                stability = 0
            
            # Mean absolute deviation
            power_mad = np.mean(np.abs(window_data - np.mean(window_data))) if len(window_data) > 0 else 0
            
            feat.extend([peaks, regularity, high_power_ratio, stability, power_mad])
            
            features.extend(feat)
        
        return np.array(features).reshape(1, -1)
    
    def predict_phase(self):
        """Predict current washing machine phase"""
        features = self.extract_features()
        
        if features is None:
            return "IDLE", 0.0  # Not enough data yet
        
        try:
            # Predict phase
            phase = self.model.predict(features)[0]
            
            # Get confidence
            probabilities = self.model.predict_proba(features)[0]
            confidence = np.max(probabilities)
            
            return phase, confidence
            
        except Exception as e:
            print(f"Error during prediction: {e}")
            return "UNKNOWN", 0.0

# Test the detector
if __name__ == "__main__":
    detector = MLPhaseDetector()
    
    # Simulate some power readings
    print("\nTesting with simulated data...")
    
    # Idle
    for _ in range(15):
        detector.add_power_reading(6.0)
    phase, conf = detector.predict_phase()
    print(f"Phase: {phase}, Confidence: {conf:.2f}")
    
    # Washing
    for _ in range(20):
        detector.add_power_reading(np.random.uniform(100, 150))
    phase, conf = detector.predict_phase()
    print(f"Phase: {phase}, Confidence: {conf:.2f}")
    
    # Rinse spike
    for _ in range(10):
        detector.add_power_reading(np.random.uniform(250, 350))
    phase, conf = detector.predict_phase()
    print(f"Phase: {phase}, Confidence: {conf:.2f}")
    
    print("\n✅ Phase detector test complete!")
