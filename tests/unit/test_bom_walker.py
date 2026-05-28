"""Tests for V1.utilities.bom_walker (Module 3)."""
from __future__ import annotations

from pathlib import Path

import networkx as nx
import pandas as pd
import pytest

from V1.config.settings import Settings
from V1.routes import audit
from V1.utilities.bom_walker import BomGraph, build_graph
from V1.utilities.unit_conversion import normalise


# --- shared real-data fixtures ---------------------------------------------

@pytest.fixture(scope="module")
def norm(input_dir: Path, settings: Settings):
    audit_result = audit.run(input_dir, settings)
    return normalise(audit_result, settings)


@pytest.fixture(scope="module")
def bom(norm, settings: Settings) -> BomGraph:
    return build_graph(
        bom_df=norm.audit.bom_df,
        aging_df=norm.aging_df,
        itemtype_df=norm.audit.itemtype_df,
        settings=settings,
    )


# --- basic shape -----------------------------------------------------------

class TestShape:
    def test_is_dag(self, bom: BomGraph) -> None:
        assert nx.is_directed_acyclic_graph(bom.graph)

    def test_sku_in_graph(self, bom: BomGraph, settings: Settings) -> None:
        assert settings.sku_code in bom.graph

    def test_gt_in_graph(self, bom: BomGraph, settings: Settings) -> None:
        assert settings.green_tyre_code in bom.graph

    def test_sku_has_single_child_gt(self, bom: BomGraph,
                                     settings: Settings) -> None:
        kids = bom.children(settings.sku_code)
        assert kids == [settings.green_tyre_code]

    def test_gt_has_9_in_scope_components(self, bom: BomGraph,
                                          settings: Settings) -> None:
        # L12 reversed 2026-05-28 — Capstrip in scope. With an empty
        # capstrip seed list, nothing is flagged is_capstrip, so
        # exclude_capstrip=True returns all 9 GT children (incl. Capstrip).
        kids = bom.children(settings.green_tyre_code, exclude_capstrip=True)
        for comp in settings.green_tyre_components:
            assert comp in kids, f"missing in-scope component: {comp!r}"
        assert "CAP 66 - CAPSTRIP" in kids

    def test_gt_has_9_children_including_capstrip(
        self, bom: BomGraph, settings: Settings
    ) -> None:
        kids = bom.children(settings.green_tyre_code, exclude_capstrip=False)
        assert len(kids) == 9
        assert "CAP 66 - CAPSTRIP" in kids


# --- capstrip propagation (L12) --------------------------------------------

class TestCapstripL12:
    def test_seeds_flagged(self, bom: BomGraph, settings: Settings) -> None:
        for seed in settings.capstrip_items:
            if seed in bom.graph:
                assert bom.graph.nodes[seed].get("is_capstrip") is True

    def test_capstrip_subtree_not_flagged_after_l12_reversal(
        self, bom: BomGraph, settings: Settings
    ) -> None:
        """L12 reversed — with an empty capstrip seed list, the Capstrip
        subtree is NO LONGER flagged is_capstrip; the chain schedules
        normally alongside everything else."""
        chain = ["CAP 66 - CAPSTRIP"] + list(
            nx.descendants(bom.graph, "CAP 66 - CAPSTRIP")
        )
        for node in chain:
            assert not bom.graph.nodes[node].get("is_capstrip"), (
                f"{node!r} still flagged is_capstrip after L12 reversal"
            )

    def test_nonstrip_nodes_not_flagged(self, bom: BomGraph,
                                       settings: Settings) -> None:
        for item in settings.green_tyre_components:
            assert not bom.graph.nodes[item].get("is_capstrip")
        assert not bom.graph.nodes[settings.green_tyre_code].get("is_capstrip")
        assert not bom.graph.nodes[settings.sku_code].get("is_capstrip")

    def test_descendants_excludes_capstrip_by_default(
        self, bom: BomGraph, settings: Settings
    ) -> None:
        all_descendants = bom.descendants(settings.sku_code,
                                          exclude_capstrip=True)
        for d in all_descendants:
            assert not bom.graph.nodes[d].get("is_capstrip"), (
                f"capstrip leak in descendants: {d}"
            )

    def test_capstrip_visible_when_opted_in(
        self, bom: BomGraph, settings: Settings
    ) -> None:
        """L12 — viz can still see the chain tagged OUT-OF-SCOPE."""
        with_cap = bom.descendants(settings.sku_code, exclude_capstrip=False)
        assert "CAP 66 - CAPSTRIP" in with_cap


# --- topological order -----------------------------------------------------

