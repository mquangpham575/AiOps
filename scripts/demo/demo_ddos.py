import argparse
import time
from demo_engine import BaseDemoRunner, _calc_increase_pct

# Scenario Configuration (Minimalist)
DDOS_SCENARIO_CFG = {
    "name": "Demo 3: DDoS & Throughput Benchmark",
    "phases": {
        "baseline": {"locust_tags": "baseline", "duration": 60},
        "load": {"locust_tags": "ddos", "duration": 120}
    }
}

def main():
    parser = argparse.ArgumentParser(description="AIOps Demo 3: DDoS Throughput Benchmark")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--baseline-dur", type=int, default=60)
    parser.add_argument("--load-dur", type=int, default=120)
    args = parser.parse_args()

    runner = BaseDemoRunner(iterations=args.iterations)
    runner._print_scenario_header(DDOS_SCENARIO_CFG["name"])
    
    for i in range(1, args.iterations + 1):
        print(f"\n[ITERATION {i}/{args.iterations}]")
        
        # 1. Stabilization Wait (10s)
        print(f"\n[STABILIZATION] Waiting 10s for system ready...")
        time.sleep(10)
        
        # 2. Load Phase
        l_res = runner.run_throughput_phase("LOAD (DDOS)", "ddos", args.load_dur)
        
        # 3. Report
        print(f"\n{'=' * 40}")
        print(f" DEMO 3 FINISHED")
        print(f"{'=' * 40}")
        print(f" Peak RPS:       {l_res['throughput_rps']}")
        print(f" Final CPU:      {l_res['cpu_pct']}%")
        print(f"{'=' * 40}")

if __name__ == "__main__":
    main()
