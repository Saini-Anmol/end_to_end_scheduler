---
name: verification-commands
description: Useful bash commands for verifying BTP scheduler correctness
metadata:
  type: project
---

## Test suite
```bash
.venv/bin/python -m pytest tests/ -q               # all 215 tests
.venv/bin/python -m pytest tests/integration/ -v   # includes determinism check
```
215 tests pass as of 2026-05-21.

## Determinism check (full pipeline)
Integration test `TestFullPath::test_deterministic_artefacts_byte_identical` patches
BD-12843443-4 Fillering proc_time to 60 SEC/BATCH, runs bootstrap twice with fixed
timestamps (2099-01-01 12:31, 12:32), then bytes-compares 9 deterministic artefacts.
This is the canonical determinism proof.

## HALT path verification
```bash
.venv/bin/python -m V1.setups.cli --inputs input --outputs /tmp/test_out
# Should exit 10 (AUDIT_NULL_PROC_TIME), produce only audit_report.md + routing_cleaned.csv
echo $?   # should be 10
ls /tmp/test_out/*/   # should NOT include schedule.csv
```

## Diamond BOM check
```python
# Run this to verify no duplicate serves_blocks from diamond BOM items:
from V1.routes.demand_explosion import run as demand_run
# ... CPJ1218 and EHT1000 are the two diamond-pattern items in pilot BOM
# verified safe 2026-05-21
```

## Key items to spot-check on every review
1. `guardrails.py` line count — must be >6 to have actual code
2. `forward_scheduler.py:239-249` — building lot machine selection loop
3. `fefo.py:27` — is_expired uses `<` not `<=` (correct for L22)
4. `diagnostics.py:54,60` — gap < mn and gap > mx (correct for L22)
5. `lot_id.py:32` — format `{safe}__{}__{:04d}` (correct L23)
