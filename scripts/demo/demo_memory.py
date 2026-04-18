import argparse
from demo_engine import BaseDemoRunner

# Scenario Configuration (Minimalist)
MEMORY_SCENARIO_CFG = {
    "name": "Demo 2: Memory Remediation Lifecycle",
    "alerts": ["ProactiveMemoryExhaustion", "HighMemoryUsage"],
    "agent_scenario": "demo_memory",
    "injection": {
        "method": "stress-ng",
        "container": "target-app",
        "command": "sudo docker exec -d target-app stress-ng --vm 1 --vm-bytes 512M --timeout {duration}s"
    }
}

def main():
    parser = argparse.ArgumentParser(description="AIOps Demo 2: Memory Leak Remediation")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--duration", type=int, default=120)
    args = parser.parse_args()

    runner = BaseDemoRunner(iterations=args.iterations, duration=args.duration)
    runner._print_scenario_header(MEMORY_SCENARIO_CFG["name"])
    
    for i in range(1, args.iterations + 1):
        print(f"\n[ITERATION {i}/{args.iterations}]")
        runner.run_remediation_cycle("demo_memory", MEMORY_SCENARIO_CFG, i)

if __name__ == "__main__":
    main()
