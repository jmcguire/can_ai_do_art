from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from . import __version__
from .archive import derive_run_title, detect_start_kind, slugify_title
from .config import Settings, load_profile, override_settings
from .engine import run_transformations


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="roomtone",
        add_help=False,
        description=(
            "Repeatedly alternate between OpenAI image generation and image "
            "description. Generations count individual transformations."
        ),
    )
    required = parser.add_argument_group("required arguments")
    optional = parser.add_argument_group("optional arguments")
    misc = parser.add_argument_group(
        "miscellaneous", "Testing, help, and informational options."
    )

    required.add_argument(
        "-s", "--start", required=True, type=Path, help="Starting text or image file"
    )
    required.add_argument(
        "-g",
        "--generations",
        required=True,
        type=int,
        help="Number of individual transformations (100 normally produces 50 of each)",
    )
    required.add_argument(
        "-p",
        "--profile",
        required=True,
        type=Path,
        help="Profile directory, or its profile.toml file",
    )

    optional.add_argument(
        "--output-dir", type=Path, default=Path("runs"),
        help="Parent directory for run archives (default: runs)",
    )
    optional.add_argument(
        "--title",
        help="Run title and URL basis (default: derived from the text seed or image filename)",
    )
    optional.add_argument(
        "--image-model",
        help=f"Text-to-image model (default: profile value; built-in: {Settings.image_model})",
    )
    optional.add_argument(
        "--vision-model",
        help=f"Image-to-text model (default: profile value; built-in: {Settings.vision_model})",
    )
    optional.add_argument(
        "--size", dest="image_size",
        help=f"Generated image size (default: profile value; built-in: {Settings.image_size})",
    )
    optional.add_argument(
        "--quality", dest="image_quality",
        help=f"Generated image quality (default: profile value; built-in: {Settings.image_quality})",
    )
    optional.add_argument(
        "--format", dest="image_format", choices=("png", "jpeg", "webp"),
        help=f"Generated image format (default: profile value; built-in: {Settings.image_format})",
    )
    optional.add_argument(
        "--detail", dest="vision_detail", choices=("auto", "low", "high", "original"),
        help=f"Vision input detail (default: profile value; built-in: {Settings.vision_detail})",
    )
    optional.add_argument(
        "--reasoning-effort", choices=("none", "low", "medium", "high", "xhigh", "max"),
        help=f"Vision reasoning effort (default: profile value; built-in: {Settings.reasoning_effort})",
    )
    optional.add_argument(
        "--max-output-tokens", type=int,
        help=f"Description output limit (default: profile value; built-in: {Settings.max_output_tokens})",
    )
    optional.add_argument(
        "--timeout", dest="timeout_seconds", type=float,
        help=f"API timeout in seconds (default: profile value; built-in: {Settings.timeout_seconds:g})",
    )
    optional.add_argument(
        "--retries", dest="retry_attempts", type=int,
        help=f"Maximum attempts per request (default: profile value; built-in: {Settings.retry_attempts})",
    )
    optional.add_argument(
        "--retry-delay", dest="retry_initial_delay_seconds", type=float,
        help=f"Initial retry delay in seconds (default: profile value; built-in: {Settings.retry_initial_delay_seconds:g})",
    )
    optional.add_argument(
        "--retry-max-delay", dest="retry_max_delay_seconds", type=float,
        help=f"Maximum retry delay in seconds (default: profile value; built-in: {Settings.retry_max_delay_seconds:g})",
    )
    optional.add_argument(
        "--env-file", type=Path, default=Path(".env"),
        help="Environment file containing OPENAI_API_KEY (default: .env)",
    )
    optional.add_argument(
        "--resume", type=Path,
        help="Interrupted run directory to continue (default: none)",
    )

    misc.add_argument(
        "--dry-run", action="store_true",
        help="Validate and show the plan without API calls (default: false)",
    )
    misc.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    misc.add_argument("-h", "--help", action="help", help="Show this help message and exit")
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
        title = derive_run_title(args.start, args.title)
        print(
            json.dumps(
                {
                    "start_kind": start_kind,
                    "first_transformation": first,
                    "generations": args.generations,
                    "images_to_create": image_count,
                    "descriptions_to_create": text_count,
                    "output_dir": str(args.output_dir),
                    "title": title,
                    "slug": slugify_title(title),
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
            title=args.title,
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
