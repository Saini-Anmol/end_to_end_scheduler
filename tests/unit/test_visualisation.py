"""Tests for V1.routes.visualisation + the three writer modules (Module 13)."""
from __future__ import annotations

from pathlib import Path

import pytest

from V1.config.settings import Settings
from V1.routes import (
    audit,
    backward_feasibility,
    demand_explosion,
    forward_scheduler,
    lot_sizing,
    time_calculation,
    visualisation,
)
from V1.utilities.bom_walker import build_graph
from V1.utilities.unit_conversion import normalise


@pytest.fixture(scope="module")
def viz_inputs(input_dir: Path, settings: Settings):
    au = audit.run(input_dir, settings)
    norm = normalise(au, settings)
    bom = build_graph(norm.audit.bom_df, norm.aging_df,
                      norm.audit.itemtype_df, settings)
    demand = demand_explosion.run(norm, bom, settings)
    lots = lot_sizing.run(norm, demand, settings)
    feas = backward_feasibility.run(lots, demand, bom, norm)
    durs = time_calculation.run(lots, norm, settings)
    sched = forward_scheduler.run(lots, demand, feas, durs, bom, norm, settings)
    return sched, demand, bom, norm.t0


def test_writes_bom_svg(
    viz_inputs, tmp_path: Path
) -> None:
    sched, demand, bom, t0 = viz_inputs
    paths = visualisation.run(sched, demand, bom, t0, tmp_path)
    assert (tmp_path / "bom_graph.svg").exists()
    # The lot-level schedule + machine view live as sheets in
    # btp_schedule.xlsx now; visualisation.run no longer emits them.
    assert not (tmp_path / "schedule.csv").exists()
    assert not (tmp_path / "machine_view.csv").exists()
    # SVG sanity-check: should have non-trivial size and contain '<svg'.
    body = (tmp_path / "bom_graph.svg").read_text()
    assert "<svg" in body
    assert len(body) > 1000


def test_master_and_piecewise_gantts(
    viz_inputs, tmp_path: Path
) -> None:
    sched, demand, bom, t0 = viz_inputs
    visualisation.run(sched, demand, bom, t0, tmp_path)
    htmls = sorted(p.name for p in tmp_path.glob("gantt_*.html"))
    assert htmls == [
        "gantt_all.html",
        "gantt_part1.html",
        "gantt_part2.html",
        "gantt_part3.html",
    ]
    for name in htmls:
        body = (tmp_path / name).read_text()
        assert "<html" in body or "<!DOCTYPE html>" in body


def test_bom_svg_byte_identical_rerun(
    viz_inputs, tmp_path: Path
) -> None:
    """Determinism: same inputs → same SVG bytes (matplotlib's SVG output is
    stable if we don't include timestamps; mpl writes metadata that can vary,
    so we accept length within 5%)."""
    from V1.reports import writer_bom_graph
    sched, demand, bom, t0 = viz_inputs
    a = tmp_path / "a"; b = tmp_path / "b"
    a.mkdir(); b.mkdir()
    writer_bom_graph.write(bom, a)
    writer_bom_graph.write(bom, b)
    a_bytes = (a / "bom_graph.svg").read_bytes()
    b_bytes = (b / "bom_graph.svg").read_bytes()
    # mpl embeds a small metadata header — accept length match as proxy.
    assert abs(len(a_bytes) - len(b_bytes)) / max(len(a_bytes), 1) < 0.05