class TestTopologicalOrder:
    def test_raws_before_masters_before_sku(self, bom: BomGraph,
                                            settings: Settings) -> None:
        order = bom.topological_order(exclude_capstrip=True)
        idx = {item: i for i, item in enumerate(order)}
        # Master compounds appear before the Green Tyre, which appears before SKU.
        assert idx["MB230"] < idx[settings.green_tyre_code]
        assert idx[settings.green_tyre_code] < idx[settings.sku_code]
        # SKU is last in the topo order.
        assert order[-1] == settings.sku_code

    def test_master_compound_chain(self, bom: BomGraph) -> None:
        """MB230 → MB231 → MB1232 → B460 chain ordering."""
        order = bom.topological_order(exclude_capstrip=True)
        idx = {item: i for i, item in enumerate(order)}
        # In our graph, MB230 is a child of MB231 (consumed by MB231 to make MB231).
        # So children come first in the topo order.
        assert idx["MB230"] < idx["MB231"]
        assert idx["MB231"] < idx["MB1232"]
        assert idx["MB1232"] < idx["B460"]

    def test_deterministic(self, bom: BomGraph) -> None:
        runs = {tuple(bom.topological_order()) for _ in range(5)}
        assert len(runs) == 1


# --- longest min-aging path (L17) ------------------------------------------

class TestLongestMinAgingPath:
    def test_positive_minutes_to_sku(self, bom: BomGraph,
                                     settings: Settings) -> None:
        """Some aging accumulates along the longest path from raws to SKU."""
        m = bom.longest_min_aging_path_to(settings.sku_code)
        assert m > 0

    def test_fits_inside_t0_to_first_curing(
        self, bom: BomGraph, settings: Settings, norm
    ) -> None:
        """L17 guardrail pre-flight: t0 + longest_min_aging ≤ first_curing_start.

        first_curing_start_min relative to t0_default is 23029 min (16d - 11m).
        Asserts the longest min-aging fits inside that envelope so the run
        is feasible with the default t0.
        """
        first_curing_min = int(norm.curing_df.iloc[0]["start_min"])
        longest = bom.longest_min_aging_path_to(settings.sku_code)
        assert longest <= first_curing_min, (
            f"L17 guardrail would HALT: longest={longest} > first_curing={first_curing_min}"
        )

    def test_excludes_capstrip(self, bom: BomGraph,
                               settings: Settings) -> None:
        with_cap = bom.longest_min_aging_path_to(settings.sku_code, exclude_capstrip=False)
        without_cap = bom.longest_min_aging_path_to(settings.sku_code, exclude_capstrip=True)
        # Either equal (capstrip path not the longest) or with_cap >= without_cap.
        # Spec requires without_cap to be the value used by the guardrail.
        assert without_cap <= with_cap or without_cap == with_cap


# --- aging missingness -----------------------------------------------------

class TestAgingMissing:
    def test_no_in_scope_items_missing_aging(self, bom: BomGraph) -> None:
        """Every in-scope intermediate node has normalised aging.

        Excludes leaves (raws, bottomless per L2) and tops (no consumer to
        age against, e.g. the SKU itself).
        """
        assert bom.items_missing_aging(exclude_capstrip=True) == []


# --- edge attributes -------------------------------------------------------

class TestEdgeAttributes:
    def test_qty_uom_attached(self, bom: BomGraph,
                              settings: Settings) -> None:
        # SKU → GT edge: 1 NOS
        edge = bom.graph[settings.sku_code][settings.green_tyre_code]
        assert edge["qty"] == 1.0
        assert edge["uom"] == "NOS"

    def test_gt_to_cpj_edge(self, bom: BomGraph,
                            settings: Settings) -> None:
        # GT → CPJ1218-162MM/29° qty=1860 MM
        edge = bom.graph[settings.green_tyre_code]["CPJ1218-162MM/29°"]
        assert edge["qty"] == 1860.0
        assert edge["uom"] == "MM"


# --- determinism -----------------------------------------------------------

class TestDeterminism:
    def test_children_sorted_ascending(self, bom: BomGraph,
                                       settings: Settings) -> None:
        kids = bom.children(settings.green_tyre_code, exclude_capstrip=False)
        assert kids == sorted(kids)

    def test_descendants_sorted_ascending(self, bom: BomGraph,
                                          settings: Settings) -> None:
        d = bom.descendants(settings.sku_code)
        assert d == sorted(d)

    def test_repeated_builds_identical(self, norm, settings: Settings) -> None:
        a = build_graph(norm.audit.bom_df, norm.aging_df,
                        norm.audit.itemtype_df, settings)
        b = build_graph(norm.audit.bom_df, norm.aging_df,
                        norm.audit.itemtype_df, settings)
        assert a.nodes(exclude_capstrip=False) == b.nodes(exclude_capstrip=False)
        assert a.topological_order() == b.topological_order()
