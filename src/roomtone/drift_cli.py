from __future__ import annotations

import argparse
from pathlib import Path

from .archive import load_run
from .drift import (
    DreamSimDistance,
    StructuralSimilarity,
    analyze_run,
    image_artifacts,
    needs_analysis,
)
from .gallery import generate_run_gallery, generate_runs_index
from .gallery_cli import _run_directories


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="roomtone-drift",
        description="Measure image drift and refresh Roomtone HTML pages.",
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs"),
        help="Archive directory to analyze (default: runs)",
    )
    scope.add_argument(
        "--run", type=Path, help="Analyze one run directory (default: all runs)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute unchanged runs (default: false)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.run is not None:
            run_dirs = [args.run.expanduser().resolve()]
            runs_dir = run_dirs[0].parent
        else:
            runs_dir = args.runs_dir.expanduser().resolve()
            run_dirs = _run_directories(runs_dir)

        analyzable = {
            run_dir
            for run_dir in run_dirs
            if image_artifacts(run_dir, load_run(run_dir))
        }
        pending = {
            run_dir
            for run_dir in analyzable
            if needs_analysis(run_dir, force=args.force)
        }
        dreamsim_metric = DreamSimDistance() if pending else None
        ssim_metric = StructuralSimilarity() if pending else None
        changed = 0
        skipped = 0
        without_images = 0
        for index, run_dir in enumerate(run_dirs, start=1):
            print(f"[{index}/{len(run_dirs)}] {run_dir.name}")
            if run_dir not in analyzable:
                without_images += 1
                generate_run_gallery(run_dir)
                continue
            _, was_changed = analyze_run(
                run_dir,
                force=args.force,
                dreamsim_metric=dreamsim_metric,
                ssim_metric=ssim_metric,
            )
            changed += int(was_changed)
            skipped += int(not was_changed)
            generate_run_gallery(run_dir)
        generate_runs_index(runs_dir)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, f"roomtone-drift: error: {exc}\n")
    print(
        "Drift analysis complete: "
        f"{changed} computed, {skipped} unchanged, {without_images} without images."
    )
    return 0
