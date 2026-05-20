"""Runtime settings loaded from V1/config/pilot.yaml.

Single source of truth for tunables (t0, efficiency, defaults, paths,
exclusion lists, Building pool). Loaded once at startup; downstream modules
read from the returned Settings dataclass.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml


PILOT_YAML_PATH = Path(__file__).parent / "pilot.yaml"


def _parse_dt(s: str) -> datetime:
    """Permissive 'YYYY-MM-DD HH:MM' parser."""
    return datetime.strptime(s.strip(), "%Y-%m-%d %H:%M")


@dataclass(frozen=True)
class Settings:
    # Pilot SKU
    sku_code: str
    sku_description: str
    green_tyre_code: str
    curing_press: str
    horizon_start: datetime
    horizon_end: datetime
    total_demand_tyres: int

    # t0 anchor (L17)
    t0_default: datetime
    t0_guardrail_enabled: bool

    # Soft-rule defaults
    efficiency_factor: float
    default_transfer_min: int
    changeover_min_v1: int

    # Building (L3 / L18)
    building_pool: tuple[str, ...]
    building_primary: str

    # Exclusions (L12, L13)
    capstrip_items: frozenset[str]
    work_away_items: frozenset[str]

    # AND-join set (Section 4.2)
    green_tyre_components: tuple[str, ...]

    # Output
    run_id_format: str
    output_root: str


def load_settings(yaml_path: Path | None = None) -> Settings:
    """Load pilot.yaml into a frozen Settings dataclass."""
    path = yaml_path or PILOT_YAML_PATH
    with open(path) as f:
        d = yaml.safe_load(f)

    p = d["pilot"]
    return Settings(
        sku_code=str(p["sku_code"]),
        sku_description=str(p["sku_description"]),
        green_tyre_code=str(p["green_tyre_code"]),
        curing_press=str(p["curing_press"]),
        horizon_start=_parse_dt(p["horizon_start"]),
        horizon_end=_parse_dt(p["horizon_end"]),
        total_demand_tyres=int(p["total_demand_tyres"]),
        t0_default=_parse_dt(d["t0"]["default"]),
        t0_guardrail_enabled=bool(d["t0"]["guardrail_assertion"]),
        efficiency_factor=float(d["efficiency"]["factor"]),
        default_transfer_min=int(d["defaults"]["transfer_time_min"]),
        changeover_min_v1=int(d["defaults"]["changeover_min_v1"]),
        building_pool=tuple(str(x) for x in d["building"]["pool"]),
        building_primary=str(d["building"]["primary"]),
        capstrip_items=frozenset(str(x) for x in d["exclusions"]["capstrip_items"]),
        work_away_items=frozenset(str(x) for x in d["work_away_items"]),
        green_tyre_components=tuple(str(x) for x in d["green_tyre_components"]),
        run_id_format=str(d["output"]["run_id_format"]),
        output_root=str(d["output"]["root"]),
    )
