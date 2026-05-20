"""Writes audit_report.md + routing_cleaned.csv.

The report is written on EVERY run, including HALT runs (so the user sees
the binding finding). routing_cleaned.csv is also written on HALT runs as
a debugging artefact — but schedule.csv and the rest of the pipeline
outputs are skipped per the bootstrap's HALT handling.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Iterable

from V1.config.enums import FindingSeverity
from V1.models.finding import AuditFinding
from V1.routes.audit import AuditResult


def _summarise_finding_counts(findings: Iterable[AuditFinding]) -> str:
    sev_counter: Counter[str] = Counter()
    code_counter: Counter[str] = Counter()
    for f in findings:
        sev_counter[f.severity.value] += 1
        code_counter[f"{f.severity.value}/{f.code}"] += 1
    lines = [
        f"- **HALT**: {sev_counter.get(FindingSeverity.HALT.value, 0)}",
        f"- **WARN**: {sev_counter.get(FindingSeverity.WARN.value, 0)}",
        "",
        "Breakdown by code:",
    ]
    for code, n in sorted(code_counter.items()):
        lines.append(f"- `{code}` × {n}")
    return "\n".join(lines)


def _section(title: str, findings: list[AuditFinding]) -> str:
    if not findings:
        return f"## {title}\n\n_None._\n"
    out = [f"## {title}", ""]
    for f in findings:
        out.append(f"- {f.to_md_line()}")
    out.append("")
    return "\n".join(out)


def write(result: AuditResult, output_dir: Path) -> None:
    """Write audit_report.md and routing_cleaned.csv into `output_dir`.

    `output_dir` is expected to already exist (created by run_context).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_routing_cleaned(result, output_dir / "routing_cleaned.csv")
    _write_audit_report(result, output_dir / "audit_report.md")


def _write_routing_cleaned(result: AuditResult, path: Path) -> None:
    """Write the cleaned routing as CSV. machines_list column is dropped in
    favour of the pipe-joined `machines_normalised` for CSV-friendliness.
    """
    df = result.routing_cleaned_df.drop(columns=["machines_list"], errors="ignore")
    df.to_csv(path, index=False)


def _write_audit_report(result: AuditResult, path: Path) -> None:
    halts = result.halt_findings
    warns = result.warn_findings

    overall = "HALT" if halts else ("WARN" if warns else "CLEAN")

    lines: list[str] = [
        "# Audit report",
        "",
        f"**Overall status:** {overall}",
        "",
        "## Summary",
        "",
        _summarise_finding_counts(result.findings),
        "",
        "## Dataset row counts",
        "",
        f"- Pilot curing rows: {len(result.curing_df)}",
        f"- Raw routing rows: {len(result.routing_df)}",
        f"- Cleaned routing rows: {len(result.routing_cleaned_df)}",
        f"- BOM rows: {len(result.bom_df)}",
        f"- Aging Master rows (deduped): {len(result.aging_df)}",
        f"- ItemType Master rows (deduped): {len(result.itemtype_df)}",
        f"- MPQ rows: {len(result.mpq_df)}",
        "",
        _section("HALT findings", halts),
        _section("WARN findings", warns),
    ]
    path.write_text("\n".join(lines))
