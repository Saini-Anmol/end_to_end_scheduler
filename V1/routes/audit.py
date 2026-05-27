"""Route 1 — audit (Section 10 #1, approach-flow steps 1-7).

Reads raw inputs from input/, classifies Section 9 findings into HALT vs Warn
buckets, parses messy routing fields, deduplicates aging/itemtype masters,
removes the Capstrip chain (L12) from the routing.

Returns an AuditResult unconditionally. The bootstrap inspects
`result.halt_findings` and decides whether to write the report-then-exit or
continue downstream. This separation lets the writer emit a complete
`audit_report.md` even on HALT.

Unit normalisation to integer minutes (L20) is NOT done here — that lives in
Module 2 (unit_normalisation). Audit only flags structural issues.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import pandas as pd

from V1.config.enums import AgingUnit, FindingSeverity
from V1.config.halt_codes import HaltCode
from V1.config.settings import Settings
from V1.models.finding import AuditFinding
from V1.utilities.machine_parser import join_machines, parse_machines


# --- Pure helpers -----------------------------------------------------------

_AGING_SHEET = "Aging Master"
_ITEMTYPE_SHEET = "ItemType Master"
_MPQ_SHEET = "MPQ"
_BUFFER_SHEET = "Buffer Master"

# Accepted aging-unit aliases (case-insensitive at check time).  Kept in sync
# with V1.utilities.unit_conversion._AGING_UNIT_MULT_MIN — every alias that
# the normaliser accepts is also "known" here, so we don't surface a noisy
# AGING_UNKNOWN_UNIT warning for a value that actually converts correctly.
_KNOWN_AGING_UNITS: frozenset[str] = frozenset({
    "Days", "Day",
    "Hours", "Hour", "Hr", "Hrs",
    "Minutes", "Minute", "Min",
})

# Mojibake → correct unicode (UTF-8 bytes c2 b0 misread as Latin-1 yields 'Â°').
# Observed on BOM row 10: 'CPJ1218-162MM/29Â°' should be 'CPJ1218-162MM/29°'.
_MOJIBAKE_FIXES: tuple[tuple[str, str], ...] = (
    ("Â°", "°"),
)


def _fix_mojibake(s: object) -> object:
    if not isinstance(s, str):
        return s
    out = s
    for bad, good in _MOJIBAKE_FIXES:
        out = out.replace(bad, good)
    return out


def _routing_sheet(sku: str) -> str:
    return f"Routing - {sku}"


def _bom_sheet(sku: str) -> str:
    return f"BOM - {sku}"


# --- Result type ------------------------------------------------------------

@dataclass
class AuditResult:
    """Outputs of the audit pass.

    Frames carry the *raw* values; minute conversion happens in Module 2.
    Capstrip items are removed from `routing_cleaned_df` per L12 but left in
    `bom_df` so the BOM viz can still tag them OUT-OF-SCOPE.
    """
    curing_df: pd.DataFrame             # pilot-scoped curing rows (42)
    routing_df: pd.DataFrame            # raw routing (62 rows)
    routing_cleaned_df: pd.DataFrame    # parsed machines, dedup, capstrip removed
    bom_df: pd.DataFrame                # full BOM for the pilot SKU (Capstrip kept)
    aging_df: pd.DataFrame              # deduped per ItemCode
    itemtype_df: pd.DataFrame           # deduped per ItemCode
    mpq_df: pd.DataFrame                # MPQ table
    findings: list[AuditFinding] = field(default_factory=list)

    @property
    def halt_findings(self) -> list[AuditFinding]:
        return [f for f in self.findings if f.severity == FindingSeverity.HALT]

    @property
    def warn_findings(self) -> list[AuditFinding]:
        return [f for f in self.findings if f.severity == FindingSeverity.WARN]


# Finding code → HALT exit code lookup. Public so bootstrap can map.
HALT_CODE_MAP: dict[str, HaltCode] = {
    "AUDIT_NULL_PROC_TIME": HaltCode.AUDIT_NULL_PROC_TIME,
    "AUDIT_MISSING_AGING": HaltCode.AUDIT_MISSING_AGING,
    "AUDIT_MISSING_ITEMTYPE": HaltCode.AUDIT_MISSING_ITEMTYPE,
    "AUDIT_NO_CURING_ROWS": HaltCode.AUDIT_MISSING_AGING,  # reuse code 11; no dedicated slot
}


# --- Loaders ---------------------------------------------------------------

def _load_inputs(
    input_dir: Path, sku: str, curing_file: Path | None = None,
) -> dict[str, pd.DataFrame]:
    """Load raw inputs. `curing_file` overrides the default curing schedule
    path; .csv and .xlsx are both supported (we sniff by suffix). The routing
    workbook + BOM are always looked up in `input_dir`."""
    if curing_file is None:
        curing_path = input_dir / "BTP_PCR_May_Curing_Schedule.csv"
    elif curing_file.is_absolute() or curing_file.exists():
        # Absolute path, or relative path that resolves from the cwd
        # (e.g. the user typed `input/foo.xlsx`).
        curing_path = curing_file
    else:
        # Bare filename — look it up inside the inputs directory.
        curing_path = input_dir / curing_file
    routing_path = input_dir / "BTP_Routing_1325216614081STMX0 BOM_Final (1).xlsx"
    if not curing_path.exists():
        raise FileNotFoundError(curing_path)
    if not routing_path.exists():
        raise FileNotFoundError(routing_path)

    suffix = curing_path.suffix.lower()
    if suffix == ".csv":
        curing = pd.read_csv(curing_path)
    elif suffix in (".xlsx", ".xls"):
        curing = pd.read_excel(curing_path)
    else:
        raise ValueError(
            f"Unsupported curing file extension {suffix!r}; use .csv or .xlsx"
        )
    xl = pd.ExcelFile(routing_path)
    return {
        "curing": curing,
        "bom": pd.read_excel(xl, sheet_name=_bom_sheet(sku)),
        "routing": pd.read_excel(xl, sheet_name=_routing_sheet(sku)),
        "aging": pd.read_excel(xl, sheet_name=_AGING_SHEET),
        "itemtype": pd.read_excel(xl, sheet_name=_ITEMTYPE_SHEET),
        "mpq": pd.read_excel(xl, sheet_name=_MPQ_SHEET),
    }


# --- Findings detectors ----------------------------------------------------

def _check_null_proc_time(routing: pd.DataFrame, findings: list[AuditFinding]) -> None:
    """Section 9 #4 / Section 8.D — HALT on null proc_time.

    Known case: BD-12843443-4 Fillering. No silent imputation.
    """
    mask = routing["proc_time"].isna()
    for idx in routing[mask].index:
        row = routing.loc[idx]
        findings.append(AuditFinding(
            severity=FindingSeverity.HALT,
            code="AUDIT_NULL_PROC_TIME",
            sheet="Routing",
            source_row=int(idx),
            item_code=str(row.get("routed_product", "")),
            message=(
                f"routed_product={row.get('routed_product')!r} "
                f"op_seq={row.get('operation_seq')} "
                f"op_name={row.get('operation_name')!r} has null proc_time. "
                "Planner must supply a value (Section 8.D — no silent default)."
            ),
            extras={"operation_seq": int(row.get("operation_seq"))
                    if pd.notna(row.get("operation_seq")) else None},
        ))


# Routing columns that define a scheduling operation. If these match across
# rows with the same (routed_product, op_seq), the duplicate is benign
# (same master compound used by several downstream products); we silently
# keep the canonical row. If they differ, surface a Warn.
_ROUTING_SCHED_FIELDS: tuple[str, ...] = (
    "department", "operation_name", "machines",
    "proc_time", "proc_time_UOM", "batch_size", "batch_UNIT",
)


def _check_routing_duplicate(routing: pd.DataFrame, findings: list[AuditFinding]) -> set[int]:
    """Section 9 #5 / L7 — duplicate (routed_product, operation_seq).

    Two cases handled separately:
      (a) is_primary != 1.0 with a primary present → drop the non-primary,
          emit a Warn per L7 (this is the EHT1000 case).
      (b) Multiple is_primary == 1.0 rows for the same key → if all share the
          scheduling fields (master compound reused by several downstreams),
          silently dedup to the canonical (lowest-index) row. If they
          disagree, surface a Warn and still keep the canonical row.

    Returns the set of pandas row indices to DROP.
    """
    drop_idx: set[int] = set()
    groups = routing.groupby(["routed_product", "operation_seq"], dropna=False)
    for (rp, seq), grp in groups:
        if len(grp) <= 1:
            continue
        primary_mask = grp["is_primary"] == 1.0
        primaries = grp[primary_mask]
        non_primaries = grp[~primary_mask]

        # (a) non-primary duplicates (L7)
        for idx in non_primaries.index:
            drop_idx.add(int(idx))
            findings.append(AuditFinding(
                severity=FindingSeverity.WARN,
                code="ROUTING_DUPLICATE_DROPPED",
                sheet="Routing",
                source_row=int(idx),
                item_code=str(rp),
                message=(
                    f"Duplicate routing row for "
                    f"(routed_product={rp!r}, operation_seq={seq}) has "
                    f"is_primary != 1.0; dropped per L7."
                ),
            ))

        # (b) collapse extra primary rows
        if len(primaries) <= 1:
            continue
        canonical_idx = int(primaries.index.min())
        sched_vals = primaries[list(_ROUTING_SCHED_FIELDS)].astype(str)
        all_agree = sched_vals.drop_duplicates().shape[0] == 1
        for idx in primaries.index:
            if idx == canonical_idx:
                continue
            drop_idx.add(int(idx))
            if not all_agree:
                findings.append(AuditFinding(
                    severity=FindingSeverity.WARN,
                    code="ROUTING_PRIMARY_CONFLICT",
                    sheet="Routing",
                    source_row=int(idx),
                    item_code=str(rp),
                    message=(
                        f"is_primary=1.0 row for (routed_product={rp!r}, "
                        f"operation_seq={seq}) disagrees on scheduling fields "
                        f"vs canonical (Excel row {canonical_idx + 2}). Keeping canonical."
                    ),
                ))
    return drop_idx


def _check_mixed_unit_aging(aging: pd.DataFrame, findings: list[AuditFinding]) -> None:
    """Section 9 #1 — Aging Master rows where MaxAgingUnit != MinAgingUnit.

    The normaliser still converts to minutes (Module 2). Surfaced as ONE
    aggregated Warn with item-code count and first 10 examples in `extras`
    — keeps the markdown report scannable.
    """
    both_present = aging["MaxAgingUnit"].notna() & aging["MinAgingUnit"].notna()
    mismatched = aging[both_present & (aging["MaxAgingUnit"] != aging["MinAgingUnit"])]
    if len(mismatched) == 0:
        return
    unique_items = sorted({str(x) for x in mismatched["ItemCode"]})
    findings.append(AuditFinding(
        severity=FindingSeverity.WARN,
        code="AGING_MIXED_UNITS",
        sheet=_AGING_SHEET,
        message=(
            f"{len(unique_items)} item code(s) have MinAgingUnit != MaxAgingUnit. "
            f"Normaliser converts to minutes downstream. "
            f"First 10: {unique_items[:10]}"
        ),
        extras={
            "unique_item_count": len(unique_items),
            "item_codes": unique_items,
        },
    ))


def _check_unknown_aging_units(aging: pd.DataFrame, findings: list[AuditFinding]) -> None:
    """Unknown aging unit string — not in the normaliser's accepted alias set.

    Aggregated to one Warn per unknown-unit value. Case-insensitive match
    against the alias set so 'Min', 'Hr', etc. are recognised.
    """
    known_lower = {u.lower() for u in _KNOWN_AGING_UNITS}
    bad_units: dict[str, set[str]] = {}
    for col in ("MinAgingUnit", "MaxAgingUnit"):
        for unit_val in aging[col].dropna().unique():
            if str(unit_val).strip().lower() in known_lower:
                continue
            items = sorted({str(x) for x in aging.loc[aging[col] == unit_val, "ItemCode"]})
            bad_units.setdefault(str(unit_val), set()).update(items)
    for unit_val, items in sorted(bad_units.items()):
        sorted_items = sorted(items)
        findings.append(AuditFinding(
            severity=FindingSeverity.WARN,
            code="AGING_UNKNOWN_UNIT",
            sheet=_AGING_SHEET,
            message=(
                f"Aging unit {unit_val!r} is not Days/Hours/Minutes. "
                f"Used by {len(sorted_items)} item(s). First 10: {sorted_items[:10]}"
            ),
            extras={"unit": unit_val, "item_codes": sorted_items},
        ))


def _check_null_transfer_time(routing: pd.DataFrame, settings: Settings,
                              findings: list[AuditFinding]) -> None:
    """Section 9 #3 — null transfer_time_min, fall back to plant default."""
    n = int(routing["transfer_time_min"].isna().sum())
    if n > 0:
        findings.append(AuditFinding(
            severity=FindingSeverity.WARN,
            code="ROUTING_NULL_TRANSFER_TIME",
            sheet="Routing",
            message=(
                f"{n} routing rows have null transfer_time_min; "
                f"defaulting to {settings.default_transfer_min} min per plant rule."
            ),
            extras={"count": n, "default_min": settings.default_transfer_min},
        ))


