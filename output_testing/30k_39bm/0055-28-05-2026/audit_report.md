# Audit report

**Overall status:** WARN

## Summary

- **HALT**: 0
- **WARN**: 11

Breakdown by code:
- `WARN/AGING_CONFLICTING_DUPLICATES` × 1
- `WARN/AGING_MIXED_UNITS` × 1
- `WARN/BOM_ENCODING_FIX` × 1
- `WARN/CAPSTRIP_ROUTING_DROPPED` × 5
- `WARN/ROUTING_ALT_MACHINE_COUNT_WRONG` × 1
- `WARN/ROUTING_DUPLICATE_DROPPED` × 1
- `WARN/ROUTING_NULL_TRANSFER_TIME` × 1

## Dataset row counts

- Pilot curing rows: 510
- Raw routing rows: 62
- Cleaned routing rows: 48
- BOM rows: 65
- Aging Master rows (deduped): 6264
- ItemType Master rows (deduped): 7104
- MPQ rows: 13

## HALT findings

_None._

## WARN findings

- [WARN] — `ROUTING_DUPLICATE_DROPPED` — `Routing` pandas row 49 (Excel row 51) — item=`EHT1000` — Duplicate routing row for (routed_product='EHT1000', operation_seq=40) has is_primary != 1.0; dropped per L7.
- [WARN] — `CAPSTRIP_ROUTING_DROPPED` — `Routing` pandas row 6 (Excel row 8) — item=`MB614` — Capstrip routing row dropped per L12 (routed_product='MB614', finished_product_stock='CAP 66 - CAPSTRIP').
- [WARN] — `CAPSTRIP_ROUTING_DROPPED` — `Routing` pandas row 7 (Excel row 9) — item=`B616M` — Capstrip routing row dropped per L12 (routed_product='B616M', finished_product_stock='CAP 66 - CAPSTRIP').
- [WARN] — `CAPSTRIP_ROUTING_DROPPED` — `Routing` pandas row 8 (Excel row 10) — item=`CAP 66` — Capstrip routing row dropped per L12 (routed_product='CAP 66', finished_product_stock='CAP 66 - CAPSTRIP').
- [WARN] — `CAPSTRIP_ROUTING_DROPPED` — `Routing` pandas row 9 (Excel row 11) — item=`CAP 66-MOTHERROLL` — Capstrip routing row dropped per L12 (routed_product='CAP 66-MOTHERROLL', finished_product_stock='CAP 66 - CAPSTRIP').
- [WARN] — `CAPSTRIP_ROUTING_DROPPED` — `Routing` pandas row 10 (Excel row 12) — item=`CAP 66 - CAPSTRIP` — Capstrip routing row dropped per L12 (routed_product='CAP 66 - CAPSTRIP', finished_product_stock='CAP 66 - CAPSTRIP').
- [WARN] — `ROUTING_NULL_TRANSFER_TIME` — `Routing` — 61 routing rows have null transfer_time_min; defaulting to 10 min per plant rule.
- [WARN] — `ROUTING_ALT_MACHINE_COUNT_WRONG` — `Routing` — 46 routing rows have alt_machine_count != len(parsed_machines). Column ignored per Section 8.F; using derived eligible_machine_count instead.
- [WARN] — `BOM_ENCODING_FIX` — `BOM` — 1 BOM string(s) had mojibake (e.g. 'Â°' → '°'); normalised to canonical unicode. First: pandas row 10, column='Output', 'CPJ1218-162MM/29Â°' → 'CPJ1218-162MM/29°'.
- [WARN] — `AGING_MIXED_UNITS` — `Aging Master` — 757 item code(s) have MinAgingUnit != MaxAgingUnit. Normaliser converts to minutes downstream. First 10: ['ARAMID', 'B102', 'B127', 'B127RP', 'B13', 'B163', 'B163RP', 'B176RP', 'B186', 'B186RP']
- [WARN] — `AGING_CONFLICTING_DUPLICATES` — `Aging Master` — 207 item code(s) have multiple Aging Master rows with conflicting (min, max, unit) values. Keeping first per ItemCode. First 10: ['AIL2056015ZEPHYR2S-2', 'B-127-50MM', 'B370', 'B7152', 'B7152RP', 'BDIN113244', 'BDIN128655', 'BDIN138355', 'CAP 66 - CAPSTRIP', 'CAP30-MOTHERROLL']
