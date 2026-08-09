from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import time
from typing import Any, Protocol

from .archive import (
    append_command,
    create_run,
    detect_start_kind,
    load_run,
    save_manifest,
    sha256_file,
    timestamp,
)
from .config import Profile, Settings
from .gallery import refresh_galleries
from .provider import write_json
from .summary import summarize_run


class Provider(Protocol):
    def text_to_image(
        self, prompt: str, destination: Path
    ) -> tuple[dict[str, Any], dict[str, Any]]: ...

    def image_to_text(
        self, image_path: Path, prompt: str
    ) -> tuple[dict[str, Any], dict[str, Any], str]: ...


def _validate_resume(
    manifest: dict[str, Any], start: Path, profile: Profile, settings: Settings
) -> None:
    if manifest["start"]["sha256"] != sha256_file(start):
        raise ValueError("The supplied start file does not match this run")
    if manifest["profile"]["sha256"] != profile.sha256:
        raise ValueError("The supplied profile does not match this run")
    if manifest["effective_settings"] != settings.to_dict():
        raise ValueError("The effective settings do not match this run")


def run_transformations(
    *,
    provider: Provider,
    start: Path,
    profile: Profile,
    settings: Settings,
    generations: int,
    output_dir: Path,
    argv: list[str],
    title: str | None = None,
    resume: Path | None = None,
    progress: callable = print,
) -> Path:
    if generations < 1:
        raise ValueError("generations must be at least 1")
    start = start.expanduser().resolve()
    if not start.is_file():
        raise ValueError(f"Start file not found: {start}")

    if resume is None:
        run_dir, manifest = create_run(
            output_dir, start, profile, settings, generations, argv, title
        )
    else:
        run_dir = resume.expanduser().resolve()
        manifest = load_run(run_dir)
        _validate_resume(manifest, start, profile, settings)
        if title is not None and " ".join(title.split()) != manifest.get("title"):
            raise ValueError("--title does not match this run")
        if generations < len(manifest["steps"]):
            raise ValueError("generations is less than the number of completed steps")
        manifest["generations_requested"] = generations
        manifest["status"] = "running"
        manifest.pop("error", None)
        append_command(run_dir, argv)
        save_manifest(run_dir, manifest)

    refresh_galleries(run_dir, manifest)

    if manifest["steps"]:
        previous = manifest["steps"][-1]
        current_kind = previous["output_kind"]
        current_path = run_dir / previous["output_path"]
    else:
        current_kind = detect_start_kind(start)
        current_path = run_dir / manifest["start"]["archived_path"]

    try:
        for number in range(len(manifest["steps"]) + 1, generations + 1):
            output_kind = "image" if current_kind == "text" else "text"
            step_dir = run_dir / f"{number:04d}-{output_kind}"
            if step_dir.exists():
                step_dir.rename(run_dir / f"{step_dir.name}.incomplete-{timestamp()}")
            step_dir.mkdir(exist_ok=False)
            started_at = datetime.now(timezone.utc).isoformat()
            started = time.monotonic()
            if current_kind == "text":
                description = current_path.read_text(encoding="utf-8").strip()
                if not description:
                    raise ValueError(f"Text input is empty: {current_path}")
                prompt = profile.text_to_image_prompt.replace(
                    "{{description}}", description
                )
                output_path = step_dir / f"image.{settings.image_format}"
                progress(f"[{number}/{generations}] text -> image")
                request, response = provider.text_to_image(prompt, output_path)
                write_json(step_dir / "request.json", request)
                write_json(step_dir / "response.json", response)
            else:
                output_path = step_dir / "description.md"
                progress(f"[{number}/{generations}] image -> text")
                request, response, description = provider.image_to_text(
                    current_path, profile.image_to_text_prompt
                )
                output_path.write_text(description.strip() + "\n", encoding="utf-8")
                write_json(step_dir / "request.json", request)
                write_json(step_dir / "response.json", response)

            manifest["steps"].append(
                {
                    "number": number,
                    "input_kind": current_kind,
                    "input_path": str(current_path.relative_to(run_dir)),
                    "output_kind": output_kind,
                    "output_path": str(output_path.relative_to(run_dir)),
                    "output_sha256": sha256_file(output_path),
                    "started_at": started_at,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                }
            )
            save_manifest(run_dir, manifest)
            refresh_galleries(run_dir, manifest)
            current_kind = output_kind
            current_path = output_path
    except BaseException as exc:
        manifest["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        manifest["error"] = {"type": type(exc).__name__, "message": str(exc)}
        save_manifest(run_dir, manifest)
        refresh_galleries(run_dir, manifest)
        raise

    completed_at = datetime.now(timezone.utc).isoformat()
    manifest["status"] = "completed"
    manifest["completed_at"] = completed_at
    manifest["summary"] = summarize_run(run_dir, manifest, completed_at)
    save_manifest(run_dir, manifest)
    refresh_galleries(run_dir, manifest)
    return run_dir