def _check_alt_machine_count(routing: pd.DataFrame,
                             findings: list[AuditFinding]) -> None:
    """Section 9 #6 — alt_machine_count column disagrees with parsed list.

    Per Section 8.F we ignore the column entirely; this surfaces the count.
    """
    routing_with_count = routing.copy()
    routing_with_count["_parsed_count"] = routing["machines"].apply(
        lambda v: len(parse_machines(v))
    )
    has_alt = routing_with_count["alt_machine_count"].notna()
    diff = routing_with_count[has_alt & (
        routing_with_count["alt_machine_count"].astype(float)
        != routing_with_count["_parsed_count"].astype(float)
    )]
    if len(diff) > 0:
        findings.append(AuditFinding(
            severity=FindingSeverity.WARN,
            code="ROUTING_ALT_MACHINE_COUNT_WRONG",
            sheet="Routing",
            message=(
                f"{len(diff)} routing rows have alt_machine_count != "
                f"len(parsed_machines). Column ignored per Section 8.F; "
                "using derived eligible_machine_count instead."
            ),
            extras={"count": int(len(diff))},
        ))


def _check_capstrip(routing: pd.DataFrame, settings: Settings,
                    findings: list[AuditFinding]) -> set[int]:
    """L12 — flag and DROP Capstrip routing rows.

    A row is Capstrip if its routed_product or finished_product_stock is in
    the configured exclusion list. Returns the set of indices to drop.
    """
    cap = settings.capstrip_items
    drop: set[int] = set()
    for idx, row in routing.iterrows():
        rp = str(row.get("routed_product", "")) if pd.notna(row.get("routed_product")) else ""
        fps = str(row.get("finished_product_stock", "")) if pd.notna(row.get("finished_product_stock")) else ""
        if rp in cap or fps in cap:
            drop.add(int(idx))
            findings.append(AuditFinding(
                severity=FindingSeverity.WARN,
                code="CAPSTRIP_ROUTING_DROPPED",
                sheet="Routing",
                source_row=int(idx),
                item_code=rp or fps,
                message=(
                    f"Capstrip routing row dropped per L12 "
                    f"(routed_product={rp!r}, finished_product_stock={fps!r})."
                ),
            ))
    return drop


