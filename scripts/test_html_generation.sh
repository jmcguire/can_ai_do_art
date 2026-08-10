#!/bin/sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_ROOT"

DEFAULT_RUN="runs/mona-lisa-by-leonardo-da-vinci-from-c2-rmf-retouched-20260809T184805Z"
SOURCE_RUN=${1:-$DEFAULT_RUN}

if [ ! -f "$SOURCE_RUN/manifest.json" ]; then
    echo "Run manifest not found: $SOURCE_RUN/manifest.json" >&2
    echo "Usage: scripts/test_html_generation.sh [run-directory]" >&2
    exit 1
fi

PREVIEW_ROOT=$(mktemp -d /tmp/roomtone-preview.XXXXXX)
trap 'rm -rf "$PREVIEW_ROOT"' EXIT HUP INT TERM
mkdir -p "$PREVIEW_ROOT/runs"
cp -R "$SOURCE_RUN" "$PREVIEW_ROOT/runs/"

PREVIEW_RUN=$(basename "$SOURCE_RUN")
.venv/bin/python -c '
from pathlib import Path
import sys

from roomtone.gallery import generate_run_gallery, generate_runs_index

runs = Path(sys.argv[1])
run = runs / sys.argv[2]
generate_run_gallery(run)
generate_runs_index(runs)
' "$PREVIEW_ROOT/runs" "$PREVIEW_RUN"

echo "Previewing the generated archive at http://localhost:8765"
echo "Press Control-C to stop."
python3 -m http.server 8765 --directory "$PREVIEW_ROOT/runs"
