# Codebase Cleanup & Code Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove stale artifacts, old demo result files, and dead entries from the AI tool surface to leave the codebase clean and consistent with the current implementation.

**Architecture:** Pure cleanup — no new modules or restructuring. Three change classes: (1) delete files/dirs that no longer serve a purpose, (2) trim the `TOOLS` dict and `TOOLS_DESCRIPTION` in `tools.py` so the AI's callable surface matches what it actually uses, (3) fix a misplaced `import time` and add one documenting test.

**Tech Stack:** Python 3.x, pytest, git

---

## File Map

| File | Action | What changes |
|---|---|---|
| `DEMO_EXECUTION_REPORT.md` | **Delete** | Stale 31KB report |
| `DEMO_VERIFICATION_REPORT.md` | **Delete** | Stale snapshot |
| `results/` | **Delete dir** | Empty directory |
| `__pycache__/` (root) | **Delete dir** | Build artifact |
| `demos/combined_results/full_demo_report_20260324_105254.txt` | **Delete** | Old run |
| `demos/combined_results/full_demo_report_20260327_010132.txt` | **Delete** | Old run |
| `demos/combined_results/full_demo_report_20260327_010241.txt` | **Delete** | Old run |
| `demos/combined_results/full_demo_report_20260327_011522.txt` | **Delete** | Old run |
| `demos/combined_results/full_demo_report_20260327_012120.txt` | **Delete** | Old run |
| `demos/combined_results/full_demo_report_20260327_012412.txt` | **Delete** | Old run |
| `demos/demo1-baseline/results/baseline_20260327_012124.txt` | **Delete** | Old run |
| `demos/demo1-baseline/results/baseline_20260327_012441.txt` | **Delete** | Old run |
| `demos/demo2-ddos/results/attack_responses_20260324_113322.log` | **Delete** | Old run |
| `demos/demo2-ddos/results/attack_responses_20260327_012947.log` | **Delete** | Old run |
| `demos/demo2-ddos/results/ddos_20260324_113322.txt` | **Delete** | Old run |
| `demos/demo2-ddos/results/ddos_20260327_012947.txt` | **Delete** | Old run |
| `demos/demo3-cpu-stress/results/cpu_stress_20260324_105947.txt` | **Delete** | Old run |
| `demos/demo3-cpu-stress/results/cpu_stress_20260324_113454.txt` | **Delete** | Old run |
| `agent/tools.py` | **Modify** | Move `import time` to top; remove 2 entries from `TOOLS` dict; remove UTILITY section from `TOOLS_DESCRIPTION` |
| `tests/test_tools.py` | **Modify** | Add `test_utility_tools_not_in_agent_tools` |

**Files kept (latest per scenario):**
- `demos/combined_results/full_demo_report_20260327_012438.txt`
- `demos/demo1-baseline/results/baseline_20260330_131036.txt`
- `demos/demo2-ddos/results/attack_responses_20260330_131619.log`
- `demos/demo2-ddos/results/ddos_20260330_131619.txt`
- `demos/demo3-cpu-stress/results/cpu_stress_20260330_131905.txt`

---

## Task 1: Delete Stale Root-Level Reports and Empty Directories

**Files:**
- Delete: `DEMO_EXECUTION_REPORT.md`
- Delete: `DEMO_VERIFICATION_REPORT.md`
- Delete: `results/` (empty directory)
- Delete: `__pycache__/` (root, build artifact)

- [ ] **Step 1: Delete the stale report files and empty/artifact directories**

```bash
rm DEMO_EXECUTION_REPORT.md DEMO_VERIFICATION_REPORT.md
rm -rf results/
rm -rf __pycache__/
```

- [ ] **Step 2: Verify they're gone and nothing else was removed**

```bash
ls -la
```

Expected output: no `DEMO_EXECUTION_REPORT.md`, no `DEMO_VERIFICATION_REPORT.md`, no `results/`, no `__pycache__/`. All other entries (`agent/`, `target-app/`, `tests/`, `docker-compose.yml`, `demo_runner.py`, etc.) still present.

- [ ] **Step 3: Verify tests still pass (nothing depended on those files)**

```bash
pytest tests/ -q
```