def _check_pilot_master_presence(
    settings: Settings,
    aging_dedup: pd.DataFrame,
    itemtype_dedup: pd.DataFrame,
    findings: list[AuditFinding],
) -> None:
    """Section 9 #8 — HALT if any of the mandatory pilot items is missing from
    Aging Master or ItemType Master.

    Mandatory set = Green Tyre + 8 in-scope components (pilot.yaml).
    Master compounds + deeper items are validated later when the BOM walker
    runs (Modules 3-4).
    """
    aging_ids = set(aging_dedup["ItemCode"].astype(str))
    itype_ids = set(itemtype_dedup["ItemCode"].astype(str))
    mandatory: list[str] = [settings.green_tyre_code, *settings.green_tyre_components]
    for item in mandatory:
        if item not in aging_ids:
            findings.append(AuditFinding(
                severity=FindingSeverity.HALT,
                code="AUDIT_MISSING_AGING",
                sheet=_AGING_SHEET,
                item_code=item,
                message=f"Pilot item {item!r} is missing from Aging Master.",
            ))
        if item not in itype_ids:
            findings.append(AuditFinding(
                severity=FindingSeverity.HALT,
                code="AUDIT_MISSING_ITEMTYPE",
                sheet=_ITEMTYPE_SHEET,
                item_code=item,
                message=f"Pilot item {item!r} is missing from ItemType Master.",
            ))


