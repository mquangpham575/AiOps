import argparse
import sys
import os

# Add the 'demo' directory to the path so we can import modules from it
sys.path.append(os.path.join(os.path.dirname(__file__), "demo"))

def main():
    parser = argparse.ArgumentParser(description="Legacy AIOps Scenario Runner (Dispatcher)")
    parser.add_argument("--scenario", required=True, help="Scenario key (demo_cpu, demo_memory, throughput)")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--duration", type=int, default=120)
    args = parser.parse_args()

    # Dispatch to specific modules depending on the scenario
    if args.scenario == "demo_cpu":
        from demo_cpu import main as cpu_main
        sys.argv = [sys.argv[0], "--iterations", str(args.iterations), "--duration", str(args.duration)]
        cpu_main()
    elif args.scenario == "demo_memory":
        from demo_memory import main as mem_main
        sys.argv = [sys.argv[0], "--iterations", str(args.iterations), "--duration", str(args.duration)]
        mem_main()
    elif args.scenario == "throughput" or args.scenario == "demo_ddos":
        from demo_ddos import main as ddos_main
        sys.argv = [sys.argv[0], "--iterations", str(args.iterations)]
        ddos_main()
    else:
        print(f"Error: Unknown scenario '{args.scenario}'. Use demo_cpu, demo_memory, or demo_ddos.")
        sys.exit(1)

if __name__ == "__main__":
    main()
