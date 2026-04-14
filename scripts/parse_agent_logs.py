import re
import sys
import datetime
import pandas as pd

def parse_logs(log_file):
    """
    Parses AI agent logs to extract detection, decision, and execution times.
    Example log format assumed:
    2024-05-14 10:00:00 - INFO - Alert received: ContainerHighCPU
    2024-05-14 10:00:02 - INFO - Calling Gemini API...
    2024-05-14 10:00:05 - INFO - Gemini response: kill process stress-ng
    2024-05-14 10:00:06 - INFO - Executed tool: kill_process
    2024-05-14 10:00:10 - INFO - Recovery confirmed.
    """
    
    with open(log_file, 'r') as f:
        logs = f.read()

    # Define regex patterns for key events
    events = {
        "alert_received": r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*Alert received",
        "api_call": r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*Calling Gemini API",
        "api_response": r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*Gemini response",
        "execution": r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*Executed tool",
        "recovery": r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*Recovery confirmed"
    }

    results = []
    
    # Simple parser: finds sequences of events
    # In a real log, we'd group by alert ID or similar.
    timestamps = {}
    for name, pattern in events.items():
        matches = re.findall(pattern, logs)
        if matches:
            timestamps[name] = datetime.datetime.strptime(matches[0], "%Y-%m-%d %H:%M:%S")

    if len(timestamps) < 5:
        print("Warning: Could not find all events in log file.")
        # Fill missing with placeholders or return
        
    def delta(t1, t2):
        if not t1 or not t2: return 0
        return (t2 - t1).total_seconds()

    detection_lag = delta(timestamps.get('alert_received'), timestamps.get('api_call'))
    decision_time = delta(timestamps.get('api_call'), timestamps.get('api_response'))
    execution_time = delta(timestamps.get('api_response'), timestamps.get('execution'))
    recovery_time = delta(timestamps.get('execution'), timestamps.get('recovery'))
    total_ttr = delta(timestamps.get('alert_received'), timestamps.get('recovery'))

    print("| Event              | Timestamp | Delta (s) |")
    print("|--------------------|-----------|-----------|")
    print(f"| Alert Received     | {timestamps.get('alert_received')} | - |")
    print(f"| Gemini API Call    | {timestamps.get('api_call')} | {detection_lag} |")
    print(f"| Gemini Response    | {timestamps.get('api_response')} | {decision_time} |")
    print(f"| Tool Execution     | {timestamps.get('execution')} | {execution_time} |")
    print(f"| Recovery Confirmed | {timestamps.get('recovery')} | {recovery_time} |")
    print(f"| **Total TTR**      | - | **{total_ttr}** |")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python parse_agent_logs.py <log_file>")
    else:
        parse_logs(sys.argv[1])
