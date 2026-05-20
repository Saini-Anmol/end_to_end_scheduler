# Fixture 4 — B460 mixed-unit aging

**Setup.** Aging Master row for `B460` has `MinAging = 4` with unit `Hours`
and `MaxAging = 4` with unit `Days`.

**Expected.** Audit normaliser outputs `min_aging_min = 240`,
`max_aging_min = 5760`. One Warn line cites the mixed-unit pair (Section 9
finding #1).

**Passes iff.**
- Cleaned aging table shows `(240, 5760)` for `B460`.
- Warn line exists in `audit_report.md`.
