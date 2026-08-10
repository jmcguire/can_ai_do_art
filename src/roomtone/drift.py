from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
from typing import Any, Protocol
import warnings

from PIL import Image

from .archive import load_run, sha256_file


SCHEMA_VERSION = 1
DREAMSIM_MODEL = "open_clip_vitb32"
DREAMSIM_PROJECT_URL = "https://github.com/ssundaram21/dreamsim"
SSIM_SIZE = (256, 256)


@dataclass(frozen=True)
class ImageArtifact:
    generation: int
    path: str
    sha256: str


class DistanceMetric(Protocol):
    package_version: str

    def distance(self, first: Path, second: Path) -> float: ...


class SimilarityMetric(Protocol):
    package_version: str

    def similarity(self, first: Path, second: Path) -> float: ...


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "unknown"


class DreamSimDistance:
    package_version: str

    def __init__(self) -> None:
        try:
            import torch
            import torch.nn.functional as functional
            from dreamsim import dreamsim
        except ImportError as exc:
            raise RuntimeError(
                "DreamSim analysis dependencies are not installed. "
                "Install them with: python -m pip install -e '.[analysis]'"
            ) from exc

        self._torch = torch
        self._functional = functional
        self._device = "cpu"
        configured_cache = os.environ.get("ROOMTONE_CACHE_DIR")
        cache_root = (
            Path(configured_cache).expanduser()
            if configured_cache
            else Path.home() / ".cache" / "roomtone"
        )
        cache_dir = cache_root / "dreamsim"
        cache_dir.mkdir(parents=True, exist_ok=True)
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Already found a `peft_config` attribute.*",
                category=UserWarning,
            )
            self._model, self._preprocess = dreamsim(
                pretrained=True,
                device=self._device,
                dreamsim_type=DREAMSIM_MODEL,
                cache_dir=str(cache_dir),
            )
        self._model.eval()
        self.package_version = _package_version("dreamsim")
        self._embeddings: dict[Path, Any] = {}

    def _embedding(self, path: Path) -> Any:
        resolved = path.resolve()
        if resolved not in self._embeddings:
            with Image.open(resolved) as source:
                image = source.convert("RGB")
                tensor = self._preprocess(image).to(self._device)
            with self._torch.no_grad():
                self._embeddings[resolved] = self._model.embed(tensor)
        return self._embeddings[resolved]

    def distance(self, first: Path, second: Path) -> float:
        left = self._embedding(first)
        right = self._embedding(second)
        similarity = self._functional.cosine_similarity(left, right, dim=-1)
        return float((1 - similarity).mean().item())


class StructuralSimilarity:
    package_version: str

    def __init__(self) -> None:
        try:
            import numpy
            from skimage.metrics import structural_similarity
        except ImportError as exc:
            raise RuntimeError(
                "SSIM analysis dependencies are not installed. "
                "Install them with: python -m pip install -e '.[analysis]'"
            ) from exc
        self._numpy = numpy
        self._structural_similarity = structural_similarity
        self.package_version = _package_version("scikit-image")
        self._images: dict[Path, Any] = {}

    def _image(self, path: Path) -> Any:
        resolved = path.resolve()
        if resolved not in self._images:
            with Image.open(resolved) as source:
                image = source.convert("RGB").resize(SSIM_SIZE, Image.Resampling.LANCZOS)
            self._images[resolved] = self._numpy.asarray(image)
        return self._images[resolved]

    def similarity(self, first: Path, second: Path) -> float:
        return float(
            self._structural_similarity(
                self._image(first),
                self._image(second),
                channel_axis=-1,
                data_range=255,
            )
        )