Expected: all tests pass, no errors about missing files.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: delete stale DEMO report files and empty results/ dir"
```

---

## Task 2: Delete Old Demo Result Files (Keep Latest Per Scenario)

**Files:**
- Delete 6 files from `demos/combined_results/`
- Delete 2 files from `demos/demo1-baseline/results/`
- Delete 4 files from `demos/demo2-ddos/results/`
- Delete 2 files from `demos/demo3-cpu-stress/results/`

- [ ] **Step 1: Delete old combined results (keep `20260327_012438` only)**

```bash
rm demos/combined_results/full_demo_report_20260324_105254.txt
rm demos/combined_results/full_demo_report_20260327_010132.txt
rm demos/combined_results/full_demo_report_20260327_010241.txt
rm demos/combined_results/full_demo_report_20260327_011522.txt
rm demos/combined_results/full_demo_report_20260327_012120.txt
rm demos/combined_results/full_demo_report_20260327_012412.txt
```

- [ ] **Step 2: Delete old baseline results (keep `20260330_131036` only)**

```bash
rm demos/demo1-baseline/results/baseline_20260327_012124.txt
rm demos/demo1-baseline/results/baseline_20260327_012441.txt
```

- [ ] **Step 3: Delete old DDoS results (keep `20260330_131619` files only)**

```bash
rm demos/demo2-ddos/results/attack_responses_20260324_113322.log
rm demos/demo2-ddos/results/attack_responses_20260327_012947.log
rm demos/demo2-ddos/results/ddos_20260324_113322.txt
rm demos/demo2-ddos/results/ddos_20260327_012947.txt
```

- [ ] **Step 4: Delete old CPU stress results (keep `20260330_131905` only)**

```bash
rm demos/demo3-cpu-stress/results/cpu_stress_20260324_105947.txt
rm demos/demo3-cpu-stress/results/cpu_stress_20260324_113454.txt
```

- [ ] **Step 5: Verify exactly one file remains per scenario**

```bash
ls demos/combined_results/
ls demos/demo1-baseline/results/
ls demos/demo2-ddos/results/
ls demos/demo3-cpu-stress/results/
```

Expected:
```
demos/combined_results/        → full_demo_report_20260327_012438.txt
demos/demo1-baseline/results/  → baseline_20260330_131036.txt
demos/demo2-ddos/results/      → attack_responses_20260330_131619.log  ddos_20260330_131619.txt
demos/demo3-cpu-stress/results/→ cpu_stress_20260330_131905.txt
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: prune old demo result files, keep latest run per scenario"
```

---

## Task 3: Fix `import time` and Trim `TOOLS` Dict in `tools.py`

**Files:**
- Modify: `agent/tools.py`

### 3a — Move `import time` to module top

- [ ] **Step 1: Open `agent/tools.py` and add `import time` to the top-level imports**

The current top of the file looks like:

```python
import subprocess
import logging
import requests
import docker
import os
```

Change it to:

```python
import subprocess
import logging
import requests
import docker
import os
import time
```

- [ ] **Step 2: Remove the misplaced `import time` from inside `reduce_system_load()`**

Find this block inside `reduce_system_load()`:

```python
        # 2. Wait a moment for system to settle
        import time
        time.sleep(2)
```

Change it to (remove the `import time` line, keep the sleep):

```python
        # 2. Wait a moment for system to settle
        time.sleep(2)
```

### 3b — Remove `get_prometheus_metrics` and `validate_container_exists` from `TOOLS`

- [ ] **Step 3: Find the `TOOLS` dict at the bottom of `agent/tools.py` and remove the two entries**

Current `TOOLS` dict:

```python
TOOLS = {
    "get_top_processes":         get_top_processes,
    "kill_process":              kill_process,
    "block_ip":                  block_ip,
    "restart_service":           restart_service,
    "get_prometheus_metrics":    get_prometheus_metrics,
    "apply_rate_limit":          apply_rate_limit,
    "check_system_load":         check_system_load,
    "reduce_system_load":        reduce_system_load,
    "auto_kill_cpu_stress":      auto_kill_cpu_stress,
    "validate_container_exists": validate_container_exists,
    "post_grafana_annotation":   post_grafana_annotation,
}
```

Replace with (9 entries, two removed):

```python
TOOLS = {
    "get_top_processes":      get_top_processes,
    "kill_process":           kill_process,
    "block_ip":               block_ip,
    "restart_service":        restart_service,
    "apply_rate_limit":       apply_rate_limit,
    "check_system_load":      check_system_load,
    "reduce_system_load":     reduce_system_load,
    "auto_kill_cpu_stress":   auto_kill_cpu_stress,
    "post_grafana_annotation": post_grafana_annotation,
}
```

### 3c — Remove UTILITY section from `TOOLS_DESCRIPTION`

- [ ] **Step 4: Find and remove the UTILITY section from `TOOLS_DESCRIPTION`**

Find this block inside the `TOOLS_DESCRIPTION` f-string:

```python
UTILITY (use any time for diagnosis):
- get_prometheus_metrics(query): Query Prometheus for live metrics
- validate_container_exists(container_name): Check if a container is running

