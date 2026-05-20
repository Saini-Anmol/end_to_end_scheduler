"""Writes dag.json — machine-readable lot dependency graph (Section 11)."""
from __future__ import annotations

import json
from pathlib import Path

from V1.routes.graph_construction import LotDagResult


def write(dag: LotDagResult, output_dir: Path) -> Path:
    out: dict = {"nodes": [], "edges": []}
    for n, data in sorted(dag.graph.nodes(data=True)):
        out["nodes"].append({
            "lot_id": n,
            "item_code": data.get("item_code"),
            "op_seq": data.get("op_seq"),
            "item_type": data.get("item_type"),
            "qty": data.get("qty"),
            "uom": data.get("uom"),
            "serves_blocks": data.get("serves_blocks", []),
        })
    for u, v, data in sorted(dag.graph.edges(data=True)):
        out["edges"].append({
            "consumer_lot": u,
            "producer_lot": v,
            "item_code": data.get("item_code"),
            "min_aging_min": data.get("min_aging_min"),
            "max_aging_min": data.get("max_aging_min"),
            "effective_gap_min": data.get("effective_gap_min"),
            "transfer_time_min": data.get("transfer_time_min"),
        })
    path = output_dir / "dag.json"
    path.write_text(json.dumps(out, indent=2, sort_keys=True))
    return path
