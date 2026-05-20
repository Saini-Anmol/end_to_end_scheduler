# Fixture 3 — EHT1000 duplicate routing row

**Setup.** Routing sheet has two rows for `EHT1000 -480MM/90°` calendering:
row 44 (`is_primary == 1.0`) and row 49 (`is_primary == NaN`).

**Expected.** Audit keeps row 44, drops row 49, logs row 49 to Warn (not
HALT). Scheduler uses row 44's machine list and processing time.

**Passes iff.**
- `routing_cleaned.csv` contains exactly one row for that item × operation.
- `audit_report.md` contains a Warn line citing row 49.