NOTE: post_grafana_annotation is called automatically — do NOT include it in your action response.
```

Replace with (UTILITY block removed):

```python
NOTE: post_grafana_annotation is called automatically — do NOT include it in your action response.
```

- [ ] **Step 5: Verify the file looks correct**

```bash
grep -n "get_prometheus_metrics\|validate_container_exists" agent/tools.py
```

Expected output: lines showing only the **function definitions** (`def get_prometheus_metrics` and `def validate_container_exists`) — NOT any lines in `TOOLS` dict or `TOOLS_DESCRIPTION`. Example expected:

```
51:def get_prometheus_metrics(query: str) -> str:
131:def validate_container_exists(container_name: str = None) -> str:
```

(Line numbers may differ — what matters is that no match appears inside the TOOLS dict or TOOLS_DESCRIPTION.)

- [ ] **Step 6: Run tests to confirm nothing broke**

```bash
pytest tests/ -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add agent/tools.py
git commit -m "refactor: move import time to module top; trim TOOLS dict to agent-callable tools only"
```

---

## Task 4: Add Documenting Test for TOOLS Surface

**Files:**
- Modify: `tests/test_tools.py`

- [ ] **Step 1: Open `tests/test_tools.py` and append the new test at the end of the file**

Add after the last existing test:

```python
def test_utility_tools_not_in_agent_tools():
    """get_prometheus_metrics and validate_container_exists are
    internal utilities — not AI-callable tools.
    They remain as functions but must NOT appear in TOOLS."""
    assert "get_prometheus_metrics" not in tools.TOOLS
    assert "validate_container_exists" not in tools.TOOLS
    # Confirm the functions still exist as utilities
    assert callable(tools.get_prometheus_metrics)
    assert callable(tools.validate_container_exists)
```

- [ ] **Step 2: Run the new test to verify it passes**

```bash
pytest tests/test_tools.py::test_utility_tools_not_in_agent_tools -v
```

Expected:
```
tests/test_tools.py::test_utility_tools_not_in_agent_tools PASSED
```

- [ ] **Step 3: Run the full test suite to confirm no regressions**

```bash
pytest tests/ -v
```

Expected: all tests pass. Count should be the same as before plus 1 new passing test.

- [ ] **Step 4: Commit**

```bash
git add tests/test_tools.py
git commit -m "test: assert utility tools are not in agent-callable TOOLS dict"
```

---

## Task 5: Final Verification

- [ ] **Step 1: Confirm TOOLS has exactly 9 keys**

```bash
python -c "
import sys, os
sys.path.insert(0, 'agent')
os.environ.setdefault('GEMINI_API_KEY', 'fake')
os.environ.setdefault('AGENT_API_KEY', 'fake-key-12345')
import tools
print('TOOLS keys:', sorted(tools.TOOLS.keys()))
print('Count:', len(tools.TOOLS))
"
```

Expected output:
```
TOOLS keys: ['apply_rate_limit', 'auto_kill_cpu_stress', 'block_ip', 'check_system_load', 'get_top_processes', 'kill_process', 'post_grafana_annotation', 'reduce_system_load', 'restart_service']
Count: 9
```

- [ ] **Step 2: Confirm `import time` is at module level (not inside a function)**

```bash
grep -n "import time" agent/tools.py
```

Expected: exactly one line, near the top of the file (line < 15), not indented.

- [ ] **Step 3: Confirm stale files are gone**

```bash
ls DEMO_EXECUTION_REPORT.md DEMO_VERIFICATION_REPORT.md results/ __pycache__/ 2>&1
```

Expected: `No such file or directory` for all four.

- [ ] **Step 4: Run full test suite one final time**

```bash
pytest tests/ -v --tb=short
```

Expected: all tests pass, zero failures, zero errors.

- [ ] **Step 5: Final commit (if any stray changes remain) and log**

```bash
git status
git log --oneline -6
```

Expected: `git status` shows clean working tree. Log shows the 3 new commits from Tasks 1–4.
