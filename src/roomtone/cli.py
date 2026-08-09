from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from . import __version__
from .archive import detect_start_kind
from .config import load_profile, override_settings
from .engine import run_transformations


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="roomtone",
        description=(
            "Repeatedly alternate between OpenAI image generation and image "
            "description. Generations count individual transformations."
        ),
    )
    parser.add_argument("--start", required=True, type=Path, help="Starting text or image file")
    parser.add_argument(
        "--generations",
        required=True,
        type=int,
        help="Number of individual transformations (100 normally produces 50 of each)",
    )
    parser.add_argument(
        "--profile",
        required=True,
        type=Path,
        help="Profile directory, or its profile.toml file",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("runs"))
    parser.add_argument("--image-model")
    parser.add_argument("--vision-model")
    parser.add_argument("--size", dest="image_size")
    parser.add_argument("--quality", dest="image_quality")
    parser.add_argument("--format", dest="image_format", choices=("png", "jpeg", "webp"))
    parser.add_argument("--detail", dest="vision_detail", choices=("auto", "low", "high", "original"))
    parser.add_argument("--reasoning-effort", choices=("none", "low", "medium", "high", "xhigh", "max"))
    parser.add_argument("--max-output-tokens", type=int)
    parser.add_argument("--timeout", dest="timeout_seconds", type=float)
    parser.add_argument("--retries", dest="retry_attempts", type=int)
    parser.add_argument("--retry-delay", dest="retry_initial_delay_seconds", type=float)
    parser.add_argument("--retry-max-delay", dest="retry_max_delay_seconds", type=float)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--resume", type=Path, help="Resume an interrupted run directory")
    parser.add_argument("--dry-run", action="store_true", help="Validate and show the plan without API calls")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.generations < 1:
        parser.error("--generations must be at least 1")
    if not args.start.expanduser().is_file():
        parser.error(f"--start file not found: {args.start}")

    try:
        profile = load_profile(args.profile)
        settings = override_settings(
            profile.settings,
            **{
                key: getattr(args, key)
                for key in (
                    "image_model",
                    "vision_model",
                    "image_size",
                    "image_quality",
                    "image_format",
                    "vision_detail",
                    "reasoning_effort",
                    "max_output_tokens",
                    "timeout_seconds",
                    "retry_attempts",
                    "retry_initial_delay_seconds",
                    "retry_max_delay_seconds",
                )
            },
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    if args.dry_run:
        start_kind = detect_start_kind(args.start)
        first = "text -> image" if start_kind == "text" else "image -> text"
        image_count = (args.generations + (1 if start_kind == "text" else 0)) // 2
        text_count = args.generations - image_count
        print(
            json.dumps(
                {
                    "start_kind": start_kind,
                    "first_transformation": first,
                    "generations": args.generations,
                    "images_to_create": image_count,
                    "descriptions_to_create": text_count,
                    "output_dir": str(args.output_dir),
                    "profile_sha256": profile.sha256,
                    "effective_settings": settings.to_dict(),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    try:
        from dotenv import load_dotenv

        load_dotenv(args.env_file)
        if not os.environ.get("OPENAI_API_KEY"):
            parser.error(
                f"OPENAI_API_KEY is not set (checked environment and {args.env_file})"
            )
        from .provider import OpenAIProvider

        provider = OpenAIProvider(settings)
        command = ["roomtone", *(argv if argv is not None else sys.argv[1:])]
        run_dir = run_transformations(
            provider=provider,
            start=args.start,
            profile=profile,
            settings=settings,
            generations=args.generations,
            output_dir=args.output_dir,
            argv=command,
            resume=args.resume,
        )
    except KeyboardInterrupt:
        print("Interrupted; the run can be resumed with --resume.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"roomtone: error: {exc}", file=sys.stderr)
        return 1

    print(f"Completed run: {run_dir}")
    return 0