def image_artifacts(run_dir: Path, manifest: dict[str, Any]) -> list[ImageArtifact]:
    candidates: list[tuple[int, str]] = []
    start = manifest.get("start") or {}
    if start.get("kind") == "image" and start.get("archived_path"):
        candidates.append((0, str(start["archived_path"])))
    candidates.extend(
        (int(step["number"]), str(step["output_path"]))
        for step in manifest.get("steps", [])
        if step.get("output_kind") == "image" and step.get("output_path")
    )
    artifacts = [
        ImageArtifact(generation, relative, sha256_file(run_dir / relative))
        for generation, relative in candidates
        if (run_dir / relative).is_file()
    ]
    return sorted(artifacts, key=lambda item: item.generation)


def _input_signature(images: list[ImageArtifact]) -> str:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "dreamsim_model": DREAMSIM_MODEL,
        "ssim_size": list(SSIM_SIZE),
        "images": [image.__dict__ for image in images],
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def load_drift(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / "drift.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_current_drift(
    run_dir: Path, manifest: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    data = load_drift(run_dir)
    if data is None:
        return None
    manifest = manifest or load_run(run_dir)
    images = image_artifacts(run_dir, manifest)
    return data if data.get("input_signature") == _input_signature(images) else None


def needs_analysis(run_dir: Path, *, force: bool = False) -> bool:
    if force:
        return True
    run_dir = run_dir.expanduser().resolve()
    manifest = load_run(run_dir)
    images = image_artifacts(run_dir, manifest)
    return load_current_drift(run_dir, manifest) is None


def analyze_run(
    run_dir: Path,
    *,
    force: bool = False,
    dreamsim_metric: DistanceMetric | None = None,
    ssim_metric: SimilarityMetric | None = None,
) -> tuple[Path, bool]:
    run_dir = run_dir.expanduser().resolve()
    manifest = load_run(run_dir)
    images = image_artifacts(run_dir, manifest)
    if not images:
        raise ValueError(f"Run contains no images: {run_dir}")

    signature = _input_signature(images)
    destination = run_dir / "drift.json"
    existing = load_drift(run_dir)
    if not force and existing and existing.get("input_signature") == signature:
        return destination, False

    dreamsim_metric = dreamsim_metric or DreamSimDistance()
    ssim_metric = ssim_metric or StructuralSimilarity()
    baseline = images[0]
    results: list[dict[str, Any]] = []
    for index, current in enumerate(images):
        current_path = run_dir / current.path
        baseline_path = run_dir / baseline.path
        previous = images[index - 1] if index else None
        previous_values = None
        if previous is not None:
            previous_path = run_dir / previous.path
            previous_values = {
                "generation": previous.generation,
                "dreamsim": dreamsim_metric.distance(previous_path, current_path),
                "ssim": ssim_metric.similarity(previous_path, current_path),
            }
        baseline_values = {
            "generation": baseline.generation,
            "dreamsim": (
                0.0
                if current == baseline
                else dreamsim_metric.distance(baseline_path, current_path)
            ),
            "ssim": (
                1.0
                if current == baseline
                else ssim_metric.similarity(baseline_path, current_path)
            ),
        }
        results.append(
            {
                "generation": current.generation,
                "path": current.path,
                "sha256": current.sha256,
                "previous": previous_values,
                "baseline": baseline_values,
            }
        )

    data = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_signature": signature,
        "baseline_generation": baseline.generation,
        "algorithms": {
            "dreamsim": {
                "display_name": "DreamSim OpenCLIP ViT-B/32",
                "kind": "perceptual_distance",
                "package": "dreamsim",
                "package_version": dreamsim_metric.package_version,
                "model": DREAMSIM_MODEL,
                "lower_is_more_similar": True,
                "project_url": DREAMSIM_PROJECT_URL,
            },
            "ssim": {
                "display_name": "Structural Similarity Index",
                "kind": "structural_similarity",
                "package": "scikit-image",
                "package_version": ssim_metric.package_version,
                "higher_is_more_similar": True,
                "preprocessing": {
                    "color_mode": "RGB",
                    "resize": list(SSIM_SIZE),
                    "resampling": "Lanczos",
                },
            },
        },
        "images": results,
    }
    temporary = run_dir / "drift.json.tmp"
    temporary.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination, True
