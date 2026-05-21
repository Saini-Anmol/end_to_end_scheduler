"""Shared pytest fixtures: input paths, tmp output dir, settings loader."""
from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import pytest

from V1.config.settings import Settings, load_settings


PROJECT_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def input_dir(project_root: Path) -> Path:
    return project_root / "input"


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Load the real pilot.yaml. Settings is frozen so this is safe to share."""
    return load_settings()


@pytest.fixture(scope="session")
def nulled_input_dir(input_dir: Path, tmp_path_factory) -> Path:
    """A copy of `input/` with the BD-12843443-4 Fillering `proc_time` row
    forced to NaN — exercises CLAUDE.md §8.D / Section 17 Fixture 2 HALT path
    regardless of whether the live input has had a value supplied."""
    dst = tmp_path_factory.mktemp("nulled_input")
    for f in input_dir.iterdir():
        shutil.copy2(f, dst / f.name)
    xlsx_path = next(dst.glob("BTP_Routing_*.xlsx"))
    sheet_name = "Routing - 1325220516095HTMX0"
    df_all = pd.read_excel(xlsx_path, sheet_name=None)
    df = df_all[sheet_name]
    mask = (df["routed_product"] == "BD-12843443-4") & (df["operation_seq"] == 60)
    df.loc[mask, "proc_time"] = float("nan")
    df.loc[mask, "proc_time_UOM"] = float("nan")
    df.loc[mask, "batch_size"] = float("nan")
    df.loc[mask, "batch_UNIT"] = float("nan")
    df_all[sheet_name] = df
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as w:
        for sheet, sub in df_all.items():
            sub.to_excel(w, sheet_name=sheet, index=False)
    return dst


@pytest.fixture
def tmp_output_root(tmp_path: Path) -> Path:
    """A fresh output root per test."""
    out = tmp_path / "output"
    out.mkdir()
    return out
