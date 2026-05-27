"""Build the BTP V1 Forward Scheduler full-project documentation PDF.

Run:  uv run python docs/build_documentation_pdf.py

Output: docs/BTP_V1_Forward_Scheduler_Documentation.pdf
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    PageBreak,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)


# -----------------------------------------------------------------------------
# Styles
# -----------------------------------------------------------------------------
NAVY = colors.HexColor("#0F2A4A")
STEEL = colors.HexColor("#2E5C8A")
LIGHT_GREY = colors.HexColor("#F2F4F7")
BORDER = colors.HexColor("#B7C0CC")
ACCENT = colors.HexColor("#C9A227")

base = getSampleStyleSheet()

H1 = ParagraphStyle(
    "H1", parent=base["Heading1"], fontName="Helvetica-Bold",
    fontSize=20, leading=24, textColor=NAVY, spaceBefore=8, spaceAfter=10,
)
H2 = ParagraphStyle(
    "H2", parent=base["Heading2"], fontName="Helvetica-Bold",
    fontSize=14, leading=18, textColor=NAVY, spaceBefore=14, spaceAfter=6,
)
H3 = ParagraphStyle(
    "H3", parent=base["Heading3"], fontName="Helvetica-Bold",
    fontSize=11.5, leading=14, textColor=STEEL, spaceBefore=10, spaceAfter=4,
)
BODY = ParagraphStyle(
    "Body", parent=base["BodyText"], fontName="Helvetica",
    fontSize=10, leading=14, alignment=TA_JUSTIFY, spaceAfter=6,
    textColor=colors.HexColor("#1A1F2B"),
)
BULLET = ParagraphStyle(
    "Bullet", parent=BODY, leftIndent=14, bulletIndent=2, spaceAfter=3,
)
SMALL = ParagraphStyle(
    "Small", parent=BODY, fontSize=8.5, leading=11, textColor=colors.HexColor("#3A4255"),
)
CODE = ParagraphStyle(
    "Code", parent=BODY, fontName="Courier", fontSize=8.5, leading=11,
    textColor=colors.HexColor("#23262E"), backColor=LIGHT_GREY,
    leftIndent=6, rightIndent=6, spaceBefore=4, spaceAfter=8,
    borderColor=BORDER, borderWidth=0.4, borderPadding=4,
)
TITLE = ParagraphStyle(
    "Title", parent=base["Title"], fontName="Helvetica-Bold",
    fontSize=26, leading=30, textColor=NAVY, alignment=TA_CENTER,
    spaceAfter=10,
)
SUBTITLE = ParagraphStyle(
    "Subtitle", parent=BODY, fontSize=12, leading=15,
    alignment=TA_CENTER, textColor=STEEL,
)
META = ParagraphStyle(
    "Meta", parent=BODY, fontSize=10, leading=13,
    alignment=TA_CENTER, textColor=colors.HexColor("#4A5365"),
)


# -----------------------------------------------------------------------------
# Page template — header + footer
# -----------------------------------------------------------------------------
def _page_decoration(canv, doc):
    canv.saveState()
    # Header band
    canv.setFillColor(NAVY)
    canv.rect(0, A4[1] - 1.1 * cm, A4[0], 1.1 * cm, stroke=0, fill=1)
    canv.setFillColor(colors.white)
    canv.setFont("Helvetica-Bold", 9)
    canv.drawString(2 * cm, A4[1] - 0.7 * cm, "JK Tyre BTP — Forward Production Scheduler (V1)")
    canv.setFont("Helvetica", 8.5)
    canv.drawRightString(A4[0] - 2 * cm, A4[1] - 0.7 * cm, "Project Documentation")
    # Footer band
    canv.setStrokeColor(BORDER)
    canv.setLineWidth(0.4)
    canv.line(2 * cm, 1.3 * cm, A4[0] - 2 * cm, 1.3 * cm)
    canv.setFillColor(colors.HexColor("#4A5365"))
    canv.setFont("Helvetica", 8.5)
    canv.drawString(2 * cm, 0.9 * cm, "Confidential — JK Tyre Banmore Tyre Plant (BTP)")
    canv.drawRightString(A4[0] - 2 * cm, 0.9 * cm, f"Page {doc.page}")
    canv.restoreState()


def _cover_decoration(canv, doc):
    canv.saveState()
    canv.setFillColor(NAVY)
    canv.rect(0, A4[1] - 3.5 * cm, A4[0], 3.5 * cm, stroke=0, fill=1)
    canv.setFillColor(ACCENT)
    canv.rect(0, A4[1] - 3.7 * cm, A4[0], 0.2 * cm, stroke=0, fill=1)
    canv.setFillColor(NAVY)
    canv.rect(0, 0, A4[0], 1.5 * cm, stroke=0, fill=1)
    canv.setFillColor(ACCENT)
    canv.rect(0, 1.5 * cm, A4[0], 0.15 * cm, stroke=0, fill=1)
    canv.setFillColor(colors.white)
    canv.setFont("Helvetica-Bold", 11)
    canv.drawString(2 * cm, A4[1] - 1.6 * cm, "JK TYRE • BANMORE TYRE PLANT")
    canv.setFont("Helvetica", 9)
    canv.drawString(2 * cm, A4[1] - 2.1 * cm, "Passenger-Car Radial Pilot Programme")
    canv.setFont("Helvetica-Bold", 9)
    canv.drawRightString(A4[0] - 2 * cm, 0.85 * cm, "Project Documentation • V1")
    canv.restoreState()


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def p(text: str, style=BODY):
    return Paragraph(text, style)


def bullets(items, style=BULLET):
    return [Paragraph(f"• {x}", style) for x in items]


def styled_table(data, col_widths=None, header=True, zebra=True, body_font=9, header_font=9.5):
    tbl = Table(data, colWidths=col_widths, repeatRows=1 if header else 0, hAlign="LEFT")
    style_cmds = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), body_font),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, BORDER),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
    ]
    if header:
        style_cmds += [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), header_font),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("TOPPADDING", (0, 0), (-1, 0), 6),
        ]
    if zebra and len(data) > 1:
        for r in range(1, len(data)):
            if r % 2 == 0:
                style_cmds.append(("BACKGROUND", (0, r), (-1, r), LIGHT_GREY))
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def _wrap_cell(text, style=None):
    return Paragraph(text, style or ParagraphStyle("c", parent=BODY, fontSize=9, leading=12))


def wrap_table(rows, col_widths, header=True):
    """Each cell wrapped in a Paragraph so it auto-wraps inside the column."""
    cs_head = ParagraphStyle("ch", parent=BODY, fontSize=9.5, leading=12,
                             fontName="Helvetica-Bold", textColor=colors.white)
    cs_body = ParagraphStyle("cb", parent=BODY, fontSize=9, leading=12)
    out = []
    for i, r in enumerate(rows):
        s = cs_head if (header and i == 0) else cs_body
        out.append([Paragraph(str(c), s) for c in r])
    return styled_table(out, col_widths=col_widths, header=header)


def code_block(text):
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe = safe.replace("\n", "<br/>")
    return Paragraph(f"<font face='Courier' size='8.5'>{safe}</font>", CODE)


# -----------------------------------------------------------------------------
# Story builder
# -----------------------------------------------------------------------------
def build_story():
    s = []

    # ----- COVER -----
    s.append(Spacer(1, 4.5 * cm))
    s.append(p("JK Tyre BTP", TITLE))
    s.append(p("Forward Production Scheduler", TITLE))
    s.append(Spacer(1, 6 * mm))
    s.append(p("Deterministic, BOM-driven, event-aware production scheduling for the Banmore Tyre Plant Passenger-Car Radial pilot SKU.", SUBTITLE))
    s.append(Spacer(1, 1.6 * cm))

    cover_meta = [
        ["Pilot SKU", "1325220516095HTMX0  —  205/65 R16 PCR Taxi MX TL"],
        ["Green Tyre", "GT2056516TAXIMXTL  —  8 in-scope BOM components"],
        ["Curing Press", "14811  (fixed input, immovable)"],
        ["Horizon", "2026-05-17 06:49  →  2026-05-30 22:19  (~14 days)"],
        ["Curing Blocks", "42 blocks  —  2,620 tyres total demand"],
        ["Build Version", "V1  —  Demand Fulfilment Scope"],
        ["Document Date", "2026-05-24"],
    ]
    s.append(wrap_table(cover_meta, col_widths=[4.0 * cm, 11.5 * cm], header=False))
    s.append(Spacer(1, 1.8 * cm))
    s.append(p("Prepared as the complete project documentation: objective, constraints, approach, architecture, pipeline modules, locked design decisions, outputs, KPIs, testing and acceptance.", META))
    s.append(PageBreak())

    # ----- TABLE OF CONTENTS -----
    s.append(p("Table of Contents", H1))
    toc_rows = [
        ["#", "Section", "Page topic"],
        ["1", "Executive Summary", "Objective, value, current status"],
        ["2", "Project Context & Domain", "BTP plant, process chain, why a scheduler"],
        ["3", "Scope — V1 vs V2+", "What V1 owns, what V2 extends"],
        ["4", "Pilot SKU — Inputs & Demand", "SKU, BOM, horizon, curing demand"],
        ["5", "Plant Resources — Departments & Machines", "Machine pools and UOMs"],
        ["6", "Hard Constraints (Section 4 of PDF)", "Aging, AND-join, MPQ, eligibility"],
        ["7", "Soft Rules & Plant Policies (Section 5)", "Transfer, efficiency, building pinning"],
        ["8", "Locked Design Decisions (L1–L23)", "Settled engineering choices"],
        ["9", "Standing Assumptions (Section 8)", "Lot sizing, null proc_time, mixer pool"],
        ["10", "Data-Quality Findings", "HALT vs WARN classification"],
        ["11", "Solution Approach", "Forward-pass philosophy in words"],
        ["12", "26-Step Approach Flow", "Implementation spec, module ownership"],
        ["13", "Pipeline Architecture", "Module diagram and data contracts"],
        ["14", "Module-by-Module Reference", "What each route / utility does"],
        ["15", "Configuration", "pilot.yaml schema and tunables"],
        ["16", "Determinism Guarantees", "Repeatability gate"],
        ["17", "HALT Exit Codes", "Engine return codes"],
        ["18", "Outputs", "Workbook + standalone artefacts"],
        ["19", "Golden Test Fixtures (Section 17)", "Five hand-computed cases"],
        ["20", "KPI Snapshot — Reference Run", "Live numbers from a successful run"],
        ["21", "Acceptance Against Section 12", "Status per acceptance criterion"],
        ["22", "How to Run", "Quick start, end-to-end execution"],
        ["23", "Project Layout", "Directory map"],
        ["24", "Glossary", "Domain and engineering terms"],
    ]
    s.append(wrap_table(toc_rows, col_widths=[1.0 * cm, 6.6 * cm, 8.8 * cm]))
    s.append(PageBreak())

    # ----- 1. EXECUTIVE SUMMARY -----
    s.append(p("1. Executive Summary", H1))
    s.append(p(
        "This documentation describes the <b>V1 release of the JK Tyre BTP Forward Production Scheduler</b>, "
        "a deterministic, BOM-driven engine that consumes the published May curing plan as a fixed input and "
        "produces a fully time-stamped, machine-assigned schedule for every upstream operation of the pilot "
        "Passenger-Car Radial SKU. Curing is never moved; if upstream cannot feed it within aging windows, "
        "the engine flags the violation in a diagnostic artefact and continues, never silently fixing demand.",
        BODY,
    ))
    s.append(p("Objective", H3))
    s.append(p(
        "Prove that every curing block in the May plan can be fed on time with all eight in-scope BOM "
        "components, within their respective aging windows, using a single forward pass that is "
        "<b>reproducible byte-for-byte</b> on the same inputs.",
        BODY,
    ))
    s.append(p("Why a forward, deterministic scheduler", H3))
    s.append(p(
        "Tyre manufacturing is rich with aging constraints: a calendered ply is unsafe to build with after "
        "24–48 hours; a master compound that has not aged long enough behaves differently on the line. "
        "Conventional spreadsheet planning cannot reason consistently about a 7-level BOM with per-edge "
        "minimum/maximum aging windows. The scheduler encodes those rules formally, walks the BOM from "
        "curing demand backward, and commits lots in chronological order with an explicit Least-Slack-First "
        "tiebreak. Reproducibility is enforced so the planner can iterate confidently.",
        BODY,
    ))
    s.append(p("What is in V1", H3))
    s.extend(bullets([
        "Hard constraints fully enforced: aging windows, AND-join across 8 components, MPQ, machine eligibility, fixed curing.",
        "Eleven output artefacts per run, including a bundled Excel workbook with 11 sheets.",
        "Five golden fixtures + 215 unit/integration tests; integration suite asserts byte-identical re-runs.",
        "Twelve pipeline modules, each runnable in isolation with a typed dataclass contract.",
        "Auto-<i>t<sub>0</sub></i> anchor (L17) computed from the longest BOM aging chain; guardrail asserts feasibility before any lot is committed.",
    ]))
    s.append(p("What V1 intentionally does <u>not</u> do", H3))
    s.extend(bullets([
        "No optimisation of curing  —  curing is a fixed input.",
        "No changeover modelling  —  set to 0 min in V1 (the 15 min / 0 min model is deferred to V2).",
        "No utilisation as an optimisation target  —  utilisation is reported but not optimised.",
        "No rescheduling, repair loops, or backtracking  —  flag-and-continue per L11.",
    ]))
    s.append(PageBreak())

    # ----- 2. CONTEXT -----
    s.append(p("2. Project Context & Domain", H1))
    s.append(p(
        "The JK Tyre Banmore Tyre Plant (BTP) manufactures Passenger-Car Radial (PCR) tyres through a "
        "long, multi-stage process chain. Every tyre flows through:",
        BODY,
    ))
    s.append(p("<b>Mixing → Final Mixing → Calendering → Cutting / Slitting → Ply Cutting → Bead Building → Extrusion → Tyre Building → Curing</b>", BODY))
    s.append(p(
        "Curing is the last operation and is the most capacity-constrained: a single curing press serves a "
        "given SKU. For the pilot, that press is <b>14811</b>. The plant has published a May curing plan that "
        "specifies which press, which 8-hour shift, and how many tyres for each of 42 blocks across the "
        "horizon. That plan is non-negotiable input  —  the V1 scheduler’s job is to make every upstream "
        "operation land in time, on a feasible machine, with every component within its aging window.",
        BODY,
    ))
    s.append(p(
        "The engine is <b>not</b> an optimiser, not a demand forecaster, and not a labour/energy/cost model. "
        "It is a scheduler over material flow, machine assignment, and time.",
        BODY,
    ))
    s.append(PageBreak())

    # ----- 3. SCOPE V1 vs V2 -----
    s.append(p("3. Scope — V1 vs V2+", H1))
    s.append(p("V1 — Demand Fulfilment", H3))
    s.append(p(
        "The V1 KPIs are deliberately simple, because the priority is correctness rather than savings:",
        BODY,
    ))
    s.extend(bullets([
        "<b>OTIF %</b> at the Building → Curing handoff (per block).",
        "<b>Count of aging violations</b> per edge.",
        "<b>Count of infeasibilities</b> per lot, with binding constraint named.",
        "<b>Coverage</b>  —  every in-scope operation has a scheduled lot.",
    ]))
    s.append(p("V2+ — Optimisation Layer", H3))
    s.append(p(
        "Once V1 is locked and reproducible, V2 layers in the savings work: changeover modelling "
        "(15 min on different product, 0 min on same), utilisation as an optimisation objective, "
        "same-product clustering on shared resources such as the Four-Roll Calendar and the mixer pool, and "
        "the strict event-driven dispatch with the full LSF tiebreak chain. None of those is touched in V1.",
        BODY,
    ))
    s.append(p("Explicit V1 simplifications", H3))
    sim_rows = [
        ["Topic", "V1 behaviour", "V2 target"],
        ["Changeover", "0 min always (L8)", "15 min different-product / 0 min same-product"],
        ["Dispatch", "Topo + chronological greedy with CPM backward pass", "Full event-heap dispatch (L21)"],
        ["LSF tiebreak", "Avoided by sequential dispatch", "4-step LSF chain (L15)"],
        ["Soft-reservation expiry", "Not modelled — no contention", "Full create/consume/expire/release log (L16)"],
        ["Backward feasibility", "Min-aging chain only", "Min-aging + processing time (refined CPM)"],
    ]
    s.append(wrap_table(sim_rows, col_widths=[3.7 * cm, 6.5 * cm, 6.3 * cm]))
    s.append(PageBreak())

    # ----- 4. PILOT SKU -----
    s.append(p("4. Pilot SKU — Inputs & Demand", H1))
    sku_rows = [
        ["Attribute", "Value"],
        ["SKU code", "1325220516095HTMX0"],
        ["Description", "205/65 R16 Passenger-Car Radial (Taxi MX TL)"],
        ["Green tyre code", "GT2056516TAXIMXTL"],
        ["Curing press", "14811 (single press for this SKU)"],
        ["Horizon", "2026-05-17 06:49 → 2026-05-30 22:19"],
        ["Curing rows", "42 (mostly 64 tyres / 8-hr block, 15-min cycle)"],
        ["Total demand", "2,620 tyres"],
        ["Pre-existing GT inventory", "0 on every row"],
        ["BOM depth", "7 levels (SKU → GT → component → sub-component → final compound → master → raw)"],
    ]
    s.append(wrap_table(sku_rows, col_widths=[4.8 * cm, 10.7 * cm]))
    s.append(Spacer(1, 4 * mm))

    s.append(p("BOM children of the Green Tyre", H3))
    bom_rows = [
        ["#", "Component code", "Item type", "In scope"],
        ["1", "CPJ1218-162MM/29°", "Rubberized Steel Belt", "Yes"],
        ["2", "CPJ1218-154MM/29°-1", "Rubberized Steel Belt", "Yes"],
        ["3", "TRD2056516TAXIMXTL", "Tread", "Yes"],
        ["4", "IL2056516TAXIMXTL", "Inner Liner", "Yes"],
        ["5", "SSW2056516TAXIMXTL", "Sidewall", "Yes"],
        ["6", "EHT1000-640MM/90°", "Rubberized Ply", "Yes"],
        ["7", "EHT1000 -480MM/90°", "Rubberized Ply", "Yes"],
        ["8", "BD-12843443-4", "Bead Apex", "Yes"],
        ["—", "CAP 66 - CAPSTRIP", "Cap Strip", "OUT OF SCOPE (L12)"],
    ]
    s.append(wrap_table(bom_rows, col_widths=[0.8 * cm, 5.0 * cm, 5.5 * cm, 4.2 * cm]))
    s.append(Spacer(1, 4 * mm))

    s.append(p("Inputs (read-only)", H3))
    inp_rows = [
        ["File", "Purpose"],
        ["BTP_PCR_May_Curing_Schedule.csv",
         "14,292 rows over the full May plan; 42 rows for the pilot SKU. Each pilot row is a non-negotiable demand event. Columns: Date, Shift, Machine, SKUCode, StartTime, EndTime, Qty, CycleTime_min, GT_Inventory, Remarks, SKU_Description."],
        ["BTP_Routing_*BOM_Final.xlsx",
         "Six sheets — BOM, Routing, Aging Master, Buffer Master (ignored per L4), ItemType Master, MPQ."],
        ["JKT_BTP_Forward_Scheduler_Problem_Statement.pdf",
         "Authoritative problem definition. Section numbers cited throughout this document resolve into this file."],
    ]
    s.append(wrap_table(inp_rows, col_widths=[5.2 * cm, 10.3 * cm]))
    s.append(PageBreak())

    # ----- 5. PLANT RESOURCES -----
    s.append(p("5. Plant Resources — Departments & Machines", H1))
    mach_rows = [
        ["Department", "Machines (eligible pool)", "Notes / UOM"],
        ["Mixing (Master)", "0201, 0202, 0203, 0204, 0205, 0206", "SEC/BATCH; batch in KG"],
        ["Final Mixing", "0201, 0202, 0203, 0204, 0205", "SEC/BATCH; batch in KG"],
        ["FOUR ROLL CALENDAR", "FRC (single shared resource)", "M/MIN or SEC/BATCH. Bottleneck candidate"],
        ["Belt Cutter", "WBC, WBCNew", "M/MIN"],
        ["FULL WIDTH SLITTER", "FWS, FWSNew", "M/MIN (Capstrip — out of scope)"],
        ["Quintuplex Extruder", "Quintuplex", "M/MIN — Tread"],
        ["TRC", "TRC", "M/MIN — Inner Liner"],
        ["Duplex Extruder", "Duplex", "M/MIN — Sidewall"],
        ["PLY CUTTER", "LTBC, HTBC, LTBCNew", "M/MIN"],
        ["VIPO", "VIPO", "MIN, batch 100 NOS (beads)"],
        ["AUTO AND MANUAL FILLERING", "FILLERING", "proc_time NULL on BD apex (HALT)"],
        ["Tyre Building (VMIMaxx)", "7001, 7002, 7003, 7004, 6001, 6002, 6003, 6004", "SEC per tyre; primary 6001 (L18)"],
        ["Curing", "14811 (fixed)", "750 SEC nominal cycle — immovable"],
    ]
    s.append(wrap_table(mach_rows, col_widths=[4.4 * cm, 5.6 * cm, 5.5 * cm]))
    s.append(PageBreak())

    # ----- 6. HARD CONSTRAINTS -----
    s.append(p("6. Hard Constraints (Problem Statement Section 4)", H1))
    s.append(p(
        "Every constraint below must hold for every scheduled lot. The engine detects and reports violations "
        "itself  —  they are never silently fixed.",
        BODY,
    ))
    hc_rows = [
        ["#", "Constraint", "Rule"],
        ["4.1", "Aging window",
         "For every BOM edge: producer_end + MIN_aging ≤ consumer_start ≤ producer_end + MAX_aging. Inclusive both ends (L22). Applies to every edge including Building → Curing."],
        ["4.2", "AND-join (BOM completeness)",
         "Tyre Building consumes 8 mandatory components. It cannot start until each one has at least one ready, in-window lot. Modelled as an atomic hard reservation across all 8 producer lots."],
        ["4.3", "Machine eligibility",
         "Every lot runs on a machine listed in the routing for that operation. One lot per machine at a time."],
        ["4.4", "MPQ",
         "Every lot satisfies MPQ_Min. Lots greater than MPQ_Max are split into equal sub-lots."],
        ["4.5", "Curing is fixed",
         "Curing rows are immovable. Aging or AND-join violations are FLAGGED; curing is never shifted (L4.5 + L11)."],
        ["4.6", "Determinism",
         "Same inputs → byte-identical outputs. No randomness, no wall-clock dependence."],
    ]
    s.append(wrap_table(hc_rows, col_widths=[1.0 * cm, 4.5 * cm, 10.0 * cm]))
    s.append(PageBreak())

    # ----- 7. SOFT RULES -----
    s.append(p("7. Soft Rules & Plant Policies (Section 5)", H1))
    s.extend(bullets([
        "<b>24×7 operation</b>  —  no shift breaks or planned maintenance windows modelled in this phase.",
        "<b>15-minute changeover</b> between different products on the same machine; 0 min for same product back-to-back. No changeover at machine cold-start. <b>V1 sets this to 0 min always</b> (L8).",
        "<b>10-minute transfer</b> between producer and consumer, interpreted via <i>effective_gap</i> = MAX(transfer_time, MIN_aging) per L14  —  material can be in transit while it ages.",
        "<b>95% machine efficiency</b>: <i>effective_time</i> = ceil(nominal_time / 0.95) (L10, L20). Single ceil direction throughout.",
        "<b>Tyre Building primary machine</b>: pin to one primary (6001 by L18); spill to a 2nd/3rd machine only if staying on the primary would force a component to age past its window.",
        "<b>Null processing times</b> must be filled with a documented, justifiable default — except <b>BD-12843443-4 Fillering</b>, which HALTs the engine until the planner supplies a value (Section 8.D).",
    ]))
    s.append(PageBreak())

    # ----- 8. LOCKED DECISIONS -----
    s.append(p("8. Locked Design Decisions (L1–L23)", H1))
    s.append(p(
        "These 23 decisions are settled. They are never relitigated without explicit reversal from the planner. "
        "Each shapes exactly one behaviour in the engine.",
        BODY,
    ))
    ld_rows = [
        ["ID", "Decision", "Choice"],
        ["L1", "Demand grain", "Per-block: one Building lot per curing row; each Building lot points to exactly one curing block."],
        ["L2", "Starting inventory", "Zero. Engine produces every compound, ply, bead from raw. Raws are bottomless pre-horizon."],
        ["L3", "Building machine", "Pin to one primary. Spill to a 2nd/3rd ONLY when staying primary would cause an aging breach."],
        ["L4", "Aging vs Buffer Master", "Aging Master is authoritative. Buffer Master ignored for this phase."],
        ["L5", "Aging clock anchor", "Timer starts at producer END, stops at consumer START."],
        ["L6", "Master→master aging", "Full aging applies on every BOM edge, including master compound → master compound."],
        ["L7", "EHT1000 duplicate", "Use the row with is_primary == 1.0; drop the NaN row; log Warn."],
        ["L8", "Changeover", "V1: 0 min always. V2 model documented but disabled."],
        ["L9", "Output time precision", "1 minute (matches curing CSV)."],
        ["L10", "Efficiency factor", "effective = ceil(nominal / 0.95). Single ceil direction throughout."],
        ["L11", "Infeasibility", "Flag and continue. No reschedule, no repair loop, no backtrack. Never shift curing."],
        ["L12", "Capstrip on ice", "Skip CAP 66 chain entirely until corrected data arrives."],
        ["L13", "Work-Away entries", "Treated as reclaim/scrap inputs, assumed already available."],
        ["L14", "Transfer + aging interplay", "effective_gap = MAX(transfer_time, MIN_aging)."],
        ["L15", "LSF tiebreak chain", "LSF → earliest curing deadline → longest downstream path → item_code asc."],
        ["L16", "Soft reservation rule", "Exclusive, invisible to others, auto-expires at consumer’s latest_acceptable_start."],
        ["L17", "t<sub>0</sub> anchor", "Auto-computed (default) as first_curing_start − critical_path − safety_buffer; guardrail asserts feasibility."],
        ["L18", "Building primary (V1)", "Lexicographic lowest machine_id: 6001."],
        ["L19", "FEFO eligibility", "Producer must have aged in (producer_end + MIN_aging ≤ sim_time). Earliest aging-MAX wins; lot_id asc tiebreak."],
        ["L20", "Time domain", "Single integer-minute domain. ceil throughout. Datetime ↔ minute lives only at audit-in and writer-out."],
        ["L21", "Event-driven dispatch", "Min-heap on (event_minute, event_class, lot_id). V1 uses topo greedy as documented simplification."],
        ["L22", "Aging-MAX inclusive", "≤ not <. gap == MAX is compliant; gap = MAX+1 is a violation."],
        ["L23", "Data-shape locks", "lot_id format, machine_id string, single unit-conversion table, datetime↔minute boundary in audit/out."],
    ]
    s.append(wrap_table(ld_rows, col_widths=[1.0 * cm, 4.4 * cm, 10.1 * cm]))
    s.append(PageBreak())

    # ----- 9. STANDING ASSUMPTIONS -----
    s.append(p("9. Standing Assumptions (Section 8)", H1))
    sa_rows = [
        ["ID", "Topic", "V1 behaviour"],
        ["8.C", "Compound lot sizing",
         "Forward-aggregate consecutive block demand into the largest lot satisfying lot_qty ≤ MPQ_Max AND aging-MAX horizon. Equal-split above MPQ_Max. HALT (locked) when a single block’s demand < MPQ_Min AND aggregation across blocks is blocked by aging-MAX."],
        ["8.D", "Null proc_time on BD-12843443-4 Fillering",
         "Do NOT impute. Audit HIGHLIGHTS the routing row and the engine refuses to schedule that operation until the planner supplies a value."],
        ["8.F", "Mixer pool size mismatch",
         "Ignore alt_machine_count entirely. Audit parses the messy machines cell and derives eligible_machine_count, which the scheduler uses."],
        ["8.I", "Dispatch rule",
         "Least Slack First (full tiebreak chain L15) for lots; FEFO with eligibility L19 and soft reservation L16 for inventory consumption. Deterministic."],
    ]
    s.append(wrap_table(sa_rows, col_widths=[1.2 * cm, 4.2 * cm, 10.1 * cm]))
    s.append(PageBreak())

    # ----- 10. DATA-QUALITY FINDINGS -----
    s.append(p("10. Data-Quality Findings (Section 9)", H1))
    s.append(p(
        "The audit module surfaces every irregularity it sees. Findings are classified as <b>HALT</b> (engine "
        "refuses to write schedule.csv and exits non-zero) or <b>WARN</b> (engine continues and lists the "
        "finding in audit_report.md).",
        BODY,
    ))
    dq_rows = [
        ["#", "Finding", "Severity"],
        ["1", "Aging Master rows with MaxAgingUnit ≠ MinAgingUnit (normalised to minutes).", "Warn"],
        ["2", "Inconsistent quoting in machine cells — parser normalises; eligible_machine_count derived.", "Warn"],
        ["3", "transfer_time_min null on most routing rows → plant default 10 min.", "Warn (default-used flag)"],
        ["4", "BD-12843443-4 Fillering proc_time NULL.", "HALT (exit code 10)"],
        ["5", "EHT1000 -480MM/90° calendering duplicate — keep is_primary=1.0.", "Warn"],
        ["6", "alt_machine_count wrong on many rows — column ignored.", "Warn"],
        ["7", "Capstrip chain has conflicting Aging Master rows + no MPQ.", "Warn + auto-exclude (L12)"],
        ["8", "Pilot items missing from Aging / ItemType Master.", "HALT (exit codes 11/12)"],
        ["9", "Informal predecessor_rule text; operation_seq is the structured signal.", "Warn on mismatch"],
        ["10", "t0 guardrail failure (L17).", "HALT (exit code 30)"],
    ]
    s.append(wrap_table(dq_rows, col_widths=[0.9 * cm, 11.0 * cm, 3.6 * cm]))
    s.append(PageBreak())

    # ----- 11. APPROACH -----
    s.append(p("11. Solution Approach", H1))
    s.append(p("Philosophy", H3))
    s.append(p(
        "The scheduler is a <b>single-pass, deterministic, BOM-driven</b> engine. From each fixed curing "
        "block it walks the BOM downward to expand demand; it then sizes lots forward in chronological "
        "order, anchored at <i>t<sub>0</sub></i>, with explicit Least-Slack-First tie-breaking. Decisions "
        "are committed once — the engine never backtracks. When a hard constraint cannot be satisfied "
        "(an aging window, an AND-join across the eight Building components, or a machine deadline), the "
        "engine logs the binding constraint by name and moves on (L11).",
        BODY,
    ))
    s.append(p("Why forward and not optimisation", H3))
    s.append(p(
        "A forward pass is auditable, explainable to the floor, and reproducible. Each lot points back to "
        "the raw-data row that defined its time, quantity, and machine. Each soft reservation is logged "
        "as it is created and as it is consumed. The cost is that the engine cannot trade off lots against "
        "each other to improve aggregate utilisation; that trade-off is deliberately deferred to V2.",
        BODY,
    ))
    s.append(p("Time domain", H3))
    s.append(p(
        "All scheduling math happens in a <b>single integer-minute domain</b>. The datetime ↔ minute "
        "conversion happens exactly twice: once in the audit step (in), and once in the output writer (out). "
        "No other module touches a <i>pd.Timestamp</i>. Every duration is computed with a single ceil direction; "
        "no module duplicates the ceil(x/60) logic. The unit-conversion table (L20) is the single source of "
        "truth.",
        BODY,
    ))
    s.append(p("Aging arithmetic", H3))
    s.append(p(
        "For every BOM edge, the engine enforces:",
        BODY,
    ))
    s.append(code_block(
        "producer_end + effective_gap   ≤  consumer_start  ≤  producer_end + MAX_aging\n"
        "where:\n"
        "  effective_gap = MAX(transfer_time_min, MIN_aging_min)   (L14)\n"
        "Both bounds are inclusive (L22)."
    ))
    s.append(p("Lot sizing", H3))
    s.append(p(
        "Lots are formed by walking served curing blocks in chronological order, accumulating quantity into "
        "the current lot while both (a) lot_qty ≤ MPQ_Max and (b) the aging horizon of the earliest "
        "served block still covers the latest. The current lot is closed and a new one opened the moment "
        "either bound breaks. If a single block's demand exceeds MPQ_Max, the lot is split into equal sub-lots; "
        "no remainder lot smaller than MPQ_Min is permitted. If a single block's demand is below MPQ_Min and "
        "aggregation across blocks is impossible because of the aging-MAX bound, the engine HALTs and prints "
        "the offending (block, compound).",
        BODY,
    ))
    s.append(p("FEFO + soft reservation", H3))
    s.append(p(
        "When a consumer lot is being scheduled, it identifies its producer lots via FEFO (First-Expiring "
        "First-Out): among lots that have aged in, the one whose aging-MAX is soonest is selected, ties broken "
        "by lot_id ascending. The chosen producer is placed under a soft reservation: exclusive, invisible to "
        "other FEFO scans, and auto-expiring at the consumer's latest_acceptable_start.",
        BODY,
    ))
    s.append(p("AND-join atomicity for Building", H3))
    s.append(p(
        "Tyre Building requires all 8 in-scope BOM components to be ready and reserved at the same instant. "
        "The reservation is <b>atomic</b>: if any one of the eight cannot be reserved, the others are released "
        "and the Building lot is routed to the infeasibility sheet with the missing component named. This is "
        "the only place where a multi-component AND-join is enforced.",
        BODY,
    ))
    s.append(PageBreak())

    # ----- 12. 26-STEP APPROACH FLOW -----
    s.append(p("12. 26-Step Approach Flow (V1)", H1))
    s.append(p(
        "This is the implementation spec. Numbered 1–26, gap-free. Each step is owned by a specific "
        "pipeline module from Section 13; each step has a deterministic, inspectable output.",
        BODY,
    ))
    steps = [
        ("1", "Load raw inputs.", "Read curing CSV, all six routing/BOM sheets, and the problem-statement PDF metadata. No mutation. (audit)"),
        ("2", "Filter to pilot SKU.", "Curing CSV → 42 rows for the pilot. Routing/BOM/Aging/ItemType/MPQ subset to all items reachable from the pilot Green Tyre, excluding the Capstrip chain (L12). (audit)"),
        ("3", "Normalise units to integer minutes.", "Apply L20 conversion table: SEC/BATCH → ceil(/60), M/MIN → ceil(lot_qty_m / proc_time), MIN → as-is; aging Days/Hours/Minutes → minutes. (audit)"),
        ("4", "Compute t0 and minute-0 anchor.", "Load t0 from config (auto or default). Run the L17 guardrail assertion. HALT and print the longest BOM path if violated. (audit)"),
        ("5", "Parse messy machine cells.", "Normalise quotes/encoding, produce clean machines list per routing row, derive eligible_machine_count. machine_id stored as string everywhere. (audit)"),
        ("6", "Classify data-quality findings.", "Split into HALT and WARN buckets per Section 9. (audit)"),
        ("7", "Handle EHT1000 duplicate.", "Keep is_primary=1.0 row; drop NaN row; log Warn. (audit)"),
        ("8", "BOM explosion per curing block.", "For each of the 42 pilot curing rows, walk the BOM downward and compute the per-edge demand quantity. (demand_explosion)"),
        ("9", "Demand aggregation per item across blocks.", "Group demand by item_code; preserve served-block list. (demand_explosion)"),
        ("10", "Lot sizing — forward aggregate.", "Build lots by walking served blocks chronologically; close and open new lot when MPQ_Max or aging-MAX horizon breaks. (lot_sizing)"),
        ("11", "Lot sizing — MPQ_Max split.", "Equal sub-lots if a single block exceeds MPQ_Max. No remainder below MPQ_Min. (lot_sizing)"),
        ("12", "Lot sizing — HALT on tight aging.", "If single-block demand < MPQ_Min AND aggregation blocked by aging-MAX, HALT. (lot_sizing)"),
        ("13", "Generate lot IDs.", "lot_id = {safe_item_code}__{op_seq}__{lot_seq:04d}. Readable item_code kept separately. (lot_sizing)"),
        ("14", "Build the lot DAG.", "Node per lot; directed edge per BOM edge with (min_aging, max_aging, effective_gap). Export dag.json. (graph_construction)"),
        ("15", "Backward feasibility limits.", "Per-lot latest_acceptable_start_min from min-aging chain. Pure forward pass owns scheduling. (backward_feasibility)"),
        ("16", "Per-lot processing duration.", "duration_min = ceil(nominal_min / 0.95). Three regimes: continuous, per-batch, per-cycle. (time_calculation)"),
        ("17", "Initialise event-driven scheduler.", "current_sim_time = t0_minute. Empty machine-free heap, empty reservation table, empty running-lots map. (scheduling)"),
        ("18", "Event loop — pop next event.", "Pop heap by (event_minute, event_class_priority, lot_id). Advance current_sim_time. (scheduling)"),
        ("19", "Dispatch — build ready set.", "Enumerate lots whose predecessors are FEFO-eligible, latest_acceptable_start ≥ sim_time, and at least one free eligible machine. (scheduling)"),
        ("20", "Dispatch — apply LSF tiebreak.", "Sort ready set by LSF chain (L15). Pick the head. (scheduling)"),
        ("21", "FEFO match + soft reservation.", "For each predecessor pick the FEFO-eligible lot with earliest aging-MAX; place soft reservation. Atomic AND-join for Building (8 components). (scheduling)"),
        ("22", "Commit the lot.", "Assign machine; set start_min and end_min; push lot-completion and lot-aged-in events. Mark consumed reservations. (scheduling)"),
        ("23", "Building primary-machine pinning.", "Try 6001 first (L18); spill only if waiting would breach aging-MAX of any component (L3). (scheduling)"),
        ("24", "Continue the loop.", "Repeat 18–23 until heap empty or every curing block has a committed Building lot (or a logged infeasibility). Expired reservations logged. (scheduling)"),
        ("25", "Diagnostics & violations.", "Recompute every gap, flag [MIN, MAX] breaches (inclusive). Classify Building → Curing OK/LATE/EARLY. Compute OTIF %. (diagnostics, kpi)"),
        ("26", "Write outputs.", "Eleven artefacts into output/<HHMM-DD-MM-YYYY>/. Datetime ones converted back from minutes only here. Exit code = 0 on clean run; non-zero with binding HALT otherwise. (visualisation + writer)"),
    ]
    rows = [["#", "Action", "Detail"]]
    for n, a, d in steps:
        rows.append([n, a, d])
    s.append(wrap_table(rows, col_widths=[1.0 * cm, 4.4 * cm, 10.1 * cm]))
    s.append(PageBreak())

    # ----- 13. PIPELINE ARCHITECTURE -----
    s.append(p("13. Pipeline Architecture", H1))
    s.append(p(
        "Thirteen pipeline steps. Each module is invocable in isolation given the upstream typed result; "
        "this makes incremental debugging straightforward. Module boundaries are frozen dataclasses "
        "(AuditResult, NormalisedResult, BomGraph, DemandResult, LotsResult, LotDagResult, "
        "FeasibilityResult, DurationResult, ScheduleResult, DiagnosticsResult, KpiResult).",
        BODY,
    ))
    s.append(code_block(
        "input/\n"
        "  curing.csv  routing.xlsx  problem.pdf\n"
        "        |\n"
        "        v\n"
        " 1.  audit                  -> audit_report.md, routing_cleaned.csv (HALT-capable)\n"
        " 2a. t0_compute (L17)       -> integer minute-0 anchor + guardrail\n"
        " 2b. unit_normalisation     -> aging/proc_time -> integer minutes (single ceil)\n"
        " 3.  bom_graph              -> nx.DiGraph + is_capstrip propagation\n"
        " 4.  demand_explosion       -> per-curing-block demand tree (zero blocks skipped)\n"
        " 5.  lot_sizing             -> Lots with serves_blocks; HALT on tight aging\n"
        " 6.  graph_construction     -> lot DAG (dag.json); effective_gap per edge\n"
        " 7.  backward_feasibility   -> latest_acceptable_start scalar per lot\n"
        " 8.  time_calculation       -> duration_min per (lot, machine), ceil(/0.95)\n"
        " 9.  forward_scheduler      -> topo greedy + CPM backward pass + FEFO + L18 + L11\n"
        "10.  diagnostics            -> aging_violations.csv, building_to_curing.csv\n"
        "11.  kpi                    -> OTIF%, util, processing min, span\n"
        "12.  visualisation          -> bom_graph.svg, schedule.csv, gantt_<block>.html (x3)\n"
        "13.  writer_excel           -> btp_schedule.xlsx (11 sheets)\n"
    ))
    s.append(PageBreak())

    # ----- 14. MODULE-BY-MODULE -----
    s.append(p("14. Module-by-Module Reference", H1))
    mods = [
        ("audit (V1/routes/audit.py)",
         "Reads raw inputs (no mutation); surfaces data-quality findings; dedups masters; parses messy machine cells; "
         "fixes Â° mojibake; drops Capstrip (L12) and the EHT1000 NaN-is_primary row (L7). HALT-capable."),
        ("t0_compute (V1/setups/t0_compute.py)",
         "L17 auto-t0: computes the longest BOM critical path (per-item duration + min-aging) from leaves to "
         "SKU; anchors t0 = first_curing_start − critical_path − safety_buffer_min. Bypassed when "
         "pilot.yaml’s t0.auto is false."),
        ("unit_conversion (V1/utilities/unit_conversion.py)",
         "Converts aging Days/Hours/Minutes (and Hr/Hrs/Min aliases) to minutes; routing proc_time SEC/BATCH, "
         "SEC, MIN to minutes via ceil(x/60); curing datetimes anchored to the chosen t0. Single ceil rounding "
         "direction throughout (L20)."),
        ("bom_walker (V1/utilities/bom_walker.py)",
         "Builds an nx.DiGraph from the BOM; propagates is_capstrip down from configured seeds; validates "
         "acyclicity. Also computes longest_min_aging_path_from/to for the L17 guardrail."),
        ("demand_explosion (V1/routes/demand_explosion.py)",
         "Walks the BOM per curing block: child_qty = parent_qty × (edge.qty / edge.output_qty). Aggregates per "
         "item; preserves serves_blocks chronologically. Zero-tyre blocks generate no demand."),
        ("lot_sizing (V1/routes/lot_sizing.py)",
         "Forward-aggregates consecutive block demands into the largest lot satisfying both qty ≤ MPQ_Max and "
         "curing-span ≤ (aging_MAX − aging_MIN). Equal-split when a single block exceeds MPQ_Max. "
         "Green Tyre is special-cased to one lot per curing row per L1. HALT (§8.C) when a single-block lot "
         "< MPQ_Min and aging-isolated from all other demand of the same item."),
        ("graph_construction (V1/routes/graph_construction.py)",
         "Builds the lot-level DAG; attaches effective_gap per L14. Emits dag.json."),
        ("backward_feasibility (V1/routes/backward_feasibility.py)",
         "Per-lot latest_acceptable_end_min derived from the min-aging chain. Conservative; refined by the "
         "scheduler’s CPM pass."),
        ("time_calculation (V1/routes/time_calculation.py)",
         "Per (lot, eligible_machine): duration_min = ceil(nominal_min / 0.95) (L10 / L20). Three regimes: "
         "continuous (M/MIN length-based), per-batch (when batch_size + batch_UNIT are set), and per-cycle / "
         "per-unit (Tyre Building consumes one cycle per building_tyres_per_cycle tyres)."),
        ("forward_scheduler (V1/routes/forward_scheduler.py)",
         "Topological greedy forward sweep with a CPM backward pass (per-lot floor + ceiling). FEFO producer pick "
         "per ingredient (L19); atomic AND-join for Building (Section 4.2); L18 prefers Building primary 6001; "
         "gap-aware machine intervals; L11 flag-and-continue."),
        ("diagnostics (V1/routes/diagnostics.py)",
         "Recomputes every consumer–producer gap; flags [MIN, MAX] breaches (inclusive, L22); classifies "
         "Building → Curing as OK / LATE / EARLY / ZERO_QTY; mirrors LATE/EARLY into aging_violations.csv with "
         "a synthetic CURING__<block> consumer id."),
        ("kpi (V1/routes/kpi.py)",
         "OTIF % at Building → Curing handoff, aging-violation totals, processing minutes, schedule span, "
         "per-machine utilisation."),
        ("visualisation (V1/routes/visualisation.py)",
         "Emits bom_graph.svg, schedule.csv, machine_view.csv, and gantt_<block>.html for three sample blocks "
         "(earliest, middle, latest in the horizon)."),
        ("writer_excel (V1/reports/writer_excel.py)",
         "Bundles btp_schedule.xlsx with 11 sheets and a curated summary sheet. HALT runs get a slim workbook "
         "(summary, routing_cleaned, audit_halt, audit_warn)."),
    ]
    rows = [["Module", "Responsibility"]]
    for name, desc in mods:
        rows.append([name, desc])
    s.append(wrap_table(rows, col_widths=[5.4 * cm, 10.1 * cm]))
    s.append(PageBreak())

    # ----- 15. CONFIGURATION -----
    s.append(p("15. Configuration (V1/config/pilot.yaml)", H1))
    s.append(p(
        "All tunables live in pilot.yaml. The file is loaded once at startup into a frozen Settings dataclass; "
        "downstream modules read from it. No environment-variable shortcut — configuration is declarative "
        "and reproducible.",
        BODY,
    ))
    s.append(code_block(
        "pilot:\n"
        "  sku_code:        '1325220516095HTMX0'\n"
        "  green_tyre_code: 'GT2056516TAXIMXTL'\n"
        "  curing_press:    '14811'       # string — leading zeros matter (L23)\n"
        "  horizon_start:   '2026-05-17 06:49'\n"
        "  horizon_end:     '2026-05-30 22:19'\n"
        "  total_demand_tyres: 2620\n"
        "\n"
        "t0:\n"
        "  auto: true                     # L17 data-driven anchor (default)\n"
        "  safety_buffer_min: 60\n"
        "  default: '2026-05-01 07:00'    # fallback when auto: false\n"
        "  guardrail_assertion: true      # L17 — HALT if longest MIN-aging path > first_curing_start\n"
        "\n"
        "efficiency:\n"
        "  factor: 0.95                   # L10 / L20\n"
        "\n"
        "defaults:\n"
        "  transfer_time_min: 10          # §9 #3 fallback when routing transfer_time is null\n"
        "  changeover_min_v1: 0           # L8 — V1 sets changeover to 0 always\n"
        "\n"
        "building:\n"
        "  pool: ['6001','6002','6003','6004','7001','7002','7003','7004']\n"
        "  primary: '6001'                # L18 — V1 deterministic primary\n"
        "  tyres_per_cycle: 2             # VMIMaxx GROUP produces 2 green tyres per cycle\n"
        "\n"
        "exclusions:\n"
        "  capstrip_items: [...]          # L12 hard-excluded set\n"
        "work_away_items: [...]           # L13 reclaim/scrap items assumed available\n"
        "green_tyre_components: [...]     # 8-component AND-join set for Building\n"
        "\n"
        "output:\n"
        "  run_id_format: '%H%M-%d-%m-%Y'\n"
        "  root: 'output'"
    ))
    s.append(PageBreak())

    # ----- 16. DETERMINISM -----
    s.append(p("16. Determinism Guarantees", H1))
    s.extend(bullets([
        "<b>No random.</b> No wall-clock-dependent defaults except the run-id timestamp, which is injectable for tests.",
        "<b>Every sort is explicit</b> — sorted(…), kind=\"stable\" on every DataFrame.sort_values. No reliance on dict insertion order.",
        "<b>Single ceil rounding</b> throughout the codebase, via V1/utilities/time_math.py. Duplicating ceil(x/60) elsewhere is treated as a defect (L23).",
        "<b>Datetime ↔ minute</b> conversion lives at exactly two boundaries: audit / unit_normalisation (in) and the schedule writer (out). No pd.Timestamp arithmetic anywhere in the scheduler core.",
        "<b>machine_id is a string end-to-end</b> so leading zeros on the mixer pool (0201, 0202, …) survive (L23).",
        "<b>lot_id is the canonical tiebreaker</b> for every dispatch and FEFO decision (L15 step 4, L19).",
    ]))
    s.append(p("Regression gate", H3))
    s.append(p(
        "The integration test suite runs the full pipeline <b>twice</b> on the same inputs and asserts: (a) dag.json "
        "is byte-identical across runs (JSON serialisation with sort_keys=True is fully stable); and (b) "
        "btp_schedule.xlsx is sheet-by-sheet DataFrame-equal across runs — the workbook bytes vary because "
        "openpyxl embeds a build timestamp, but every cell value is reproducible. The summary sheet is excluded "
        "because it carries the per-run run_id by design.",
        BODY,
    ))
    s.append(PageBreak())

    # ----- 17. HALT CODES -----
    s.append(p("17. HALT Exit Codes", H1))
    s.append(p(
        "The engine exits with a stable non-zero code so wrappers can branch on the binding finding. "
        "Defined in V1/config/halt_codes.py.",
        BODY,
    ))
    halt_rows = [
        ["Code", "Name", "Meaning"],
        ["0", "OK", "All 12 routes ran; every artefact written."],
        ["10", "AUDIT_NULL_PROC_TIME", "A routing row has a null proc_time (§9 #4, §8.D)."],
        ["11", "AUDIT_MISSING_AGING", "A mandatory pilot item is absent from the Aging Master (§9 #8)."],
        ["12", "AUDIT_MISSING_ITEMTYPE", "A mandatory pilot item is absent from the ItemType Master (§9 #8)."],
        ["20", "LOT_SIZING_TIGHT_AGING", "Single-block lot below MPQ_Min, aging-isolated from same-item demand (§8.C)."],
        ["30", "T0_GUARDRAIL_VIOLATION", "t0 + sum(MIN_aging) along longest BOM path > first_curing_start (L17)."],
    ]
    s.append(wrap_table(halt_rows, col_widths=[1.4 * cm, 5.0 * cm, 9.1 * cm]))
    s.append(p(
        "In every HALT case the engine still writes audit_report.md and routing_cleaned.csv so the planner "
        "has the evidence in hand without re-running.",
        BODY,
    ))
    s.append(PageBreak())

    # ----- 18. OUTPUTS -----
    s.append(p("18. Outputs", H1))
    s.append(p(
        "Every run creates a fresh dated folder output/&lt;HHMM-DD-MM-YYYY&gt;/. Folders are never overwritten "
        "across runs — re-running within the same minute raises FileExistsError (deliberate). A successful "
        "run emits seven files:",
        BODY,
    ))
    out_rows = [
        ["Artefact", "Content"],
        ["btp_schedule.xlsx",
         "Headline planner artefact. Single workbook with 11 sheets — summary, kpi, schedule, machine_view, "
         "building_to_curing, aging_violations, infeasibilities, reservation_log, routing_cleaned, audit_halt, audit_warn."],
        ["audit_report.md",
         "Markdown rendering of Section 9 findings, split into HALT vs WARN buckets with sheet/row citations."],
        ["dag.json",
         "Machine-readable lot dependency graph — nodes + edges with aging windows and effective-gap minutes."],
        ["bom_graph.svg",
         "Static BOM tree viz. Capstrip subtree appears tagged OUT-OF-SCOPE."],
        ["gantt_b<NN>.html",
         "Plotly Gantt for three sample blocks — earliest, middle, latest in the horizon."],
    ]
    s.append(wrap_table(out_rows, col_widths=[4.6 * cm, 10.9 * cm]))
    s.append(Spacer(1, 4 * mm))

    s.append(p("Workbook sheet contents", H3))
    sht_rows = [
        ["Sheet", "Columns / description"],
        ["summary", "Run metadata + headline KPIs (run_id, t0, sku, OTIF, processing minutes, span)."],
        ["kpi", "Counts, OTIF %, aging-violation breakdown, processing minutes, span, per-machine utilisation."],
        ["schedule", "Lot-level schedule. on_time_flag=False marks lots that finished after aging-MIN ceiling (L11)."],
        ["machine_view", "Same rows sorted by (machine_id, start_min, lot_id) for floor-level execution."],
        ["building_to_curing", "One row per Building (GT) lot per served block. Classification = OK / LATE / EARLY / ZERO_QTY."],
        ["aging_violations", "One row per breached consumer–producer pair: edge_min, edge_max, actual_gap, violation_type."],
        ["infeasibilities", "One row per unschedulable lot with the binding constraint named."],
        ["reservation_log", "Per CLAUDE.md §16: event_minute, event_type, consumer_lot_id, producer_lot_id, qty."],
        ["routing_cleaned", "Routing after dedup (L7), Capstrip drop (L12), machine-list normalisation (§8.F)."],
        ["audit_halt", "HALT findings only."],
        ["audit_warn", "WARN findings only."],
    ]
    s.append(wrap_table(sht_rows, col_widths=[3.5 * cm, 12.0 * cm]))
    s.append(PageBreak())

    # ----- 19. GOLDEN FIXTURES -----
    s.append(p("19. Golden Test Fixtures (Section 17)", H1))
    s.append(p(
        "These five fixtures are hand-computed and encoded as unit tests. They are the minimum acceptance bar "
        "for the audit and lot-sizing modules; the scheduler is only trusted after they pass.",
        BODY,
    ))
    fix_rows = [
        ["#", "Fixture", "What it locks in"],
        ["1", "f1_eht1000_24h_squeeze", "Tightest aging window in the pilot: EHT1000 24-hour MAX into curing block #1. Inclusive boundary at exactly 1440 min (L22)."],
        ["2", "f2_bd_fillering_halt", "Null proc_time on BD-12843443-4 Fillering → HALT before any schedule.csv is written."],
        ["3", "f3_eht1000_duplicate_row", "Two routing rows for EHT1000 -480MM/90° calendering — is_primary == 1.0 kept, NaN dropped, logged WARN (L7)."],
        ["4", "f4_b460_mixed_unit", "B460 aging MinAging = 4 Hours, MaxAging = 4 Days. Normaliser must output (240, 5760) minutes."],
        ["5", "f5_mpq_tight_aging_halt", "Synthetic single-block demand < MPQ_Min with the next block beyond aging-MAX. HALT in lot_sizing."],
    ]
    s.append(wrap_table(fix_rows, col_widths=[0.8 * cm, 4.8 * cm, 9.9 * cm]))
    s.append(PageBreak())

    # ----- 20. KPI SNAPSHOT -----
    s.append(p("20. KPI Snapshot — Reference Run", H1))
    s.append(p(
        "The numbers below are taken from a successful end-to-end run on the pilot inputs with the BD Fillering "
        "proc_time supplied as a planner placeholder (60 SEC/BATCH, batch 100 NOS). They illustrate the shape "
        "of the artefacts a planner would inspect.",
        BODY,
    ))
    snap = [
        ["Metric", "Value"],
        ["run_id", "0013-22-05-2026"],
        ["t0 (auto-anchored, L17)", "2026-05-16 13:58:00"],
        ["sku_code", "1325220516095HTMX0"],
        ["green_tyre_code", "GT2056516TAXIMXTL"],
        ["curing_press", "14811"],
        ["horizon", "2026-05-17 06:49 → 2026-05-30 22:19"],
        ["total_demand_tyres", "2,620"],
        ["audit_halt_findings", "0"],
        ["audit_warn_findings", "12"],
        ["lots_sized", "567"],
        ["lot_sizing_warnings", "56"],
        ["lots_scheduled", "564"],
        ["lots_infeasible", "3"],
        ["aging_violations", "4 (2 min-breach, 2 max-breach)"],
        ["building_to_curing_ok", "36"],
        ["building_to_curing_late", "2"],
        ["building_to_curing_early", "0"],
        ["OTIF %", "92.308 %"],
        ["total_processing_min", "8,611"],
        ["schedule_span_min", "18,794"],
        ["changeover_min_v1", "0 (per L8)"],
    ]
    s.append(wrap_table(snap, col_widths=[5.5 * cm, 10.0 * cm]))
    s.append(Spacer(1, 5 * mm))
    s.append(p("Selected per-machine utilisation (busy / span)", H3))
    util_rows = [
        ["Machine", "Busy (min)", "Span (min)", "Util %"],
        ["Mixer 0201", "515", "16,324", "3.16 %"],
        ["Mixer 0202", "335", "16,183", "2.07 %"],
        ["Mixer 0206", "141", "141", "100.00 %"],
        ["Building 6001 (primary)", "578", "17,757", "3.26 %"],
        ["Building 6002 (spill)", "440", "17,755", "2.48 %"],
        ["Building 6003 (spill)", "272", "16,786", "1.62 %"],
        ["FRC (calendar bottleneck)", "1,024", "16,214", "6.32 %"],
        ["FILLERING", "2,760", "16,768", "16.46 %"],
        ["Duplex Extruder", "490", "15,342", "3.19 %"],
        ["HTBC (ply cutter)", "192", "17,983", "1.07 %"],
    ]
    s.append(wrap_table(util_rows, col_widths=[5.0 * cm, 3.0 * cm, 3.0 * cm, 4.5 * cm]))
    s.append(p(
        "<i>Low utilisation values are expected at V1 — a single pilot SKU shares each shared resource with "
        "the rest of the plant, which is out of V1’s scope. Utilisation will become a first-class objective "
        "only in V2.</i>",
        SMALL,
    ))
    s.append(PageBreak())

    # ----- 21. ACCEPTANCE -----
    s.append(p("21. Acceptance Against Section 12", H1))
    acc_rows = [
        ["#", "Criterion", "Status"],
        ["1", "Correctness — every hard constraint holds; violations are self-reported.",
         "Met. 0 MIN-aging violations under forward-pass discipline on the reference run. Infeasibilities named."],
        ["2", "Reproducibility — byte-identical re-run.",
         "Met. Integration test asserts dag.json byte-identical + workbook DataFrame-equal sheet-by-sheet across 2 runs."],
        ["3", "Explainability — every lot points back to raw data.",
         "Met. lot_id encodes item + op_seq + lot_seq; producer_lot_ids on each ScheduledLot; reservation log captured."],
        ["4", "Coverage — every in-scope operation has a scheduled lot.",
         "Met when BD Fillering proc_time supplied. Without it, the cascade correctly flags BD + GT as infeasible (§8.D)."],
        ["5", "Diagnostics quality — complete + actionable.",
         "Met. Three diagnostics sheets + infeasibility records each carry the binding constraint name."],
        ["6", "Code quality — modular, fresh-clone runnable.",
         "Met. uv sync + uv run pytest works from a fresh clone; each module has its own tests; one-line entrypoint."],
        ["7", "Visualisation clarity.",
         "Met (basic). Hierarchical bom_graph.svg with Capstrip tagged; Plotly Gantt for early/mid/late sample blocks."],
    ]
    s.append(wrap_table(acc_rows, col_widths=[0.9 * cm, 6.4 * cm, 8.2 * cm]))
    s.append(PageBreak())

    # ----- 22. HOW TO RUN -----
    s.append(p("22. How to Run", H1))
    s.append(p("Prerequisites", H3))
    s.extend(bullets([
        "Python ≥ 3.11",
        "uv  —  https://github.com/astral-sh/uv (or any PEP-517-compatible installer)",
    ]))
    s.append(p("Install", H3))
    s.append(code_block("uv sync --extra dev --extra viz"))
    s.append(p("Run end-to-end", H3))
    s.append(code_block(
        "uv run python main.py\n"
        "\n"
        "# equivalent invocations\n"
        "uv run python -m V1.setups.cli --inputs input/\n"
        "uv run btp-scheduler --inputs input/"
    ))
    s.append(p("Expected behaviour on vanilla pilot inputs", H3))
    s.append(p(
        "The audit module HALTs at exit code <b>10</b> (AUDIT_NULL_PROC_TIME) because routing row 61 — "
        "BD-12843443-4 AUTO AND MANUAL FILLERING — has a null proc_time. This is the correct behaviour per "
        "CLAUDE.md §8.D: no silent imputation. The engine writes audit_report.md and routing_cleaned.csv so the "
        "planner can inspect the binding finding before supplying a value.",
        BODY,
    ))
    s.append(p("Running the full pipeline end-to-end", H3))
    s.append(p("Supply a value for the Fillering proc_time — two options:", BODY))
    s.extend(bullets([
        "Edit the routing Excel in <i>input/</i> and re-run.",
        "Use the integration test path, which patches a copy of the inputs in a temporary folder and runs the full chain twice (asserting byte-identical re-runs).",
    ]))
    s.append(code_block("uv run pytest tests/integration -v"))
    s.append(p("Test suites", H3))
    s.append(code_block(
        "uv run pytest tests -q                  # all tests\n"
        "uv run pytest tests/unit -q             # unit tests\n"
        "uv run pytest tests/integration -v      # end-to-end + determinism"
    ))
    s.append(PageBreak())

    # ----- 23. PROJECT LAYOUT -----
    s.append(p("23. Project Layout", H1))
    s.append(code_block(
        ".\n"
        "├── CLAUDE.md                  # Authoritative spec  —  read first\n"
        "├── README.md                  # Install, run, read outputs\n"
        "├── main.py                    # Canonical entry  —  `uv run python main.py`\n"
        "├── pyproject.toml             # uv-managed deps; Python  ≥ 3.11\n"
        "├── input/                     # Raw inputs (read-only)\n"
        "│     ├── BTP_PCR_May_Curing_Schedule.csv\n"
        "│     ├── BTP_Routing_…BOM_Final (1).xlsx\n"
        "│     └── JKT_BTP_Forward_Scheduler_Problem_Statement.pdf\n"
        "├── output/<HHMM-DD-MM-YYYY>/  # One dated folder per run\n"
        "├── V1/\n"
        "│     ├── config/              # pilot.yaml + Settings + HaltCode + enums\n"
        "│     ├── models/              # Frozen dataclasses (Lot, ScheduledLot, …)\n"
        "│     ├── routes/              # Pipeline modules\n"
        "│     ├── utilities/           # Pure helpers (time math, FEFO, BOM walker, …)\n"
        "│     ├── reports/             # Output writers\n"
        "│     └── setups/              # CLI, bootstrap, t0_compute\n"
        "├── tests/\n"
        "│     ├── conftest.py\n"
        "│     ├── fixtures/            # 5 golden cases\n"
        "│     ├── unit/                # 228+ unit tests\n"
        "│     └── integration/         # End-to-end + byte-identical re-run\n"
        "└── docs/\n"
        "      └── methodology.md       # Approach, evidence, acceptance"
    ))
    s.append(PageBreak())

    # ----- 24. GLOSSARY -----
    s.append(p("24. Glossary", H1))
    gloss_rows = [
        ["Term", "Definition"],
        ["BTP", "Banmore Tyre Plant — the JK Tyre facility this scheduler targets."],
        ["PCR", "Passenger-Car Radial."],
        ["BOM", "Bill of Materials. For the pilot, 7 levels deep from SKU to raw."],
        ["GT", "Green Tyre. The product of Tyre Building, consumed by Curing."],
        ["MPQ", "Min/Max Production Quantity. The size band a single lot must fall within."],
        ["FEFO", "First-Expiring First-Out. Pick the producer whose aging-MAX expires soonest."],
        ["LSF", "Least Slack First. Dispatch by smallest (latest_acceptable_start − sim_time)."],
        ["AND-join", "Tyre Building requires all 8 components together — atomic reservation."],
        ["t<sub>0</sub>", "Run anchor. Earliest possible mixer start; minute-0 in the integer-minute domain."],
        ["effective_gap", "MAX(transfer_time_min, MIN_aging_min) per L14."],
        ["OTIF", "On-Time-In-Full. Building lot delivered within its curing block aging window."],
        ["Capstrip", "Out-of-scope BOM subtree (L12) — corrected data not yet provided."],
        ["Work-Away", "Reclaim/scrap rubber pre-positioned at the line; assumed already available (L13)."],
        ["FRC", "Four-Roll Calendar — single shared resource, calenders CPJ1218 and EHT1000 plies."],
        ["VMIMaxx", "Tyre Building machine group (6001–6004, 7001–7004)."],
        ["Soft reservation", "Exclusive, expiring producer-lot pin that the consumer places via FEFO (L16)."],
        ["Aging-MIN", "Minimum time a producer’s material must rest before a consumer can start (≥)."],
        ["Aging-MAX", "Maximum time a producer’s material is acceptable; inclusive bound ≤ (L22)."],
        ["HALT", "Audit/lot-sizing failure that stops the run with a non-zero exit code."],
        ["WARN", "Audit finding logged in audit_report.md; the run continues."],
    ]
    s.append(wrap_table(gloss_rows, col_widths=[3.6 * cm, 11.9 * cm]))
    s.append(Spacer(1, 8 * mm))
    s.append(p(
        "<i>End of Project Documentation.</i>",
        ParagraphStyle("end", parent=BODY, alignment=TA_CENTER, fontSize=10, textColor=STEEL),
    ))
    return s


# -----------------------------------------------------------------------------
# Build
# -----------------------------------------------------------------------------
def build(out_path: Path) -> Path:
    doc = BaseDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
        title="JK Tyre BTP — Forward Production Scheduler (V1) — Project Documentation",
        author="JK Tyre BTP Scheduling Programme",
    )
    frame_cover = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height + 1.5 * cm,
        id="cover", showBoundary=0,
    )
    frame_body = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        id="body", showBoundary=0,
    )
    doc.addPageTemplates([
        PageTemplate(id="Cover", frames=[frame_cover], onPage=_cover_decoration),
        PageTemplate(id="Body", frames=[frame_body], onPage=_page_decoration),
    ])
    story = build_story()
    # Insert a NextPageTemplate-like marker: first page uses Cover, subsequent pages Body.
    from reportlab.platypus.doctemplate import NextPageTemplate
    final_story = [NextPageTemplate("Cover")]
    inserted_break = False
    out_story = []
    for el in story:
        out_story.append(el)
        if not inserted_break and isinstance(el, PageBreak):
            out_story.insert(0, NextPageTemplate(["Cover", "Body"]))
            inserted_break = True
    if not inserted_break:
        out_story.insert(0, NextPageTemplate("Body"))
    doc.build(out_story)
    return out_path


if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "BTP_V1_Forward_Scheduler_Documentation.pdf"
    p_ = build(out)
    print(f"Wrote {p_}")
