#!/usr/bin/env python3
"""
Analyze historical power data to calculate typical phase durations
This provides the statistical baseline for time estimation
"""

import pandas as pd
import numpy as np
from datetime import datetime
import json

# Load and analyze the historical data
df = pd.read_csv('power_log_gus.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'])
df['time_seconds'] = (df['timestamp'] - df['timestamp'].iloc[0]).dt.total_seconds()

print("=" * 70)
print("PHASE DURATION ANALYSIS")
print("=" * 70)

# Apply simple rule-based phase labeling
def label_phase(power):
    if power < 15:
        return 'IDLE'
    elif power > 270:
        return 'SPIN'
    elif power > 180:
        return 'RINSE'
    else:
        return 'WASHING'

df['phase'] = df['power_w'].apply(label_phase)

# Calculate phase durations
phase_durations = []
current_phase = df['phase'].iloc[0]
phase_start_time = df['time_seconds'].iloc[0]

for i in range(1, len(df)):
    if df['phase'].iloc[i] != current_phase:
        # Phase changed
        duration = df['time_seconds'].iloc[i] - phase_start_time
        phase_durations.append({
            'phase': current_phase,
            'duration_seconds': duration,
            'duration_minutes': duration / 60
        })
        
        current_phase = df['phase'].iloc[i]
        phase_start_time = df['time_seconds'].iloc[i]

# Add the last phase
duration = df['time_seconds'].iloc[-1] - phase_start_time
phase_durations.append({
    'phase': current_phase,
    'duration_seconds': duration,
    'duration_minutes': duration / 60
})

# Convert to DataFrame for analysis
durations_df = pd.DataFrame(phase_durations)

# Calculate statistics for each phase
print("\nPHASE DURATION STATISTICS (minutes):")
print("-" * 70)

phase_stats = {}
for phase in ['IDLE', 'WASHING', 'RINSE', 'SPIN']:
    phase_data = durations_df[durations_df['phase'] == phase]['duration_minutes']
    
    if len(phase_data) > 0:
        stats = {
            'count': len(phase_data),
            'mean': float(phase_data.mean()),
            'median': float(phase_data.median()),
            'std': float(phase_data.std()),
            'min': float(phase_data.min()),
            'max': float(phase_data.max()),
            'p25': float(phase_data.quantile(0.25)),
            'p75': float(phase_data.quantile(0.75))
        }
        phase_stats[phase] = stats
        
        print(f"\n{phase}:")
        print(f"  Count: {stats['count']}")
        print(f"  Mean: {stats['mean']:.1f} min")
        print(f"  Median: {stats['median']:.1f} min")
        print(f"  Std Dev: {stats['std']:.1f} min")
        print(f"  Range: {stats['min']:.1f} - {stats['max']:.1f} min")
        print(f"  25th-75th percentile: {stats['p25']:.1f} - {stats['p75']:.1f} min")

# Filter out very short phases (likely noise or transitions)
print("\n" + "=" * 70)
print("FILTERING OUT SHORT PHASES (< 1 minute)")
print("=" * 70)

filtered_durations = durations_df[durations_df['duration_minutes'] >= 1.0]

print("\nFILTERED PHASE DURATION STATISTICS (minutes):")
print("-" * 70)

filtered_stats = {}
for phase in ['IDLE', 'WASHING', 'RINSE', 'SPIN']:
    phase_data = filtered_durations[filtered_durations['phase'] == phase]['duration_minutes']
    
    if len(phase_data) > 0:
        stats = {
            'count': len(phase_data),
            'mean': float(phase_data.mean()),
            'median': float(phase_data.median()),
            'std': float(phase_data.std()),
            'min': float(phase_data.min()),
            'max': float(phase_data.max())
        }
        filtered_stats[phase] = stats
        
        print(f"\n{phase}:")
        print(f"  Count: {stats['count']}")
        print(f"  Mean: {stats['mean']:.1f} min")
        print(f"  Median: {stats['median']:.1f} min")

# Use filtered median as the baseline for time estimation
print("\n" + "=" * 70)
print("RECOMMENDED TIME ESTIMATES FOR MODEL")
print("=" * 70)

recommended_estimates = {}
for phase in ['WASHING', 'RINSE', 'SPIN']:
    if phase in filtered_stats and filtered_stats[phase]['count'] > 0:
        # Use median for robustness against outliers
        recommended_estimates[phase] = {
            'typical_duration_minutes': round(filtered_stats[phase]['median'], 1)
        }
        print(f"{phase}: {recommended_estimates[phase]['typical_duration_minutes']} minutes")

# Estimate total cycle time
total_cycle_time = sum([v['typical_duration_minutes'] for v in recommended_estimates.values()])
print(f"\nEstimated Total Cycle Time: {total_cycle_time:.1f} minutes")

# Save to JSON for use in the model
output = {
    'phase_durations': recommended_estimates,
    'total_cycle_time_minutes': round(total_cycle_time, 1),
    'analysis_date': datetime.now().isoformat(),
    'data_source': 'power_log_gus.csv',
    'sample_count': len(df)
}

with open('phase_duration_estimates.json', 'w') as f:
    json.dump(output, f, indent=2)

print(f"\n✅ Phase duration estimates saved to: phase_duration_estimates.json")
print("=" * 70)
