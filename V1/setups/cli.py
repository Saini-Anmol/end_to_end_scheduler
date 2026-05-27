"""CLI entry: `btp-scheduler --inputs input/ --outputs output/ [--t0 ...]`.

Single command runs the engine end-to-end from a fresh clone (Section 13).
Today wired through to Module 1 only; further modules will be added to
bootstrap as they land.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from V1.config.settings import load_settings
from V1.setups import bootstrap


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="btp-scheduler",
        description="JK Tyre BTP forward production scheduler (V1).",
    )
    p.add_argument("--inputs", type=Path, default=Path("input"),
                   help="Directory containing the 3 raw input files.")
    p.add_argument("--outputs", type=Path, default=None,
                   help="Output root. Defaults to pilot.yaml 'output.root'.")
    p.add_argument("--curing", type=Path, default=None,
                   help="Override the curing schedule file. Path can be "
                        "absolute or relative to --inputs. Accepts .csv "
                        "or .xlsx. Defaults to "
                        "<inputs>/BTP_PCR_May_Curing_Schedule.csv.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    settings = load_settings()
    return bootstrap.run(
        settings=settings,
        input_dir=args.inputs,
        output_root=args.outputs,
        curing_file=args.curing,
    )


if __name__ == "__main__":
    sys.exit(main())
