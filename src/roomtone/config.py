from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import tomllib


@dataclass(frozen=True)
class Settings:
    image_model: str = "gpt-image-2"
    vision_model: str = "gpt-5.6"
    image_size: str = "1024x1024"
    image_quality: str = "low"
    image_format: str = "png"
    vision_detail: str = "high"
    reasoning_effort: str = "none"
    max_output_tokens: int = 1500
    timeout_seconds: float = 300.0
    retry_attempts: int = 5
    retry_initial_delay_seconds: float = 2.0
    retry_max_delay_seconds: float = 30.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Profile:
    root: Path
    config_path: Path
    text_to_image_path: Path
    image_to_text_path: Path
    text_to_image_prompt: str
    image_to_text_prompt: str
    settings: Settings
    sha256: str


def _profile_hash(root: Path, paths: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def load_profile(profile_arg: Path) -> Profile:
    supplied = profile_arg.expanduser().resolve()
    if supplied.is_dir():
        root = supplied
        config_path = root / "profile.toml"
    else:
        config_path = supplied
        root = supplied.parent

    if not config_path.is_file():
        raise ValueError(f"Profile configuration not found: {config_path}")

    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)

    models = raw.get("models", {})
    prompts = raw.get("prompts", {})
    image = raw.get("image", {})
    vision = raw.get("vision", {})
    network = raw.get("network", {})

    text_to_image_path = (root / prompts.get("text_to_image", "text-to-image.md")).resolve()
    image_to_text_path = (root / prompts.get("image_to_text", "image-to-text.md")).resolve()
    for path in (text_to_image_path, image_to_text_path):
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Profile prompt must be inside {root}: {path}") from exc
        if not path.is_file():
            raise ValueError(f"Profile prompt not found: {path}")

    text_to_image_prompt = text_to_image_path.read_text(encoding="utf-8").strip()
    image_to_text_prompt = image_to_text_path.read_text(encoding="utf-8").strip()
    if "{{description}}" not in text_to_image_prompt:
        raise ValueError(
            f"{text_to_image_path} must contain the literal placeholder "
            "{{description}}"
        )
    if not image_to_text_prompt:
        raise ValueError(f"Image-to-text prompt is empty: {image_to_text_path}")

    settings = Settings(
        image_model=str(models.get("text_to_image", Settings.image_model)),
        vision_model=str(models.get("image_to_text", Settings.vision_model)),
        image_size=str(image.get("size", Settings.image_size)),
        image_quality=str(image.get("quality", Settings.image_quality)),
        image_format=str(image.get("format", Settings.image_format)),
        vision_detail=str(vision.get("detail", Settings.vision_detail)),
        reasoning_effort=str(
            vision.get("reasoning_effort", Settings.reasoning_effort)
        ),
        max_output_tokens=int(
            vision.get("max_output_tokens", Settings.max_output_tokens)
        ),
        timeout_seconds=float(
            network.get("timeout_seconds", Settings.timeout_seconds)
        ),
        retry_attempts=int(network.get("retry_attempts", Settings.retry_attempts)),
        retry_initial_delay_seconds=float(
            network.get(
                "retry_initial_delay_seconds", Settings.retry_initial_delay_seconds
            )
        ),
        retry_max_delay_seconds=float(
            network.get("retry_max_delay_seconds", Settings.retry_max_delay_seconds)
        ),
    )
    if settings.retry_attempts < 1:
        raise ValueError("retry_attempts must be at least 1")
    if settings.max_output_tokens < 1:
        raise ValueError("max_output_tokens must be at least 1")

    return Profile(
        root=root,
        config_path=config_path,
        text_to_image_path=text_to_image_path,
        image_to_text_path=image_to_text_path,
        text_to_image_prompt=text_to_image_prompt,
        image_to_text_prompt=image_to_text_prompt,
        settings=settings,
        sha256=_profile_hash(
            root, (config_path.resolve(), text_to_image_path, image_to_text_path)
        ),
    )


def override_settings(settings: Settings, **overrides: object) -> Settings:
    values = settings.to_dict()
    values.update({key: value for key, value in overrides.items() if value is not None})
    return Settings(**values)