def _check_pilot_curing_present(
    settings: Settings, curing: pd.DataFrame, findings: list[AuditFinding]
) -> None:
    """Sanity: pilot SKU has rows in the curing schedule."""
    if len(curing) == 0:
        findings.append(AuditFinding(
            severity=FindingSeverity.HALT,
            code="AUDIT_NO_CURING_ROWS",
            sheet="Curing",
            item_code=settings.sku_code,
            message=(
                f"Curing schedule has zero rows for SKU={settings.sku_code!r}. "
                "Cannot proceed."
            ),
        ))


# --- Cleaners --------------------------------------------------------------

def _clean_routing(
    routing: pd.DataFrame, drop_idx: set[int], settings: Settings
) -> pd.DataFrame:
    """Apply machine parsing, drop rows in `drop_idx`, attach
    `machines_list` and `eligible_machine_count`. Sort deterministically.
    """
    kept = routing.drop(index=sorted(drop_idx)).reset_index(drop=True).copy()
    kept["machines_list"] = kept["machines"].apply(parse_machines)
    kept["eligible_machine_count"] = kept["machines_list"].apply(len)
    # CSV-friendly representation of the list
    kept["machines_normalised"] = kept["machines_list"].apply(join_machines)
    kept = kept.sort_values(
        by=["routed_product", "operation_seq"], kind="stable"
    ).reset_index(drop=True)
    return kept


