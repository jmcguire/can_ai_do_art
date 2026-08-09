from __future__ import annotations

import base64
from pathlib import Path
import tempfile
import unittest

from roomtone.archive import load_run
from roomtone.cli import main
from roomtone.config import load_profile
from roomtone.engine import run_transformations


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = PROJECT_ROOT / "profiles" / "default"


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def text_to_image(self, prompt: str, destination: Path):
        self.calls.append("text_to_image")
        destination.write_bytes(b"fake-png-" + str(len(self.calls)).encode())
        return (
            {"model": "fake-image", "prompt": prompt},
            {"id": f"image-{len(self.calls)}"},
        )

    def image_to_text(self, image_path: Path, prompt: str):
        self.calls.append("image_to_text")
        return (
            {"model": "fake-vision", "source": image_path.name},
            {"id": f"text-{len(self.calls)}"},
            f"description produced at call {len(self.calls)}",
        )


class FailsOnceProvider(FakeProvider):
    def text_to_image(self, prompt: str, destination: Path):
        self.calls.append("text_to_image")
        destination.write_bytes(b"partial")
        raise RuntimeError("simulated failure")


class RoomtoneTests(unittest.TestCase):
    def test_default_profile_loads(self):
        profile = load_profile(DEFAULT_PROFILE)
        self.assertEqual(profile.settings.image_model, "gpt-image-2")
        self.assertIn("{{description}}", profile.text_to_image_prompt)

    def test_text_start_alternates_and_counts_individual_transformations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            start = root / "seed.txt"
            start.write_text("a red circle", encoding="utf-8")
            profile = load_profile(DEFAULT_PROFILE)
            provider = FakeProvider()
            run_dir = run_transformations(
                provider=provider,
                start=start,
                profile=profile,
                settings=profile.settings,
                generations=4,
                output_dir=root / "runs",
                argv=["roomtone", "--generations", "4"],
            )

            self.assertEqual(
                provider.calls,
                ["text_to_image", "image_to_text", "text_to_image", "image_to_text"],
            )
            manifest = load_run(run_dir)
            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(len(manifest["steps"]), 4)
            self.assertEqual(manifest["steps"][-1]["output_kind"], "text")
            self.assertTrue((run_dir / "0004" / "description.md").is_file())
            self.assertTrue((run_dir / "profile" / "profile.toml").is_file())

    def test_image_start_begins_with_description(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            start = root / "seed.png"
            start.write_bytes(base64.b64decode("iVBORw0KGgo="))
            profile = load_profile(DEFAULT_PROFILE)
            provider = FakeProvider()
            run_transformations(
                provider=provider,
                start=start,
                profile=profile,
                settings=profile.settings,
                generations=3,
                output_dir=root / "runs",
                argv=["roomtone"],
            )
            self.assertEqual(
                provider.calls, ["image_to_text", "text_to_image", "image_to_text"]
            )

    def test_dry_run_makes_no_run_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            start = root / "seed.txt"
            start.write_text("seed", encoding="utf-8")
            output = root / "runs"
            status = main(
                [
                    "--start",
                    str(start),
                    "--generations",
                    "100",
                    "--profile",
                    str(DEFAULT_PROFILE),
                    "--output-dir",
                    str(output),
                    "--dry-run",
                ]
            )
            self.assertEqual(status, 0)
            self.assertFalse(output.exists())

    def test_resume_continues_from_last_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            start = root / "seed.txt"
            start.write_text("seed", encoding="utf-8")
            profile = load_profile(DEFAULT_PROFILE)
            first_provider = FakeProvider()
            run_dir = run_transformations(
                provider=first_provider,
                start=start,
                profile=profile,
                settings=profile.settings,
                generations=2,
                output_dir=root / "runs",
                argv=["roomtone"],
            )
            second_provider = FakeProvider()
            resumed = run_transformations(
                provider=second_provider,
                start=start,
                profile=profile,
                settings=profile.settings,
                generations=4,
                output_dir=root / "runs",
                argv=["roomtone", "--resume", str(run_dir)],
                resume=run_dir,
            )
            self.assertEqual(resumed, run_dir)
            self.assertEqual(second_provider.calls, ["text_to_image", "image_to_text"])
            self.assertEqual(len(load_run(run_dir)["steps"]), 4)

    def test_resume_preserves_and_moves_incomplete_step(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            start = root / "seed.txt"
            start.write_text("seed", encoding="utf-8")
            profile = load_profile(DEFAULT_PROFILE)
            with self.assertRaisesRegex(RuntimeError, "simulated failure"):
                run_transformations(
                    provider=FailsOnceProvider(),
                    start=start,
                    profile=profile,
                    settings=profile.settings,
                    generations=1,
                    output_dir=root / "runs",
                    argv=["roomtone"],
                )
            run_dir = next((root / "runs").iterdir())
            run_transformations(
                provider=FakeProvider(),
                start=start,
                profile=profile,
                settings=profile.settings,
                generations=1,
                output_dir=root / "runs",
                argv=["roomtone", "--resume", str(run_dir)],
                resume=run_dir,
            )
            self.assertTrue((run_dir / "0001" / "image.png").is_file())
            self.assertEqual(len(list(run_dir.glob("0001.incomplete-*"))), 1)


if __name__ == "__main__":
    unittest.main()
