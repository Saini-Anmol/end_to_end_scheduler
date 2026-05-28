"""Scenario test: 30,000 GT demand on 39 Tyre-Building machines.

PURPOSE
-------
Stress-test the V1 forward scheduler against a high-volume curing schedule
(30k tyres, 170 presses, 1-day horizon) while ASSUMING 39 Tyre-Building
machines are available (vs the production fleet of 8: 6001-6004, 7001-7004).
The harness asks the question: "How long does the upstream chain take to
feed 30k GT through 39 parallel building lines?"

ISOLATION
---------
This file lives outside `V1/` and is NOT imported by the main scheduler,
the CLI, or the test suite. The runtime overrides it applies (routing
machines cell, settings.building_pool) are scoped to this process via
monkey-patch with a `try/finally` restore. The production scheduler is
NEVER mutated.

WHAT IS OVERRIDDEN
------------------
1. **Routing — GT op 70 `machines` cell** — original lists 8 building
   machines; we substitute a 39-machine list (6001..6039) so the
   eligibility index built by audit picks up all 39.
2. **`settings.building_pool`** — extended to 39 entries so the L18
   "preferred primary" check still finds the primary in the pool.
3. **`settings.building_primary`** — kept as "6001" (first by alpha order).
4. **`forward_scheduler._is_building_lot`** — patched to return False so
   the L18 "wait on primary" logic is disabled FOR THIS TEST RUN. With
   L18 active and an infeasible curing schedule (every block is LATE),
   the engine falls back to pinning every GT lot on 6001 — defeating
   the purpose of having 39 machines. By treating GT as a regular op,
   the scheduler picks the earliest-finishing machine across the pool
   and we observe genuine 39-way parallelism.

WHAT IS NOT OVERRIDDEN
----------------------
- Lot sizing, FEFO matching, AND-join atomicity, aging windows, MPQ
  values, BOM, or any other scheduler logic.
- The 30k curing schedule itself: read verbatim from
  `input/curing_schedule_30k_170presses_1day.xlsx`.

RUN
---
    uv run python testing/run_30k_39_building.py

OUTPUTS
-------
Written under `output_testing/30k_39bm/<HHMM-DD-MM-YYYY>/`, NOT `output/`,
so test runs never collide with production runs.
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

# Make repo root importable when invoked as `python testing/run_30k_39_building.py`.
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from V1.config.settings import load_settings  # noqa: E402
from V1.routes import audit as audit_mod  # noqa: E402
from V1.routes import forward_scheduler as fs_mod  # noqa: E402
from V1.setups import bootstrap  # noqa: E402


# ── Test knobs ────────────────────────────────────────────────────────────
BUILDING_MACHINE_COUNT = 39
BUILDING_MACHINES = tuple(f"60{i:02d}" for i in range(1, BUILDING_MACHINE_COUNT + 1))
CURING_FILE = Path("input/curing_schedule_30k_170presses_1day.xlsx")
INPUT_DIR = Path("input")
OUTPUT_ROOT = Path("output_testing/30k_39bm")


def _patch_routing(raw_inputs: dict) -> dict:
    """Replace GT op 70's machines cell with the 39-machine list."""
    routing = raw_inputs["routing"].copy()
    new_machines_str = ", ".join(BUILDING_MACHINES)

    mask = (
        (routing["routed_product"].astype(str) == "GT2056516TAXIMXTL")
        & (routing["operation_seq"] == 70)
    )
    matched = int(mask.sum())
    if matched == 0:
        raise RuntimeError(
            "Could not find GT2056516TAXIMXTL op 70 row in routing — "
            "is the SKU code or operation_seq still right?"
        )

    routing.loc[mask, "machines"] = new_machines_str
    if "alt_machine_count" in routing.columns:
        routing.loc[mask, "alt_machine_count"] = BUILDING_MACHINE_COUNT
    print(
        f"[test-patch] Overrode {matched} GT op 70 row(s): now lists "
        f"{BUILDING_MACHINE_COUNT} building machines "
        f"({BUILDING_MACHINES[0]}..{BUILDING_MACHINES[-1]})."
    )
    raw_inputs["routing"] = routing
    return raw_inputs


def main() -> int:
    print("=" * 74)
    print("BTP V1 — TEST SCENARIO: 30k curing demand × 39 building machines")
    print("=" * 74)
    print(f"  curing file        : {CURING_FILE}")
    print(f"  building pool size : {BUILDING_MACHINE_COUNT}")
    print(f"  outputs root       : {OUTPUT_ROOT}")
    print(f"  ⚠️  This is an isolated test — production config untouched.")
    print()

    # Patch the building pool in settings (frozen dataclass → replace).
    settings = load_settings()
    settings = dataclasses.replace(
        settings,
        building_pool=BUILDING_MACHINES,
        building_primary=BUILDING_MACHINES[0],
    )

    # Monkey-patch _load_inputs to inject the 39-machine routing cell.
    # We patch the FUNCTION on the module, not the class — restored in
    # the finally block so the interpreter exits clean.
    original_load = audit_mod._load_inputs

    def _patched_load(*args, **kwargs):
        raw = original_load(*args, **kwargs)
        return _patch_routing(raw)

    audit_mod._load_inputs = _patched_load

    # Disable L18 single-primary pinning for the duration of this test.
    # See module docstring point #4 for rationale.
    original_is_building = fs_mod._is_building_lot
    fs_mod._is_building_lot = lambda lot, settings: False
    print(
        "[test-patch] Disabled L18 building-primary pinning — GT lots will "
        "fan out across all 39 machines via standard earliest-end dispatch."
    )

    try:
        exit_code = bootstrap.run(
            settings=settings,
            input_dir=INPUT_DIR,
            output_root=OUTPUT_ROOT,
            curing_file=CURING_FILE,
        )
    finally:
        audit_mod._load_inputs = original_load
        fs_mod._is_building_lot = original_is_building

    print()
    print("=" * 74)
    print(f"[test] finished — exit code {exit_code}.")
    print(f"[test] artefacts: {OUTPUT_ROOT}/<latest>/")
    print("=" * 74)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
