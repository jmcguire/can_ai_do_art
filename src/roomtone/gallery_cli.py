from __future__ import annotations

import argparse
from pathlib import Path

from .gallery import generate_run_gallery, generate_runs_index


def _run_directories(runs_dir: Path) -> list[Path]:
    if not runs_dir.is_dir():
        raise ValueError(f"Runs directory not found: {runs_dir}")
    return sorted(
        path for path in runs_dir.iterdir() if path.is_dir() and (path / "manifest.json").is_file()
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="roomtone-gallery",
        description="Regenerate Roomtone HTML pages without making API calls.",
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Archive directory to rebuild (default: runs)",
    )
    scope.add_argument(
        "--run", type=Path, help="Rebuild one run directory (default: all runs)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.run is not None:
            run_dir = args.run.expanduser().resolve()
            if not (run_dir / "manifest.json").is_file():
                raise ValueError(f"Run manifest not found: {run_dir / 'manifest.json'}")
            generate_run_gallery(run_dir)
            generate_runs_index(run_dir.parent)
            count = 1
        else:
            runs_dir = args.runs_dir.expanduser().resolve()
            run_dirs = _run_directories(runs_dir)
            for run_dir in run_dirs:
                generate_run_gallery(run_dir)
            generate_runs_index(runs_dir)
            count = len(run_dirs)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"roomtone-gallery: error: {exc}\n")
    print(f"Regenerated galleries for {count} run{'s' if count != 1 else ''}.")
    return 0
