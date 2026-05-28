"""Isolated test harnesses for the BTP V1 scheduler.

Scripts in this folder are NOT wired into the production pipeline or the
test suite. They exist solely to run one-off scenario tests with
runtime overrides applied to a *copy* of the configuration — the main
scheduler logic in `V1/` is never modified.

Each harness:
  - Monkey-patches only inside its own process.
  - Writes outputs under a dedicated `output_testing/<scenario>/` root
    so it never pollutes `output/`.
  - Restores any patched globals in a `try/finally` block so the
    interpreter exits in a clean state.
"""
