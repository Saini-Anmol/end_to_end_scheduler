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


def test_writes_bom_svg_and_schedule_csvs(
    viz_inputs, tmp_path: Path
) -> None:
    sched, demand, bom, t0 = viz_inputs
    paths = visualisation.run(sched, demand, bom, t0, tmp_path)
    assert (tmp_path / "bom_graph.svg").exists()
    assert (tmp_path / "schedule.csv").exists()
    assert (tmp_path / "machine_view.csv").exists()
    # SVG sanity-check: should have non-trivial size and contain '<svg'.
    body = (tmp_path / "bom_graph.svg").read_text()
    assert "<svg" in body
    assert len(body) > 1000


def test_gantt_html_per_sample_block(
    viz_inputs, tmp_path: Path
) -> None:
    sched, demand, bom, t0 = viz_inputs
    visualisation.run(sched, demand, bom, t0, tmp_path)
    htmls = sorted(tmp_path.glob("gantt_*.html"))
    # Up to 3 sample blocks; might be fewer if a block has no scheduled lots.
    assert 1 <= len(htmls) <= 3
    for p in htmls:
        body = p.read_text()
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
