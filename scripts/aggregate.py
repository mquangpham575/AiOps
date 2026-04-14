import pandas as pd
import glob
import sys
import os

def aggregate_results(directory):
    """Aggregates Locust CSV stats and prints a comparison table."""
    all_stats_files = glob.glob(os.path.join(directory, "*_stats.csv"))
    
    if not all_stats_files:
        print(f"No results found in {directory}")
        return

    phase_data = {"Phase A": [], "Phase B": []}
    
    for file in all_stats_files:
        df = pd.read_csv(file)
        # Select the 'Aggregated' row if it exists, otherwise use total
        summary = df[df['Name'] == 'Aggregated']
        if summary.empty:
            continue
            
        phase = "Phase A" if "phase_a" in file else "Phase B"
        
        phase_data[phase].append({
            "p50": summary['50%'].values[0],
            "p95": summary['95%'].values[0],
            "p99": summary['99%'].values[0],
            "Requests/s": summary['Requests/s'].values[0],
            "Failures/s": summary['Failures/s'].values[0]
        })

    # Calculate means
    comparison = {}
    for phase, metrics in phase_data.items():
        if not metrics:
            continue
        df_phase = pd.DataFrame(metrics)
        comparison[phase] = df_phase.mean()

    # Print markdown table
    if not comparison:
        print("Could not aggregate enough data.")
        return

    print("| Metric | Phase A (Baseline) | Phase B (Load) |")
    print("|--------|-------------------|----------------|")
    for metric in ["p50", "p95", "p99", "Requests/s", "Failures/s"]:
        val_a = f"{comparison['Phase A'][metric]:.2f}" if "Phase A" in comparison else "N/A"
        val_b = f"{comparison['Phase B'][metric]:.2f}" if "Phase B" in comparison else "N/A"
        print(f"| {metric} | {val_a} | {val_b} |")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python aggregate.py <directory>")
    else:
        aggregate_results(sys.argv[1])
