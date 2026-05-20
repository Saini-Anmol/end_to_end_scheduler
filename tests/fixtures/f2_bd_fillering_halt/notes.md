# Fixture 2 — BD-12843443-4 Fillering HALT

**Setup.** Routing row for `BD-12843443-4` Fillering has `proc_time = NaN`.

**Expected.** Audit module classifies this as HALT (Section 9 finding #4 /
Section 8.D — no silent imputation). Engine exits non-zero **before** any
`schedule.csv` is written. `audit_report.md` names the offending routing row.

**Passes iff.**
- No `schedule.csv` exists in the output folder.
- Exit code ≠ 0.
- `audit_report.md` contains the HALT line citing the BD Fillering row.
