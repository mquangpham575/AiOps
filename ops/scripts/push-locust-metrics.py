#!/usr/bin/env python3
"""
push-locust-metrics.py - Push Locust CSV metrics to Prometheus Pushgateway
==========================================================================

Usage:
    python push-locust-metrics.py --csv-dir results --pushgateway http://localhost:9091
    python push-locust-metrics.py --csv results/stats.csv --job locust_baseline

Locust outputs CSV files:
    results_stats.csv
    results_exceptions.csv
    results_history.csv
"""

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Optional

import requests


class LocustMetricsPusher:
    def __init__(
        self, pushgateway_url: str, job: str = "locust", instance: str = "loadgen"
    ):
        self.pushgateway_url = pushgateway_url.rstrip("/")
        self.job = job
        self.instance = instance

    def _push_metric(
        self,
        metric_name: str,
        value: float,
        metric_type: str = "gauge",
        labels: dict = None,
        help_text: str = "",
    ):
        """Push a single metric to Pushgateway."""
        label_str = ""
        if labels:
            label_parts = [f'{k}="{v}"' for k, v in labels.items()]
            label_str = "{" + ",".join(label_parts) + "}"

        metric_line = f"# TYPE {metric_name} {metric_type}\n"
        if help_text:
            metric_line = f"# HELP {metric_name} {help_text}\n" + metric_line

        payload = f"{metric_line}{metric_name}{label_str} {value}\n"

        url = f"{self.pushgateway_url}/metrics/job/{self.job}/instance/{self.instance}"
        if labels:
            for k, v in labels.items():
                url += f"/{k}/{v}"

        try:
            requests.post(url, data=payload.encode("utf-8"), timeout=5)
        except requests.exceptions.RequestException as e:
            print(f"[WARN] Failed to push {metric_name}: {e}", file=sys.stderr)

    def push_csv(self, csv_path: Path, phase: str = "baseline"):
        """Push metrics from a Locust stats CSV file."""
        if not csv_path.exists():
            print(f"[ERROR] CSV file not found: {csv_path}", file=sys.stderr)
            return

        labels = {"phase": phase}

        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                method = row.get("Method", "GET")
                name = row.get("Name", "total")

                type_labels = {**labels, "method": method.lower(), "endpoint": name}

                self._push_metric(
                    "locust_request_count",
                    float(row.get("Request Count", 0)),
                    "gauge",
                    type_labels,
                    "Total request count",
                )
                self._push_metric(
                    "locust_failure_count",
                    float(row.get("Failure Count", 0)),
                    "gauge",
                    type_labels,
                    "Total failure count",
                )
                self._push_metric(
                    "locust_median_response_time",
                    float(row.get("Median Response Time", 0)),
                    "gauge",
                    type_labels,
                    "Median response time in ms",
                )
                self._push_metric(
                    "locust_avg_response_time",
                    float(row.get("Average Response Time", 0)),
                    "gauge",
                    type_labels,
                    "Average response time in ms",
                )
                self._push_metric(
                    "locust_max_response_time",
                    float(row.get("Max Response Time", 0)),
                    "gauge",
                    type_labels,
                    "Max response time in ms",
                )
                self._push_metric(
                    "locust_requests_per_second",
                    float(row.get("Requests/s", 0)),
                    "gauge",
                    type_labels,
                    "Requests per second",
                )

        print(f"[OK] Pushed metrics from {csv_path} (phase={phase})")

    def push_stats_from_dir(self, csv_dir: Path, phase: str = "baseline"):
        """Push all stats from a directory containing Locust CSV files."""
        csv_dir = Path(csv_dir)

        stats_file = csv_dir / "stats.csv"
        if stats_file.exists():
            self.push_csv(stats_file, phase)

        exceptions_file = csv_dir / "exceptions.csv"
        if exceptions_file.exists():
            self._push_exceptions(exceptions_file, phase)

        history_file = csv_dir / "history.csv"
        if history_file.exists():
            self._push_history(history_file, phase)

    def _push_exceptions(self, exceptions_file: Path, phase: str):
        """Push exception counts."""
        with open(exceptions_file, newline="") as f:
            reader = csv.DictReader(f)
            count = sum(1 for _ in reader)
        self._push_metric(
            "locust_exception_count",
            float(count),
            "gauge",
            {"phase": phase},
            "Number of exceptions",
        )
        print(f"[OK] Pushed exception count: {count}")

    def _push_history(self, history_file: Path, phase: str):
        """Push historical metrics (timestamps + RPS)."""
        with open(history_file, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                timestamp = int(row.get("Timestamp", 0))
                rps = float(row.get("RPS", 0))
                self._push_metric(
                    "locust_rps_historical",
                    rps,
                    "gauge",
                    {"phase": phase, "timestamp": str(timestamp)},
                    "Historical RPS",
                )
        print(f"[OK] Pushed historical metrics from {history_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Push Locust CSV metrics to Prometheus Pushgateway",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Push from directory
  python push-locust-metrics.py --csv-dir results/baseline_run_001 --phase baseline

  # Push single CSV
  python push-locust-metrics.py --csv results/stats.csv --job locust_load

  # Full pipeline
  locust -f tests/performance/locustfile.py --host=http://10.0.1.6:80 --run-time 300s --headless --csv results/baseline
  python push-locust-metrics.py --csv-dir results/baseline --pushgateway http://10.0.1.5:9091 --phase baseline
        """,
    )
    parser.add_argument(
        "--csv-dir", type=Path, help="Directory containing Locust CSV files"
    )
    parser.add_argument("--csv", type=Path, help="Single CSV file to push")
    parser.add_argument(
        "--pushgateway",
        default="http://localhost:9091",
        help="Pushgateway URL (default: http://localhost:9091)",
    )
    parser.add_argument(
        "--job", default="locust", help="Job name for metrics (default: locust)"
    )
    parser.add_argument(
        "--instance", default="loadgen", help="Instance name (default: loadgen)"
    )
    parser.add_argument(
        "--phase", default="baseline", help="Phase label (baseline/load)"
    )

    args = parser.parse_args()

    if not args.csv_dir and not args.csv:
        parser.error("Either --csv-dir or --csv must be specified")

    pusher = LocustMetricsPusher(
        pushgateway_url=args.pushgateway, job=args.job, instance=args.instance
    )

    if args.csv:
        pusher.push_csv(args.csv, args.phase)
    elif args.csv_dir:
        pusher.push_stats_from_dir(args.csv_dir, args.phase)

    print(f"[DONE] Metrics pushed to {args.pushgateway}")


if __name__ == "__main__":
    main()
