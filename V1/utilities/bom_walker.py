"""BOM graph + traversal helpers (Module 3).

Builds a directed graph from the BOM where edges go from PARENT (produced
item / Output column) to CHILD (consumed item / input code column).

  parent = consumer  (what's being produced)
  child  = producer  (what's being consumed to make the parent)

Capstrip subtree handling (L12): the configured seed items
(`settings.capstrip_items`) and every item reachable downward from them are
flagged `is_capstrip=True`. Default traversals skip these. The BOM viz can
still render them tagged "OUT OF SCOPE — awaiting data" by opting in.

Longest-min-aging path is exposed for two consumers:
  - L17 t0 guardrail (assertion at run start).
  - L15 step-3 dispatch tiebreaker (downstream path remaining).

Determinism: every neighbour iteration is sorted ascending by item code.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import networkx as nx
import pandas as pd

from V1.config.settings import Settings


@dataclass(frozen=True)
class BomGraph:
    """A frozen wrapper around an nx.DiGraph plus convenience helpers.

    The wrapped graph is mutable, but the BomGraph instance itself is frozen
    so consumers can pass it around without fearing reference swaps.
    """
    graph: nx.DiGraph

    # ----- topology helpers (all sorted for determinism) -----

    def nodes(self, exclude_capstrip: bool = True) -> list[str]:
        return sorted(
            n for n, d in self.graph.nodes(data=True)
            if not (exclude_capstrip and d.get("is_capstrip"))
        )

    def children(self, item: str, exclude_capstrip: bool = True) -> list[str]:
        """Items consumed to make `item`, sorted ascending."""
        out = []
        for c in self.graph.successors(item):
            if exclude_capstrip and self.graph.nodes[c].get("is_capstrip"):
                continue
            out.append(c)
        return sorted(out)

    def parents(self, item: str, exclude_capstrip: bool = True) -> list[str]:
        """Items that consume `item`, sorted ascending."""
        out = []
        for p in self.graph.predecessors(item):
            if exclude_capstrip and self.graph.nodes[p].get("is_capstrip"):
                continue
            out.append(p)
        return sorted(out)

    def is_terminal(self, item: str, exclude_capstrip: bool = True) -> bool:
        """`item` has no in-scope children — i.e., it's a raw / pre-existing
        input (L2 — bottomless raws)."""
        return len(self.children(item, exclude_capstrip=exclude_capstrip)) == 0

    def descendants(self, item: str, exclude_capstrip: bool = True) -> list[str]:
        """All items reachable downward from `item` (transitive children)."""
        visited: set[str] = set()
        stack = [item]
        while stack:
            n = stack.pop()
            if n in visited:
                continue
            visited.add(n)
            for c in self.children(n, exclude_capstrip=exclude_capstrip):
                stack.append(c)
        visited.discard(item)
        return sorted(visited)

    def ancestors(self, item: str, exclude_capstrip: bool = True) -> list[str]:
        """All items reachable upward (transitive parents)."""
        visited: set[str] = set()
        stack = [item]
        while stack:
            n = stack.pop()
            if n in visited:
                continue
            visited.add(n)
            for p in self.parents(n, exclude_capstrip=exclude_capstrip):
                stack.append(p)
        visited.discard(item)
        return sorted(visited)

    def topological_order(self, exclude_capstrip: bool = True) -> list[str]:
        """Children-first order — raws before masters before components.

        Uses nx's lexicographical topological sort for determinism. nx's
        default convention puts source nodes (no incoming) first, so we
        reverse the graph (raws have no incoming there) and topo-sort that.
        """
        g = self._scoped_subgraph() if exclude_capstrip else self.graph
        reversed_g = g.reverse(copy=True)
        return list(nx.lexicographical_topological_sort(reversed_g))

    def _scoped_subgraph(self) -> nx.DiGraph:
        keep = [n for n, d in self.graph.nodes(data=True)
                if not d.get("is_capstrip")]
        return self.graph.subgraph(keep).copy()

    # ----- aging-path helpers -----

    def longest_min_aging_path_to(
        self, top: str, exclude_capstrip: bool = True
    ) -> int:
        """Max sum of `aging_min_minutes` along any path from a leaf descendant
        up to `top`, INCLUDING `top` itself.

        Missing aging values count as 0 (raws are bottomless per L2). Used by
        the L17 t0 guardrail.
        """
        g = self._scoped_subgraph() if exclude_capstrip else self.graph
        if top not in g:
            raise KeyError(f"{top!r} not in graph")
        topo_parents_first = list(nx.lexicographical_topological_sort(g))
        best: dict[str, int] = {}
        for n in reversed(topo_parents_first):  # leaves first
            children = sorted(g.successors(n))
            own = _safe_int_minutes(g.nodes[n].get("aging_min_minutes"))
            if not children:
                best[n] = own
            else:
                best[n] = own + max(best[c] for c in children)
        return best[top]

    def longest_min_aging_path_from(
        self, item: str, top: str | None = None, exclude_capstrip: bool = True
    ) -> int:
        """Max sum of `aging_min_minutes` along any path from `item` (inclusive)
        UP to `top` (inclusive) through ancestors.

        Used by Module 6 (backward feasibility) to compute the conservative
        downstream lead time from each lot's item to the SKU.

        `top` defaults to the unique zero-in-degree node (SKU). Missing aging
        values count as 0 (L2 — raws are bottomless; finished-good SKU has no
        consumer to age against).
        """
        g = self._scoped_subgraph() if exclude_capstrip else self.graph
        if item not in g:
            raise KeyError(f"{item!r} not in graph")
        if top is None:
            tops = [n for n in g.nodes() if g.in_degree(n) == 0]
            if len(tops) != 1:
                raise ValueError(
                    f"longest_min_aging_path_from: cannot infer `top`, candidates={tops}"
                )
            top = tops[0]
        anc = nx.ancestors(g, item) | {item}
        if top not in anc and top != item:
            raise KeyError(f"{top!r} is not an ancestor of {item!r}")
        sub = g.subgraph(anc).copy()
        # In `sub`, `item` is the only sink (no successors that lead anywhere in `anc`).
        # We DP by visiting `item` first, then ancestors:
        # best[item] = own_aging(item); best[n] = max(best[c] for c in sub.successors(n)) + own_aging(n).
        sub_reversed = sub.reverse(copy=True)
        best: dict[str, int] = {}
        for n in nx.lexicographical_topological_sort(sub_reversed):
            own = _safe_int_minutes(g.nodes[n].get("aging_min_minutes"))
            children_in_sub = list(sub.successors(n))
            if not children_in_sub:
                best[n] = own
            else:
                best[n] = max(best[c] for c in children_in_sub) + own
        return best[top]

    def items_missing_aging(self, exclude_capstrip: bool = True) -> list[str]:
        """In-scope items whose normalised aging is missing/None/NaN.

        Used by the run-start validation to HALT before scheduling on items
        with unknown aging units. Excluded:
          - Leaves (out_degree=0): raws, bottomless per L2.
          - Tops (in_degree=0): no consumer to age against (e.g. the SKU itself,
            which is the terminal saleable good).
        """
        g = self._scoped_subgraph() if exclude_capstrip else self.graph
        out: list[str] = []
        for n in sorted(g.nodes()):
            if g.out_degree(n) == 0:
                continue
            if g.in_degree(n) == 0:
                continue
            v = g.nodes[n].get("aging_min_minutes")
            if v is None or (isinstance(v, float) and pd.isna(v)):
                out.append(n)
        return out


# --- builder ---------------------------------------------------------------

def build_graph(
    bom_df: pd.DataFrame,
    aging_df: pd.DataFrame,
    itemtype_df: pd.DataFrame,
    settings: Settings,
) -> BomGraph:
    """Build the BOM graph from normalised input frames.

    `aging_df` must already carry `min_aging_min` / `max_aging_min` columns
    (produced by V1.utilities.unit_conversion.normalise).
    """
    aging_by_item: dict[str, dict] = {}
    for _, row in aging_df.iterrows():
        aging_by_item[str(row["ItemCode"])] = {
            "min": row.get("min_aging_min"),
            "max": row.get("max_aging_min"),
        }
    itype_by_item: dict[str, str] = {
        str(row["ItemCode"]): str(row["ItemType"])
        for _, row in itemtype_df.iterrows()
        if pd.notna(row.get("ItemType"))
    }

    g = nx.DiGraph()

    def ensure_node(item: str) -> None:
        if item in g:
            return
        a = aging_by_item.get(item, {})
        g.add_node(
            item,
            item_type=itype_by_item.get(item),
            aging_min_minutes=a.get("min"),
            aging_max_minutes=a.get("max"),
            is_capstrip=(item in settings.capstrip_items),
            is_work_away=(item in settings.work_away_items),
        )

    # Per-item production rate: parent's `output qty` + `unit` from the BOM.
    # Constant across all of parent's outgoing edges (same row defines both),
    # so we can also stash on the node for cheap lookup later.
    for _, row in bom_df.iterrows():
        parent = str(row["Output"])
        child = str(row["input code"])
        ensure_node(parent)
        ensure_node(child)
        out_qty = float(row["output qty"]) if pd.notna(row.get("output qty")) else None
        out_uom = str(row["unit"]) if pd.notna(row.get("unit")) else None
        in_qty = float(row["qty"]) if pd.notna(row.get("qty")) else None
        in_uom = str(row["unit.1"]) if pd.notna(row.get("unit.1")) else None
        g.add_edge(
            parent, child,
            output_qty=out_qty,
            output_uom=out_uom,
            qty=in_qty,
            uom=in_uom,
            input_item_type=(str(row.get("Input ItemType"))
                             if pd.notna(row.get("Input ItemType")) else None),
        )
        # Stash on parent node (idempotent — same value across all rows).
        if g.nodes[parent].get("bom_output_qty") is None:
            g.nodes[parent]["bom_output_qty"] = out_qty
            g.nodes[parent]["bom_output_uom"] = out_uom

    _propagate_capstrip_down(g, settings)

    if not nx.is_directed_acyclic_graph(g):
        cycles = sorted(map(tuple, nx.simple_cycles(g)))
        raise ValueError(f"BOM graph contains cycles: {cycles[:3]}")

    return BomGraph(graph=g)


# --- helpers ---------------------------------------------------------------

def _propagate_capstrip_down(g: nx.DiGraph, settings: Settings) -> None:
    """Flag every descendant of a configured capstrip seed as is_capstrip too.

    The seeds themselves are flagged at node creation. Here we walk DOWN to
    cover their full subtree (L12 — skip everything related to the chain).
    """
    seeds = sorted(s for s in settings.capstrip_items if s in g)
    visited: set[str] = set()
    stack: list[str] = list(seeds)
    while stack:
        n = stack.pop()
        if n in visited:
            continue
        visited.add(n)
        for c in sorted(g.successors(n)):
            stack.append(c)
    for n in visited:
        g.nodes[n]["is_capstrip"] = True


def _safe_int_minutes(v: object) -> int:
    """Cast aging-minute value to int, treating None/NaN as 0 (L2 — raws are
    bottomless)."""
    if v is None:
        return 0
    try:
        if pd.isna(v):
            return 0
    except TypeError:
        pass
    return int(v)
