"""Re-exports + literal constants that never come from pilot.yaml.

For convenience: `from V1.config.constants import SETTINGS` gives downstream
modules a one-import path to the resolved runtime config.
"""
from __future__ import annotations

from V1.config.settings import Settings, load_settings


# Module-level lazy-loaded settings handle. Tests use load_settings() directly
# with a fixture path; production code reads SETTINGS.
SETTINGS: Settings = load_settings()


# Routing dedup key — used by audit to collapse the EHT1000 duplicate row (L7).
ROUTING_DEDUP_KEY: tuple[str, ...] = ("routed_product", "operation_seq")
