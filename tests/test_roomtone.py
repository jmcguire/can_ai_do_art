from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from PIL import Image

from roomtone.archive import derive_run_title, load_run, slugify_title
from roomtone.cli import build_parser, main
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
            {
                "id": f"image-{len(self.calls)}",
                "model": "gpt-image-2",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 20,
                    "total_tokens": 30,
                    "input_tokens_details": {"text_tokens": 10, "image_tokens": 0},
                    "output_tokens_details": {"image_tokens": 20},
                },
            },
        )

    def image_to_text(self, image_path: Path, prompt: str):
        self.calls.append("image_to_text")
        return (
            {"model": "fake-vision", "source": image_path.name},
            {
                "id": f"text-{len(self.calls)}",
                "model": "gpt-5.6-sol",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 30,
                    "total_tokens": 130,
                    "input_tokens_details": {
                        "cached_tokens": 0,
                        "cache_write_tokens": 80,
                    },
                },
            },
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
            self.assertRegex(run_dir.name, r"^a-red-circle-\d{8}T\d{6}Z$")
            self.assertEqual(manifest["title"], "a red circle")
            self.assertEqual(manifest["slug"], "a-red-circle")
            self.assertTrue((run_dir / "0000" / "seed.txt").is_file())
            self.assertTrue((run_dir / "0004-text" / "description.md").is_file())
            self.assertTrue((run_dir / "0001-image" / "image.png").is_file())
            self.assertTrue((run_dir / "profile" / "profile.toml").is_file())
            self.assertTrue((run_dir / "index.html").is_file())
            self.assertTrue((run_dir.parent / "index.html").is_file())
            self.assertIn("elapsed_seconds", manifest["steps"][0])
            gallery = (run_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn("<title>a red circle · Roomtone</title>", gallery)
            self.assertIn("<h1>a red circle</h1>", gallery)
            self.assertIn("Generation 0", gallery)
            self.assertIn("0000/seed.txt", gallery)
            self.assertIn("Generation 1", gallery)
            self.assertIn("Generation 3", gallery)
            self.assertEqual(manifest["summary"]["images_generated"], 2)
            self.assertEqual(manifest["summary"]["descriptions_generated"], 2)
            self.assertEqual(manifest["summary"]["tokens"]["total"], 320)
            self.assertAlmostEqual(manifest["summary"]["estimated_cost_usd"], 0.0043)

    def test_help_groups_arguments_and_documents_optional_defaults(self):
        help_text = build_parser().format_help()
        self.assertIn("required arguments:", help_text)
        self.assertIn("optional arguments:", help_text)
        self.assertIn("miscellaneous:", help_text)
        self.assertIn("default: runs", help_text)
        self.assertIn("gpt-image-2", help_text)
        self.assertIn("false", help_text)
        self.assertIn("--title", help_text)
        self.assertIn("text seed or image filename", help_text)

    def test_required_argument_shortcuts(self):
        args = build_parser().parse_args(
            ["-s", "seed.txt", "-g", "12", "-p", "profiles/default"]
        )
        self.assertEqual(args.start, Path("seed.txt"))
        self.assertEqual(args.generations, 12)
        self.assertEqual(args.profile, Path("profiles/default"))

    def test_title_derivation_and_slugging(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            text_seed = root / "seed.txt"
            text_seed.write_text(
                "A red chair, standing alone. This is ignored.", encoding="utf-8"
            )
            image_seed = root / "Mona_Lisa-study.png"
            image_seed.write_bytes(b"image")
            self.assertEqual(derive_run_title(text_seed), "A red chair")
            self.assertEqual(derive_run_title(image_seed), "Mona Lisa Study")
            self.assertEqual(derive_run_title(text_seed, "  My   Run  "), "My Run")
            self.assertEqual(slugify_title("Café / Night #1"), "cafe-night-1")

    def test_image_start_begins_with_description(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            start = root / "seed.png"
            Image.new("RGB", (24, 36), "navy").save(start)
            profile = load_profile(DEFAULT_PROFILE)
            provider = FakeProvider()
            run_dir = run_transformations(
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
            manifest = load_run(run_dir)
            self.assertEqual(manifest["title"], "Seed")
            self.assertFalse(manifest["start"]["resized"])
            self.assertEqual(manifest["start"]["archived_dimensions"], [24, 36])
            gallery = (run_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn("Generation 0", gallery)
            self.assertIn("0000/seed.png", gallery)

    def test_large_image_seed_is_downscaled_without_distortion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            start = root / "wide-seed.jpg"
            Image.new("RGB", (2400, 1200), "goldenrod").save(
                start, quality=95
            )
            profile = load_profile(DEFAULT_PROFILE)
            run_dir = run_transformations(
                provider=FakeProvider(),
                start=start,
                profile=profile,
                settings=profile.settings,
                generations=1,
                output_dir=root / "runs",
                argv=["roomtone"],
            )

            manifest = load_run(run_dir)
            archived_seed = run_dir / manifest["start"]["archived_path"]
            with Image.open(archived_seed) as image:
                self.assertEqual(image.size, (1024, 512))
            self.assertTrue(manifest["start"]["resized"])
            self.assertEqual(manifest["start"]["original_dimensions"], [2400, 1200])
            self.assertEqual(manifest["start"]["archived_dimensions"], [1024, 512])
            self.assertNotEqual(
                manifest["start"]["sha256"],
                manifest["start"]["archived_sha256"],
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
            run_dir = next(path for path in (root / "runs").iterdir() if path.is_dir())
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
            self.assertTrue((run_dir / "0001-image" / "image.png").is_file())
            self.assertEqual(len(list(run_dir.glob("0001-image.incomplete-*"))), 1)


if __name__ == "__main__":
    unittest.main()
