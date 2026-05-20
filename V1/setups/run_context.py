"""Run context: creates output/<HHMM-DD-MM-YYYY>/ and threads paths everywhere.

Run-id format per pilot.yaml (default `%H%M-%d-%m-%Y`). No cross-run state,
no append, no overwrite — the engine refuses to start if the target folder
already exists with the same timestamp (extremely unlikely under minute
granularity; raised as an explicit error rather than silently overwriting).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from V1.config.settings import Settings


@dataclass(frozen=True)
class RunContext:
    input_dir: Path
    output_dir: Path
    run_id: str
    settings: Settings


def make_run_context(
    settings: Settings,
    input_dir: Path,
    output_root: Path | None = None,
    now: datetime | None = None,
) -> RunContext:
    """Build a RunContext and create its output_dir.

    `now` is injectable for deterministic tests.
    """
    root = output_root or Path(settings.output_root)
    stamp = (now or datetime.now()).strftime(settings.run_id_format)
    out = root / stamp
    if out.exists():
        raise FileExistsError(
            f"Run folder already exists: {out}. Wait one minute and re-run."
        )
    out.mkdir(parents=True, exist_ok=False)
    return RunContext(
        input_dir=input_dir,
        output_dir=out,
        run_id=stamp,
        settings=settings,
    )
