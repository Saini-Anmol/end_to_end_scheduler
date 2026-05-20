"""Run-level assertions.

- L17 t0 guardrail: t0 + sum(MIN_aging) along longest BOM path <= first_curing_start.
- Section 16 invariant: every reservation 'created' row has exactly one
  matching 'consumed' | 'expired' | 'released' row.
"""
