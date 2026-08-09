from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
from typing import Any
import unicodedata

from . import __version__
from .config import Profile, Settings


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def detect_start_kind(path: Path) -> str:
    return "image" if path.suffix.lower() in IMAGE_SUFFIXES else "text"


def code_revision() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def derive_run_title(start: Path, explicit_title: str | None = None) -> str:
    if explicit_title is not None:
        title = " ".join(explicit_title.split())
        if not title:
            raise ValueError("--title cannot be empty")
        return title

    if detect_start_kind(start) == "text":
        text = " ".join(start.read_text(encoding="utf-8").split())
        title = re.split(r"[,.]", text, maxsplit=1)[0].strip()
    else:
        stem = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", start.stem)
        title = re.sub(r"[-_]+", " ", stem).strip().title()
    return title or "Untitled Roomtone"


def slugify_title(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")
    return (slug[:72].rstrip("-") or "roomtone")


def create_run(
    output_dir: Path,
    start: Path,
    profile: Profile,
    settings: Settings,
    generations: int,
    argv: list[str],
    title: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    resolved_title = derive_run_title(start, title)
    slug = slugify_title(resolved_title)
    run_dir = output_dir.expanduser().resolve() / f"{slug}-{timestamp()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    archived_profile = run_dir / "profile"
    archived_profile.mkdir()
    shutil.copy2(profile.config_path, archived_profile / "profile.toml")
    for prompt_path in (profile.text_to_image_path, profile.image_to_text_path):
        relative = prompt_path.relative_to(profile.root)
        destination = archived_profile / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(prompt_path, destination)
    seed_dir = run_dir / "0000"
    seed_dir.mkdir()
    seed_copy = seed_dir / start.name
    shutil.copy2(start, seed_copy)
    (run_dir / "commands.txt").write_text(
        shlex.join(argv) + "\n", encoding="utf-8"
    )
    now = datetime.now(timezone.utc).isoformat()
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "roomtone_version": __version__,
        "git_commit": code_revision(),
        "created_at": now,
        "updated_at": now,
        "status": "running",
        "title": resolved_title,
        "slug": slug,
        "generations_requested": generations,
        "start": {
            "original_path": str(start),
            "archived_path": str(seed_copy.relative_to(run_dir)),
            "kind": detect_start_kind(start),
            "sha256": sha256_file(start),
        },
        "profile": {
            "original_path": str(profile.root),
            "archived_path": "profile",
            "sha256": profile.sha256,
        },
        "effective_settings": settings.to_dict(),
        "steps": [],
    }
    save_manifest(run_dir, manifest)
    return run_dir, manifest


def load_run(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "manifest.json"
    if not path.is_file():
        raise ValueError(f"Run manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(run_dir: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    temporary = run_dir / "manifest.json.tmp"
    temporary.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(run_dir / "manifest.json")


def append_command(run_dir: Path, argv: list[str]) -> None:
    with (run_dir / "commands.txt").open("a", encoding="utf-8") as handle:
        handle.write(shlex.join(argv) + "\n")
