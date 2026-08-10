# Roomtone

[![Roomtone archive deployment](https://github.com/jmcguire/can_ai_do_art/actions/workflows/pages.yml/badge.svg?branch=main)](https://github.com/jmcguire/can_ai_do_art/actions/workflows/pages.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![OpenAI API](https://img.shields.io/badge/OpenAI-API-412991?logo=openai&logoColor=white)](https://developers.openai.com/api/)
[![Open issues](https://img.shields.io/github/issues/jmcguire/can_ai_do_art)](https://github.com/jmcguire/can_ai_do_art/issues)
[![Browse the archive](https://img.shields.io/badge/GitHub%20Pages-browse%20the%20archive-222222?logo=githubpages&logoColor=white)](https://jmcguire.github.io/can_ai_do_art/)

Roomtone repeatedly translates text into an image and an image back into text.
It is inspired by Alvin Lucier's *I Am Sitting in a Room*: each transformation
removes and introduces information until the characteristic tendencies of the
models become audible—or, here, visible.

[Browse the published Roomtone run archive.](https://jmcguire.github.io/can_ai_do_art/)

`--generations` counts individual transformations. With a text seed, 100
generations produce 50 images and 50 descriptions. With an image seed, the order
is reversed.

## Install

Roomtone requires Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp .env.example .env
```

Put your OpenAI API key in `.env`. The `.env` file and local `seeds/` directory
are ignored by Git. Generated runs are checked in so the experiment archive can
be published and reproduced.

Some OpenAI accounts may need API organization verification before GPT Image
models can be used. See OpenAI's image generation guide if the API reports an
access error.

Image-drift analysis is optional because its local vision model is much larger
than Roomtone's normal runtime dependencies. Install it when needed with:

```bash
python -m pip install -e '.[analysis]'
```

The first analysis downloads the DreamSim model weights to
`~/.cache/roomtone/dreamsim`. Set `ROOMTONE_CACHE_DIR` to change the parent cache
directory. Drift calculation is local and makes no OpenAI API calls.

## Run

```bash
roomtone \
  --start seeds/first.txt \
  --generations 100 \
  --profile profiles/default
```

The three arguments above are required. See every option with:

```bash
roomtone --help
```

Validate a run without calling OpenAI or creating an output directory:

```bash
roomtone \
  --start seeds/first.txt \
  --generations 100 \
  --profile profiles/default \
  --dry-run
```

The three required options also have short forms: `-s`, `-g`, and `-p`.

Resume an interrupted run with the same start file, profile, and effective
settings. `--generations` may be increased to extend it:

```bash
roomtone \
  --start seeds/first.txt \
  --generations 100 \
  --profile profiles/default \
  --resume runs/a-simple-wooden-chair-20260809T143210Z
```

## Profiles and overrides

A profile directory contains:

```text
profile.toml
text-to-image.md
image-to-text.md
```

The text-to-image prompt must contain the literal `{{description}}` placeholder.
Edit either Markdown file to change the behavior of one half of the loop.

Settings resolve in this order:

1. Built-in defaults
2. Values in `profile.toml`
3. Command-line overrides

For example:

```bash
roomtone \
  --start seeds/first.txt \
  --generations 10 \
  --profile profiles/default \
  --image-model gpt-image-2 \
  --vision-model gpt-5.6 \
  --quality medium
```

The resolved settings are recorded in each run's `manifest.json`.

## Run archive

Each run receives a title-based directory under `runs/`, ending in a UTC timestamp
for uniqueness, for example:

```text
runs/a-simple-wooden-chair-20260809T143210Z/
├── manifest.json
├── drift.json
├── commands.txt
├── index.html
├── profile/
├── 0000/
│   └── first.txt
├── 0001-image/
│   ├── image.png
│   ├── request.json
│   └── response.json
└── 0002-text/
    ├── description.md
    ├── request.json
    └── response.json
```

The `0000/` directory contains the archived seed. Every transformation directory
is labeled by its output kind, making images and descriptions easy to find while
browsing the filesystem.

Large image seeds are downscaled when archived to fit within the configured
generated-image dimensions. Aspect ratio is preserved, and smaller seeds are
not enlarged. The manifest records the original and archived dimensions, byte
sizes, and checksums. When image size is `auto`, the seed is bounded to
1024×1024.

By default, the title is the first text-seed fragment before a comma or period,
or the image seed's filename with separators converted to spaces. Override it with
`--title "My experiment"`. The title appears in the run page's browser title and
heading, and its slug forms the beginning of the published URL.

The manifest records timestamps, Roomtone version, Git commit when available,
effective settings, checksums, step status, and elapsed time for each completed
transformation. A completed run also records a summary with total wall time,
artifact counts and bytes, token usage by model, and estimated API cost together
with the exact pricing assumptions and date used. Image response base64 is
decoded to the image file; its location and checksum replace the duplicate
base64 string in `response.json`. No API key is archived.

## Visual drift analysis

Measure every run under the default `runs/` directory and refresh its published
pages with:

```bash
roomtone-drift
```

The first image in each run is the baseline, whether that is the generation 0
seed or the first generated image after a text seed. Each later image is compared
with both the baseline and the immediately previous image. Unchanged runs are
skipped; use `--force` to recompute them. To limit the command to one run or use
a different archive location:

```bash
roomtone-drift --run runs/example-20260809T143210Z
roomtone-drift --runs-dir other-runs
```

Each run receives one root-level `drift.json`. It contains the raw distance and
similarity observations for every configured algorithm: single-branch DreamSim
OpenCLIP ViT-B/32 is the displayed perceptual-distance metric, while SSIM is
retained as a structural diagnostic. This derived file is separate from the run
manifest and can be safely recomputed from the archived images.

Regenerate every HTML page without recalculating drift or making API calls:

```bash
roomtone-gallery
```

`roomtone-gallery` also accepts `--run` and `--runs-dir`. Both archive commands
default to `runs/`; there is no required positional `runs` argument.

Each run also receives a self-contained HTML gallery. Its front page presents
the run title and description with thumbnails for the seed and every generated
image. When drift data is present, the front page adds a chart comparing each
image with the previous image and the baseline. Selecting a thumbnail opens that
generation with the image and its input and output descriptions side by side;
the run title returns to the overview, and the left and right arrow keys move
through the sequence. Run date, elapsed time, estimated cost, and artifact count
appear in a quiet footer. The parent `runs/index.html` catalogs every archived
run.

Each step sees only the immediately preceding artifact. Earlier images,
descriptions, and conversation state are not sent back to the model.

## Cost and interruption

Image generation will normally dominate cost. Start with a short dry run and a
one- or two-generation paid run before committing to 100 transformations. The
default profile uses low image quality to keep exploratory runs less expensive;
change it deliberately when visual fidelity matters more.

There is no cooldown between successful transformations. Roomtone waits only
when a request fails with a connection, timeout, server, or rate-limit error;
those retries use exponential backoff. Normal runtime is otherwise OpenAI API
latency. Future run manifests record `elapsed_seconds` per completed step so
image generation and description time can be compared directly.

Every completed transformation is checkpointed. If a request exhausts its
retries or the process is interrupted, the manifest is marked accordingly and
the run can be resumed.

## GitHub Pages

The included `.github/workflows/pages.yml` workflow publishes the checked-in
`runs/` directory as a GitHub Pages site. In the repository's GitHub settings,
select **GitHub Actions** as the Pages source. Thereafter, pushing a changed run
to `main` publishes the archive index and every run gallery automatically.

The workflow can also be launched manually from GitHub's Actions tab. Because
runs contain generated images, repository history will grow with each
experiment; this is intentional for the archive, but very large experiments may
eventually benefit from Git LFS or an object-storage-backed gallery.

## Development

Enable the repository's commit guard once per clone:

```bash
git config core.hooksPath .githooks
```

The guard keeps generated archives separate from code: a commit may contain
project files or run files, but not both. Run data commits may contain only one
top-level run directory plus the generated `runs/index.html` and `.nojekyll`.
As an exception, a gallery refresh may update `index.html` and root-level
`drift.json` files across any number of runs, together with `runs/index.html`
and `.nojekyll`, so analysis and presentation changes can be published in one
commit.

The test suite uses a fake provider and makes no network requests:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Preview the generated archive design locally using a temporary copy of an
existing run:

```bash
scripts/test_html_generation.sh [run-directory]
```

Then open <http://localhost:8765>. The temporary preview is removed when the
server stops, so the archived run remains unchanged.
