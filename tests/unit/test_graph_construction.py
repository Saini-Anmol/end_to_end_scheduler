"""Tests for V1.routes.graph_construction (Module 9) + writer_dag."""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pytest

from V1.config.settings import Settings
from V1.models.lot import LotsResult
from V1.reports import writer_dag
from V1.routes import audit, demand_explosion, graph_construction, lot_sizing
from V1.utilities.bom_walker import build_graph
from V1.utilities.unit_conversion import normalise


@pytest.fixture(scope="module")
def norm(input_dir: Path, settings: Settings):
    return normalise(audit.run(input_dir, settings), settings)


@pytest.fixture(scope="module")
def bom(norm, settings: Settings):
    return build_graph(norm.audit.bom_df, norm.aging_df,
                       norm.audit.itemtype_df, settings)


@pytest.fixture(scope="module")
def lots(norm, bom, settings: Settings) -> LotsResult:
    return lot_sizing.run(norm, demand_explosion.run(norm, bom, settings), settings)


@pytest.fixture(scope="module")
def dag(lots, bom, norm, settings):
    return graph_construction.run(lots, bom, norm, settings)


class TestShape:
    def test_one_node_per_lot(self, dag, lots: LotsResult) -> None:
        assert dag.node_count() == len(lots.lots)
        assert set(dag.graph.nodes()) == {l.lot_id for l in lots.lots}

    def test_has_edges(self, dag) -> None:
        assert dag.edge_count() > 0


class TestEdgeAttributes:
    def test_edge_carries_aging_window(self, dag) -> None:
        for _, _, data in dag.graph.edges(data=True):
            assert data["min_aging_min"] >= 0
            assert data["max_aging_min"] >= data["min_aging_min"]
            assert data["effective_gap_min"] >= 0
            # effective_gap = max(transfer, min_aging) per L14
            assert data["effective_gap_min"] >= data["min_aging_min"]
            assert data["effective_gap_min"] >= data["transfer_time_min"]

    def test_consumer_to_producer_direction(
        self, dag, lots: LotsResult, bom
    ) -> None:
        """Every edge goes consumer-item → producer-item per the BOM."""
        nodes = dict(dag.graph.nodes(data=True))
        for u, v, data in dag.graph.edges(data=True):
            consumer_item = nodes[u]["item_code"]
            producer_item = nodes[v]["item_code"]
            assert producer_item == data["item_code"]
            # producer_item should be a BOM child of consumer_item
            assert producer_item in bom.children(consumer_item, exclude_capstrip=True)


class TestBlockOverlap:
    def test_edges_only_when_blocks_overlap(self, dag) -> None:
        nodes = dict(dag.graph.nodes(data=True))
        for u, v in dag.graph.edges():
            u_blocks = set(nodes[u]["serves_blocks"])
            v_blocks = set(nodes[v]["serves_blocks"])
            assert u_blocks & v_blocks, f"edge {u}→{v} without block overlap"


class TestCapstripExcluded:
    def test_no_capstrip_in_lot_dag(self, dag, settings: Settings) -> None:
        for _, data in dag.graph.nodes(data=True):
            assert data["item_code"] not in settings.capstrip_items


class TestWriter:
    def test_writes_dag_json(self, dag, tmp_path: Path) -> None:
        path = writer_dag.write(dag, tmp_path)
        assert path.exists()
        body = json.loads(path.read_text())
        assert "nodes" in body and "edges" in body
        assert len(body["nodes"]) == dag.node_count()
        assert len(body["edges"]) == dag.edge_count()

    def test_byte_identical_rerun(self, dag, tmp_path: Path) -> None:
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        writer_dag.write(dag, a)
        writer_dag.write(dag, b)
        assert (a / "dag.json").read_bytes() == (b / "dag.json").read_bytes()
