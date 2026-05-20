"""Shared pytest fixtures: input paths, tmp output dir, settings loader."""
from __future__ import annotations

from pathlib import Path

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


@pytest.fixture
def tmp_output_root(tmp_path: Path) -> Path:
    """A fresh output root per test."""
    out = tmp_path / "output"
    out.mkdir()
    return out