def _dedup_aging(aging: pd.DataFrame, findings: list[AuditFinding]) -> pd.DataFrame:
    """Collapse duplicate ItemCode rows. Conflicting (min, max, unit) tuples
    are aggregated into one Warn with the conflicting item codes listed in
    `extras` to keep the markdown report scannable.
    """
    aging_sorted = aging.sort_values(by="ItemCode", kind="stable")
    groups = aging_sorted.groupby("ItemCode", dropna=False, sort=False)
    rows: list[pd.Series] = []
    conflicting_items: list[str] = []
    for item, grp in groups:
        if len(grp) > 1:
            uniq = grp[["MinAging", "MaxAging", "MinAgingUnit", "MaxAgingUnit"]].drop_duplicates()
            if len(uniq) > 1:
                conflicting_items.append(str(item))
        rows.append(grp.iloc[0])
    if conflicting_items:
        findings.append(AuditFinding(
            severity=FindingSeverity.WARN,
            code="AGING_CONFLICTING_DUPLICATES",
            sheet=_AGING_SHEET,
            message=(
                f"{len(conflicting_items)} item code(s) have multiple Aging Master rows "
                f"with conflicting (min, max, unit) values. Keeping first per ItemCode. "
                f"First 10: {sorted(conflicting_items)[:10]}"
            ),
            extras={"item_codes": sorted(conflicting_items)},
        ))
    return pd.DataFrame(rows).reset_index(drop=True)


def _dedup_itemtype(itemtype: pd.DataFrame, findings: list[AuditFinding]) -> pd.DataFrame:
    """Collapse duplicate ItemCode rows. Conflicting types aggregated to one Warn."""
    sorted_df = itemtype.sort_values(by="ItemCode", kind="stable")
    groups = sorted_df.groupby("ItemCode", dropna=False, sort=False)
    rows: list[pd.Series] = []
    conflicting_items: list[str] = []
    for item, grp in groups:
        if len(grp) > 1:
            uniq = grp["ItemType"].dropna().drop_duplicates()
            if len(uniq) > 1:
                conflicting_items.append(str(item))
        rows.append(grp.iloc[0])
    if conflicting_items:
        findings.append(AuditFinding(
            severity=FindingSeverity.WARN,
            code="ITEMTYPE_CONFLICTING_DUPLICATES",
            sheet=_ITEMTYPE_SHEET,
            message=(
                f"{len(conflicting_items)} item code(s) have multiple ItemType rows "
                f"with conflicting ItemType values. Keeping first. "
                f"First 10: {sorted(conflicting_items)[:10]}"
            ),
            extras={"item_codes": sorted(conflicting_items)},
        ))
    return pd.DataFrame(rows).reset_index(drop=True)


