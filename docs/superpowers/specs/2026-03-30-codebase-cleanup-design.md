# Codebase Cleanup & Code Hygiene — Design Spec
**Date:** 2026-03-30
**Project:** NT531 — Agentic AIOps Demo
**Scope:** Option B — Surface cleanup + targeted code hygiene
**Risk:** Low — no architectural changes, no import-path changes

---

## 1. Problem Statement

After a day of heavy development (25 commits), the codebase has accumulated:

- Stale markdown reports at the root that are no longer accurate
- 8+ demo result files from repeated test runs (only the latest matters)
- An empty `results/` directory
- A root `__pycache__/` that should not be version-controlled
- Two tools in the AI-callable `TOOLS` dict (`get_prometheus_metrics`, `validate_container_exists`) that the AI never selects and were superseded by `enrich_alert_context`
- A misplaced `import time` inside a function body in `tools.py`

---

## 2. Goals

1. Remove all stale and accumulated artifacts without breaking any functionality.
2. Trim the AI tool surface to exactly what the agent uses — no phantom options.
3. Fix a misplaced `import time` in `tools.py`.
4. Document the "utility vs. agent-callable" distinction with a test.
5. Update `.gitignore` to prevent future accumulation.

**Out of scope:** Restructuring files/modules, changing any business logic, modifying tests for existing behavior, changing the LLM or pipeline.

---

## 3. Changes

### 3.1 File Deletions

| Path | Reason |
|---|---|
| `results/` | Empty directory, no content |
| `__pycache__/` (root) | Build artifact, must not be tracked |
| `DEMO_EXECUTION_REPORT.md` | 31KB stale report — superseded by `demo_runner.py` CSV output |
| `DEMO_VERIFICATION_REPORT.md` | Stale snapshot, no longer accurate |
| `demos/combined_results/full_demo_report_20260324_105254.txt` | Old run; keep latest (20260327_012438) only |
| `demos/combined_results/full_demo_report_20260327_010132.txt` | Old run; keep latest (20260327_012438) only |
| `demos/combined_results/full_demo_report_20260327_010241.txt` | Old run; keep latest (20260327_012438) only |
| `demos/combined_results/full_demo_report_20260327_011522.txt` | Old run; keep latest (20260327_012438) only |
| `demos/combined_results/full_demo_report_20260327_012120.txt` | Old run; keep latest (20260327_012438) only |
| `demos/combined_results/full_demo_report_20260327_012412.txt` | Old run; keep latest (20260327_012438) only |
| `demos/demo1-baseline/results/baseline_20260327_*.txt` (2 files) | Old runs; keep 20260330 only |
| `demos/demo2-ddos/results/attack_responses_20260324_*.log` | Old run; keep 20260330 only |
| `demos/demo2-ddos/results/ddos_20260324_*.txt` | Old run; keep 20260330 only |
| `demos/demo2-ddos/results/attack_responses_20260327_*.log` | Old run; keep 20260330 only |
| `demos/demo2-ddos/results/ddos_20260327_*.txt` | Old run; keep 20260330 only |
| `demos/demo3-cpu-stress/results/cpu_stress_20260324_*.txt` | Old run; keep 20260330 only |
| `demos/demo3-cpu-stress/results/cpu_stress_20260324_113454.txt` | Old run; keep 20260330 only |

**Files kept (latest per scenario):**
- `demos/combined_results/full_demo_report_20260327_012438.txt` (latest combined report)
- `demos/demo1-baseline/results/baseline_20260330_131036.txt`
- `demos/demo2-ddos/results/attack_responses_20260330_131619.log`
- `demos/demo2-ddos/results/ddos_20260330_131619.txt`
- `demos/demo3-cpu-stress/results/cpu_stress_20260330_131905.txt`

### 3.2 `.gitignore` Updates

Add or confirm the following entries are present:
```
__pycache__/
*.pyc
*.pyo
.pytest_cache/
results/
```

### 3.3 `agent/tools.py` — Trim TOOLS Dict

**Remove** `get_prometheus_metrics` and `validate_container_exists` from the `TOOLS` dict.
The functions themselves stay in `tools.py` (they have tests and serve as internal utilities).

Before:
```python
TOOLS = {
    "get_top_processes":         get_top_processes,
    "kill_process":              kill_process,
    "block_ip":                  block_ip,
    "restart_service":           restart_service,
    "get_prometheus_metrics":    get_prometheus_metrics,   # ← REMOVE
    "apply_rate_limit":          apply_rate_limit,
    "check_system_load":         check_system_load,
    "reduce_system_load":        reduce_system_load,
    "auto_kill_cpu_stress":      auto_kill_cpu_stress,
    "validate_container_exists": validate_container_exists, # ← REMOVE
    "post_grafana_annotation":   post_grafana_annotation,
}
```

After: 9 entries (the two removed).

### 3.4 `agent/tools.py` — Trim TOOLS_DESCRIPTION

Remove the "UTILITY" section from `TOOLS_DESCRIPTION`:
```
UTILITY (use any time for diagnosis):
- get_prometheus_metrics(query): Query Prometheus for live metrics
- validate_container_exists(container_name): Check if a container is running
```

This section is part of the system prompt sent to the AI. Removing it prevents the AI from ever seeing these as options.

### 3.5 `agent/tools.py` — Fix Misplaced Import

Move `import time` from inside `reduce_system_load()` body to the module-level imports at the top of `tools.py`.

Before (inside function):
```python
def reduce_system_load() -> str:
    ...
    import time          # ← misplaced
    time.sleep(2)
```

After (at top of file):
```python
import subprocess
import logging
import requests
import docker
import os
import time             # ← moved here
```

### 3.6 `tests/test_tools.py` — Add Sanity Test

Add one test to document the intentional design decision:

```python
def test_utility_tools_not_in_agent_tools():
    """get_prometheus_metrics and validate_container_exists are
    internal utilities — not AI-callable tools."""
    assert "get_prometheus_metrics" not in tools.TOOLS
    assert "validate_container_exists" not in tools.TOOLS
```

---

## 4. Risk Assessment

| Change | Risk | Mitigation |
|---|---|---|
| File deletions | None — no code references these files | Verified no imports |
| `.gitignore` update | None | Additive only |
| Remove from TOOLS | Negligible — AI never called them | Confirmed by code review + test added |
| Trim TOOLS_DESCRIPTION | Negligible — only changes system prompt | AI still has all scenario-mapped tools |
| Move `import time` | None — `time` is stdlib, always available | Trivial change |
| New test | None | Adds confidence, no side effects |

---

## 5. Success Criteria

- `git status` shows no untracked/stale artifacts after cleanup
- All existing tests pass: `pytest tests/`
- `TOOLS` dict has exactly 9 keys (not 11)
- `"get_prometheus_metrics"` and `"validate_container_exists"` do NOT appear in `TOOLS_DESCRIPTION`
- New test `test_utility_tools_not_in_agent_tools` passes
- `import time` appears at module level in `tools.py`, not inside a function
