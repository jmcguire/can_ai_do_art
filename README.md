# Roomtone

Roomtone repeatedly translates text into an image and an image back into text.
It is inspired by Alvin Lucier's *I Am Sitting in a Room*: each transformation
removes and introduces information until the characteristic tendencies of the
models become audible—or, here, visible.

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

Put your OpenAI API key in `.env`. That file and the generated `runs/` directory
are ignored by Git.

Some OpenAI accounts may need API organization verification before GPT Image
models can be used. See OpenAI's image generation guide if the API reports an
access error.

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

Resume an interrupted run with the same start file, profile, and effective
settings. `--generations` may be increased to extend it:

```bash
roomtone \
  --start seeds/first.txt \
  --generations 100 \
  --profile profiles/default \
  --resume runs/20260809T143210.123456Z
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

Each run receives a timestamp-only directory under `runs/`, for example:

```text
runs/20260809T143210.123456Z/
├── manifest.json
├── commands.txt
├── profile/
├── seed/
├── 0001/
│   ├── image.png
│   ├── request.json
│   └── response.json
└── 0002/
    ├── description.md
    ├── request.json
    └── response.json
```

The manifest records timestamps, Roomtone version, Git commit when available,
effective settings, checksums, and step status. Image response base64 is decoded
to the image file; its location and checksum replace the duplicate base64 string
in `response.json`. No API key is archived.

Each step sees only the immediately preceding artifact. Earlier images,
descriptions, and conversation state are not sent back to the model.

## Cost and interruption

Image generation will normally dominate cost. Start with a short dry run and a
one- or two-generation paid run before committing to 100 transformations. The
default profile uses low image quality to keep exploratory runs less expensive;
change it deliberately when visual fidelity matters more.

Every completed transformation is checkpointed. If a request exhausts its
retries or the process is interrupted, the manifest is marked accordingly and
the run can be resumed.

## Development

The test suite uses a fake provider and makes no network requests:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