def _clean_bom_strings(
    bom: pd.DataFrame, findings: list[AuditFinding]
) -> pd.DataFrame:
    """Fix mojibake in BOM string columns (Output, input code, Input ItemType).

    Observed: 'CPJ1218-162MM/29Â°' (UTF-8 `°` misread as Latin-1) appears as
    a producer-side string in BOM row 10, while the clean form
    'CPJ1218-162MM/29°' is used everywhere else. Without this fix, the
    graph would have two distinct nodes for the same item.
    """
    cleaned = bom.copy()
    affected: list[tuple[int, str, str, str]] = []
    for col in ("Output", "input code", "Input ItemType"):
        if col not in cleaned.columns:
            continue
        for idx, val in cleaned[col].items():
            new_val = _fix_mojibake(val)
            if isinstance(val, str) and new_val != val:
                affected.append((int(idx), col, val, str(new_val)))
                cleaned.at[idx, col] = new_val
    if affected:
        findings.append(AuditFinding(
            severity=FindingSeverity.WARN,
            code="BOM_ENCODING_FIX",
            sheet=f"BOM",
            message=(
                f"{len(affected)} BOM string(s) had mojibake (e.g. 'Â°' → '°'); "
                f"normalised to canonical unicode. First: pandas row "
                f"{affected[0][0]}, column={affected[0][1]!r}, "
                f"{affected[0][2]!r} → {affected[0][3]!r}."
            ),
            extras={"affected": affected},
        ))
    return cleaned


def _scope_curing_to_pilot(curing: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    mask = curing["SKUCode"].astype(str) == settings.sku_code
    out = curing[mask].copy()
    # Parse datetimes — date format in the source is M/D/YYYY HH:MM (US).
    for col in ("StartTime", "EndTime"):
        out[col] = pd.to_datetime(out[col], format="%m/%d/%Y %H:%M", errors="coerce")
    # Machine + SKUCode forced to string per L23.
    out["Machine"] = out["Machine"].astype(str)
    out["SKUCode"] = out["SKUCode"].astype(str)
    return out.sort_values("StartTime", kind="stable").reset_index(drop=True)


# --- Public entry ----------------------------------------------------------

def run(
    input_dir: Path, settings: Settings, curing_file: Path | None = None,
) -> AuditResult:
    """Run the audit pass.

    Always returns an AuditResult. The bootstrap inspects `result.halt_findings`
    and decides whether to halt (write report, exit non-zero) or continue.

    `curing_file` (optional) overrides the default
    `<input_dir>/BTP_PCR_May_Curing_Schedule.csv`. Accepts `.csv` or `.xlsx`.
    """
    raw = _load_inputs(input_dir, settings.sku_code, curing_file=curing_file)
    findings: list[AuditFinding] = []

    # Curing — pilot scope
    curing_pilot = _scope_curing_to_pilot(raw["curing"], settings)
    _check_pilot_curing_present(settings, curing_pilot, findings)

    # Routing — findings on the raw frame, then clean
    _check_null_proc_time(raw["routing"], findings)
    dup_drop = _check_routing_duplicate(raw["routing"], findings)
    capstrip_drop = _check_capstrip(raw["routing"], settings, findings)
    _check_null_transfer_time(raw["routing"], settings, findings)
    _check_alt_machine_count(raw["routing"], findings)
    routing_cleaned = _clean_routing(
        raw["routing"], dup_drop | capstrip_drop, settings
    )

    # BOM — fix mojibake before anything downstream reads the strings.
    bom_cleaned = _clean_bom_strings(raw["bom"], findings)

    # Aging — findings, then dedup
    _check_mixed_unit_aging(raw["aging"], findings)
    _check_unknown_aging_units(raw["aging"], findings)
    aging_dedup = _dedup_aging(raw["aging"], findings)
    itemtype_dedup = _dedup_itemtype(raw["itemtype"], findings)
    _check_pilot_master_presence(settings, aging_dedup, itemtype_dedup, findings)

    return AuditResult(
        curing_df=curing_pilot,
        routing_df=raw["routing"],
        routing_cleaned_df=routing_cleaned,
        bom_df=bom_cleaned,
        aging_df=aging_dedup,
        itemtype_df=itemtype_dedup,
        mpq_df=raw["mpq"],
        findings=findings,
    )
