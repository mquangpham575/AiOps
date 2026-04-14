import pandas as pd
import glob
import sys
import os

def aggregate_scenario3(directory):
    """
    Aggregates Scenario 3 results comparing Attacker vs Legitimate users.
    Expects CSV files like: run_limit100_stats.csv
    """
    all_files = glob.glob(os.path.join(directory, "*_stats.csv"))
    
    configs = {}
    
    for file in all_files:
        # Extract config name from filename, e.g., 'limit100' or 'nolimit'
        config_name = os.path.basename(file).split('_')[1]
        
        df = pd.read_csv(file)
        
        # We need to distinguish between Legitimate and Attacker
        # In the locustfile, we used name="Legitimate: ..." and name="Attack: ..."
        
        legit_rows = df[df['Name'].str.contains('Legitimate', na=False)]
        attack_rows = df[df['Name'].str.contains('Attack', na=False)]
        aggregated = df[df['Name'] == 'Aggregated']
        
        if config_name not in configs:
            configs[config_name] = []
            
        configs[config_name].append({
            "Attacker RPS": attack_rows['Requests/s'].sum() if not attack_rows.empty else 0,
            "Legitimate p95": legit_rows['95%'].mean() if not legit_rows.empty else 0,
            "Error Rate": aggregated['Failures/s'].values[0] / aggregated['Requests/s'].values[0] * 100 if aggregated['Requests/s'].values[0] > 0 else 0,
            "Total RPS": aggregated['Requests/s'].values[0]
        })

    # Summary table
    print("| Config | Attacker RPS | Legitimate p95 | Error Rate | Attack Blocked % |")
    print("|--------|-------------|----------------|------------|-----------------|")
    
    # Baseline (no limit) for blocked % calculation
    baseline_rps = 0
    if 'nolimit' in configs:
        baseline_rps = pd.DataFrame(configs['nolimit'])['Attacker RPS'].mean()

    for config, runs in configs.items():
        df_config = pd.DataFrame(runs)
        avg_atk = df_config['Attacker RPS'].mean()
        avg_p95 = df_config['Legitimate p95'].mean()
        avg_err = df_config['Error Rate'].mean()
        
        blocked_pct = 0
        if baseline_rps > 0 and config != 'nolimit':
            blocked_pct = (1 - (avg_atk / baseline_rps)) * 100
            
        print(f"| {config} | {avg_atk:.1f} | {avg_p95:.1f}ms | {avg_err:.1f}% | {blocked_pct:.1f}% |")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python aggregate_scenario3.py <directory>")
    else:
        aggregate_scenario3(sys.argv[1])
