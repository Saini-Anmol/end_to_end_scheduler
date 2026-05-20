"""Writes bom_graph.svg — static BOM viz.

Hierarchical layout: SKU at the top, raws at the bottom. Capstrip nodes
appear tagged "OUT OF SCOPE" in a distinct colour per L12. Each node label
shows item code + (if known) the min/max aging window in minutes.

Layout uses networkx's `multipartite_layout` keyed by topological level so
the picture reads top-down without needing graphviz.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx

from V1.utilities.bom_walker import BomGraph


def _level_map(g: nx.DiGraph) -> dict[str, int]:
    """Topological levels: SKU level=0, deeper items get higher numbers."""
    levels: dict[str, int] = {}
    for n in nx.topological_sort(g):  # parents first (SKU first)
        preds = list(g.predecessors(n))
        if not preds:
            levels[n] = 0
        else:
            levels[n] = max(levels[p] for p in preds) + 1
    return levels


def write(bom: BomGraph, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    g = bom.graph
    levels = _level_map(g)
    for n in g.nodes():
        g.nodes[n]["_level"] = levels[n]

    pos = nx.multipartite_layout(g, subset_key="_level", align="horizontal")
    # multipartite_layout: x = level, y = within-level order. We want SKU at
    # top (higher y) — invert y.
    pos = {n: (x, -y) for n, (x, y) in pos.items()}

    fig, ax = plt.subplots(figsize=(18, 12))
    capstrip_nodes = [n for n, d in g.nodes(data=True) if d.get("is_capstrip")]
    in_scope = [n for n in g.nodes() if n not in set(capstrip_nodes)]
    nx.draw_networkx_nodes(
        g, pos, nodelist=in_scope, node_size=900, node_color="#4F8FBF", ax=ax
    )
    if capstrip_nodes:
        nx.draw_networkx_nodes(
            g, pos, nodelist=capstrip_nodes, node_size=900,
            node_color="#D9D9D9", linewidths=1.2, edgecolors="#888888", ax=ax
        )
    nx.draw_networkx_edges(
        g, pos, arrows=True, arrowstyle="->", arrowsize=10,
        edge_color="#666666", width=0.7, ax=ax
    )
    labels: dict[str, str] = {}
    for n, d in g.nodes(data=True):
        tag = " (OUT-OF-SCOPE)" if d.get("is_capstrip") else ""
        a_min = d.get("aging_min_minutes")
        a_max = d.get("aging_max_minutes")
        if a_min is not None and a_max is not None:
            aging = f"\n[{a_min}–{a_max} min]"
        else:
            aging = ""
        labels[n] = f"{n}{aging}{tag}"
    nx.draw_networkx_labels(g, pos, labels=labels, font_size=7, ax=ax)
    ax.set_title("BOM graph — pilot SKU 1325220516095HTMX0")
    ax.axis("off")
    plt.tight_layout()
    path = output_dir / "bom_graph.svg"
    plt.savefig(path, format="svg")
    plt.close(fig)
    return path
