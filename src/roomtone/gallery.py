from __future__ import annotations

from datetime import datetime
from html import escape
import json
from pathlib import Path
from typing import Any

from .drift import DREAMSIM_PROJECT_URL, load_current_drift


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def _display_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.strftime("%B %d, %Y · %H:%M UTC")
    except (TypeError, ValueError):
        return value


def _display_date(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.strftime("%B %d, %Y")
    except (TypeError, ValueError):
        return value


def _format_duration(seconds: object) -> str:
    if not isinstance(seconds, (int, float)):
        return "—"
    rounded = int(round(seconds))
    minutes, remaining = divmod(rounded, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {remaining}s"
    if minutes:
        return f"{minutes}m {remaining}s"
    return f"{remaining}s"


def _format_cost(value: object) -> str:
    return f"${value:.4f}" if isinstance(value, (int, float)) else "—"


def _excerpt(value: str, limit: int = 420) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    sentence_end = max(text.rfind(mark, 0, limit) for mark in (".", "!", "?"))
    if sentence_end >= limit // 2:
        return text[: sentence_end + 1]
    word_end = text.rfind(" ", 0, limit - 1)
    return text[: word_end if word_end > 0 else limit - 1].rstrip() + "…"


def _run_description(run_dir: Path, manifest: dict[str, Any]) -> str:
    explicit = manifest.get("description")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    seed = manifest.get("start") or {}
    if seed.get("kind") == "text" and seed.get("archived_path"):
        description = _read_text(run_dir / seed["archived_path"])
        if description:
            return _excerpt(description)

    for step in manifest.get("steps", []):
        if step.get("output_kind") == "text" and step.get("output_path"):
            description = _read_text(run_dir / step["output_path"])
            if description:
                return _excerpt(description)

    return "An iterative sequence alternating image generation and image description."


def _page_shell(title: str, body: str, *, script: str = "") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>{escape(title)}</title>
  <style>
    * {{ box-sizing:border-box; }}
    html {{ background:#eceae4; color:#25231f; }}
    body {{ margin:0; font:16px/1.5 Arial,Helvetica,sans-serif; }}
    a {{ color:inherit; text-underline-offset:3px; }}
    .site-header {{ width:min(1020px,calc(100% - 72px)); margin:auto; padding:20px 0 11px; border-bottom:1px solid #aaa69d; display:flex; justify-content:space-between; align-items:baseline; gap:28px; }}
    .run-link {{ font:400 17px/1.2 Georgia,serif; }}
    .collection-link {{ font:11px/1.2 Arial,sans-serif; white-space:nowrap; }}
    .eyebrow {{ color:#716c64; font:10px/1.2 Arial,sans-serif; letter-spacing:1.35px; text-transform:uppercase; }}
    .run-index,.generation-page {{ display:none; }}
    .run-index.active,.generation-page.active {{ display:block; }}
    .run-hero {{ width:min(1020px,calc(100% - 72px)); margin:auto; padding:58px 0 40px; text-align:center; }}
    .run-hero h1 {{ max-width:760px; margin:8px auto 15px; font:400 clamp(2.15rem,6vw,2.75rem)/1.06 Georgia,serif; }}
    .run-hero p {{ max-width:690px; margin:auto; color:#4d4942; font:15px/1.65 Georgia,serif; white-space:pre-wrap; }}
    .sequence {{ width:min(1020px,calc(100% - 72px)); margin:auto; padding:0 0 58px; }}
    .sequence-head {{ margin-bottom:14px; padding-bottom:8px; border-bottom:1px solid #aaa69d; display:flex; justify-content:space-between; gap:16px; font-size:10px; letter-spacing:.8px; text-transform:uppercase; }}
    .thumbs {{ display:grid; grid-template-columns:repeat(4,1fr); gap:25px 20px; }}
    .thumb {{ display:block; text-decoration:none; min-width:0; }}
    .thumb-frame {{ padding:7px; background:#d8d1c1; border:4px solid #302d28; box-shadow:0 4px 8px rgba(35,30,22,.14); transition:transform .12s ease; }}
    .thumb:hover .thumb-frame,.thumb:focus-visible .thumb-frame {{ transform:translateY(-2px); }}
    .thumb img {{ display:block; width:100%; height:auto; aspect-ratio:1; object-fit:contain; background:#f7f6f1; }}
    .text-thumb {{ display:grid; place-items:center; aspect-ratio:1; padding:15%; background:#f7f6f1; color:#4d4942; text-align:center; font:clamp(.75rem,2vw,1rem)/1.35 Georgia,serif; overflow:hidden; }}
    .thumb-label {{ display:flex; justify-content:space-between; gap:8px; margin-top:8px; font-size:10px; color:#5d5952; }}
    .thumb-label strong {{ color:#25231f; font-weight:400; }}
    .object-record {{ width:min(760px,100%); margin:15px auto 0; display:flex; justify-content:center; flex-wrap:wrap; gap:3px 8px; color:#87827a; font:10px/1.4 Arial,sans-serif; }}
    .object-record strong {{ color:#77726a; font-weight:400; }}
    .work {{ width:min(1020px,calc(100% - 72px)); margin:auto; padding:40px 0 46px; }}
    .object-heading {{ text-align:center; margin-bottom:22px; }}
    .object-heading h1 {{ margin:6px 0 0; font:400 21px/1.2 Georgia,serif; }}
    .frame {{ width:min(650px,100%); margin:auto; padding:20px; background:#d8d1c1; border:9px solid #292723; box-shadow:0 8px 18px rgba(35,30,22,.2); }}
    .frame img {{ display:block; width:100%; height:auto; max-height:70vh; object-fit:contain; background:#f7f6f1; }}
    .seed-text {{ width:min(650px,100%); min-height:430px; margin:auto; padding:clamp(30px,8vw,78px); display:grid; place-items:center; background:#f7f6f1; border:1px solid #aaa69d; }}
    .seed-text p {{ margin:0; white-space:pre-wrap; overflow-wrap:anywhere; font:clamp(1.2rem,4vw,2rem)/1.5 Georgia,serif; }}
    .comparison {{ margin:34px auto 0; display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); border-top:1px solid #9e9a92; border-bottom:1px solid #9e9a92; }}
    .text-record {{ min-width:0; padding:19px 26px 22px 0; }}
    .text-record + .text-record {{ border-left:1px solid #c5c1b8; padding:19px 0 22px 26px; }}
    .text-record h2 {{ margin:0 0 9px; font:10px/1.2 Arial,sans-serif; text-transform:uppercase; letter-spacing:1.15px; color:#69645d; }}
    .text-record p {{ margin:0; white-space:pre-wrap; overflow-wrap:anywhere; font:14px/1.62 Georgia,serif; }}
    .work-nav {{ margin-top:19px; display:flex; justify-content:center; align-items:center; gap:22px; font-size:11px; }}
    .work-nav a {{ padding:4px; }}
    .work-nav .disabled {{ color:#8b867e; text-decoration:none; }}
    .drift-study {{ width:min(948px,calc(100% - 72px)); margin:0 auto 42px; padding-top:22px; border-top:1px solid #aaa69d; }}
    .study-heading {{ display:flex; justify-content:space-between; align-items:flex-start; gap:20px; margin-bottom:10px; }}
    .study-heading h2 {{ margin:5px 0 0; font:400 20px/1.2 Georgia,serif; }}
    .legend {{ display:flex; flex-wrap:wrap; gap:17px; color:#5f5a53; font-size:11px; }}
    .legend span {{ display:flex; align-items:center; gap:6px; }}
    .legend i {{ width:24px; border-top:2px solid #2f5452; }}
    .legend .baseline i {{ border-color:#92643d; border-top-style:dashed; }}
    .chart-wrap {{ position:relative; width:100%; }}
    .chart-wrap svg {{ display:block; width:100%; height:auto; }}
    .chart-frame {{ fill:#f7f6f1; stroke:#aaa69d; }}
    .chart-grid {{ stroke:#cbc7be; stroke-width:1; }}
    .chart-axis {{ fill:#5f5a53; font:10px Arial,sans-serif; }}
    .chart-title {{ fill:#4d4942; font:11px Arial,sans-serif; }}
    .chart-previous {{ fill:none; stroke:#2f5452; stroke-width:2.25; }}
    .chart-baseline {{ fill:none; stroke:#92643d; stroke-width:2.25; stroke-dasharray:6 5; }}
    .chart-point-previous {{ fill:#f7f6f1; stroke:#2f5452; stroke-width:2; }}
    .chart-point-baseline {{ fill:#f7f6f1; stroke:#92643d; stroke-width:2; }}
    .chart-hover-hit {{ fill:transparent; cursor:crosshair; }}
    .chart-guide {{ display:none; stroke:#6f6a62; stroke-width:1; }}
    .chart-hover-marker {{ display:none; }}
    .chart-tooltip {{ display:none; position:absolute; pointer-events:none; background:#fff; border:1px solid #aaa69d; padding:8px 10px; color:#25231f; box-shadow:0 2px 5px rgba(35,30,22,.08); font:11px/1.45 Arial,sans-serif; }}
    .chart-tooltip strong {{ display:block; font-weight:400; margin-bottom:3px; }}
    details.method {{ margin-top:12px; border-top:1px solid #cbc7be; padding-top:9px; color:#57534c; font:11px/1.55 Georgia,serif; }}
    details.method summary {{ width:max-content; cursor:pointer; color:#25231f; font-family:Arial,sans-serif; text-decoration:underline; text-underline-offset:3px; }}
    details.method p {{ max-width:720px; margin:9px 0 0; }}
    .run-footer {{ background:#dedbd4; border-top:1px solid #b6b2a9; }}
    .run-footer-inner {{ width:min(1020px,calc(100% - 72px)); margin:auto; padding:25px 0 29px; display:grid; grid-template-columns:minmax(270px,1.35fr) minmax(380px,1fr); gap:48px; }}
    .run-index .run-footer-inner {{ display:block; }}
    .footer-context h2 {{ margin:6px 0 8px; font:400 20px/1.15 Georgia,serif; }}
    .footer-context p {{ max-width:560px; margin:0; color:#514d46; white-space:pre-wrap; font:11px/1.55 Georgia,serif; }}
    .run-facts {{ margin:0; display:grid; grid-template-columns:repeat(2,1fr); gap:0 26px; align-content:start; }}
    .run-index .run-facts {{ grid-template-columns:repeat(4,1fr); gap:0 28px; }}
    .run-facts div {{ border-top:1px solid #bcb8af; padding:7px 0 9px; }}
    .run-facts dt {{ color:#716c64; font-size:9px; letter-spacing:.65px; text-transform:uppercase; }}
    .run-facts dd {{ margin:2px 0 0; font:11px/1.35 Arial,sans-serif; }}
    .archive {{ width:min(1020px,calc(100% - 72px)); margin:auto; padding:56px 0 70px; }}
    .archive-header {{ max-width:720px; margin:0 auto 44px; text-align:center; }}
    .archive-header h1 {{ margin:8px 0 14px; font:400 clamp(2.3rem,7vw,3.5rem)/1.04 Georgia,serif; }}
    .archive-header p {{ margin:0; color:#4d4942; font:15px/1.65 Georgia,serif; }}
    .runs {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:34px 24px; }}
    .run {{ display:block; text-decoration:none; min-width:0; }}
    .run-frame {{ padding:8px; background:#d8d1c1; border:5px solid #302d28; box-shadow:0 5px 10px rgba(35,30,22,.14); }}
    .run-frame img,.placeholder {{ display:block; width:100%; aspect-ratio:1.25; object-fit:contain; background:#f7f6f1; }}
    .placeholder {{ display:grid; place-items:center; padding:20px; color:#716c64; font:16px/1.4 Georgia,serif; text-align:center; }}
    .run-copy {{ padding:12px 2px 0; }}
    .run-copy h2 {{ margin:5px 0 7px; font:400 20px/1.18 Georgia,serif; }}
    .run-description {{ margin:0 0 9px; color:#514d46; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; font:11px/1.5 Georgia,serif; }}
    .run-meta {{ color:#716c64; font-size:10px; }}
    .empty {{ padding:48px; border-top:1px solid #aaa69d; border-bottom:1px solid #aaa69d; color:#716c64; text-align:center; font:15px/1.5 Georgia,serif; }}
    @media (max-width:760px) {{
      .thumbs {{ grid-template-columns:repeat(3,1fr); }}
      .runs {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
      .run-footer-inner {{ grid-template-columns:1fr; gap:22px; }}
      .run-index .run-facts {{ grid-template-columns:repeat(2,1fr); }}
      .study-heading {{ display:block; }}
      .legend {{ margin-top:10px; }}
    }}
    @media (max-width:560px) {{
      .site-header,.run-hero,.sequence,.work,.run-footer-inner,.archive,.drift-study {{ width:calc(100% - 40px); }}
      .site-header {{ align-items:flex-start; }}
      .run-hero {{ padding-top:40px; }}
      .thumbs {{ grid-template-columns:repeat(2,1fr); gap:22px 14px; }}
      .comparison {{ grid-template-columns:1fr; }}
      .text-record {{ padding:17px 0 19px; }}
      .text-record + .text-record {{ border-left:0; border-top:1px solid #c5c1b8; padding:19px 0; }}
      .frame {{ padding:11px; border-width:6px; }}
      .runs {{ grid-template-columns:1fr; }}
    }}
    @media (max-width:390px) {{ .collection-link {{ max-width:110px; white-space:normal; text-align:right; }} }}
    @media (prefers-reduced-motion:reduce) {{ .thumb-frame {{ transition:none; }} }}
  </style>
  <noscript><style>.run-index,.generation-page {{ display:block; }} .generation-page {{ border-top:1px solid #aaa69d; }}</style></noscript>
</head>
<body>{body}{script}</body>
</html>
"""


def _gallery_items(run_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    steps = manifest.get("steps", [])
    seed = manifest["start"]
    items: list[dict[str, Any]] = [
        {
            "number": 0,
            "kind": seed["kind"],
            "path": seed["archived_path"],
            "input_text": (
                _read_text(run_dir / seed["archived_path"])
                if seed["kind"] == "text"
                else "This is the original image seed; no text produced it."
            ),
        }
    ]
    items.extend(
        {
            "number": step["number"],
            "kind": "image",
            "path": step["output_path"],
            "input_text": _read_text(run_dir / step["input_path"]),
        }
        for step in steps
        if step.get("output_kind") == "image"
    )
    for item in items:
        item["output_text"] = next(
            (
                _read_text(run_dir / step["output_path"])
                for step in steps
                if step.get("input_path") == item["path"]
                and step.get("output_kind") == "text"
            ),
            "",
        )
    return items


def _drift_records(drift: dict[str, Any] | None) -> dict[int, dict[str, Any]]:
    if not drift:
        return {}
    records: dict[int, dict[str, Any]] = {}
    for record in drift.get("images", []):
        if not isinstance(record, dict) or not isinstance(record.get("generation"), int):
            continue
        records[record["generation"]] = record
    return records


def _drift_value(record: dict[str, Any], comparison: str) -> float | None:
    values = record.get(comparison)
    value = values.get("dreamsim") if isinstance(values, dict) else None
    return float(value) if isinstance(value, (int, float)) else None


def _drift_record_markup(record: dict[str, Any] | None) -> str:
    if not record:
        return ""
    previous = _drift_value(record, "previous")
    baseline = _drift_value(record, "baseline")
    if previous is None or baseline is None:
        return ""
    return (
        '<div class="object-record"><span>Visual drift:</span>'
        f"<strong>{previous:.3f} from previous image</strong><span>·</span>"
        f"<strong>{baseline:.3f} from baseline</strong></div>"
    )


def _polyline(points: list[tuple[float, float]]) -> str:
    if not points:
        return ""
    return "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in points)


def _drift_chart(drift: dict[str, Any] | None) -> str:
    records = sorted(_drift_records(drift).values(), key=lambda item: item["generation"])
    if len(records) < 2:
        return ""

    width, height = 900.0, 250.0
    left, right, top, bottom = 60.0, 22.0, 18.0, 42.0
    plot_width = width - left - right
    plot_height = height - top - bottom
    values = [
        value
        for record in records
        for value in (
            _drift_value(record, "previous"),
            _drift_value(record, "baseline"),
        )
        if value is not None
    ]
    maximum = max(values, default=0.0)
    ceiling = maximum * 1.1 if maximum > 0 else 1.0

    def x_position(index: int) -> float:
        return left + (plot_width * index / (len(records) - 1))

    def y_position(value: float) -> float:
        return top + plot_height * (1 - value / ceiling)

    previous_points = [
        (x_position(index), y_position(value))
        for index, record in enumerate(records)
        if (value := _drift_value(record, "previous")) is not None
    ]
    baseline_points = [
        (x_position(index), y_position(value))
        for index, record in enumerate(records)
        if (value := _drift_value(record, "baseline")) is not None
    ]
    grid: list[str] = []
    for tick in range(5):
        value = ceiling * tick / 4
        y = y_position(value)
        grid.append(
            f'<line class="chart-grid" x1="{left:.2f}" y1="{y:.2f}" x2="{width-right:.2f}" y2="{y:.2f}"></line>'
            f'<text class="chart-axis" x="{left-8:.2f}" y="{y+3:.2f}" text-anchor="end">{value:.2f}</text>'
        )

    label_stride = max(1, (len(records) - 1 + 7) // 8)
    x_labels = [
        f'<text class="chart-axis" x="{x_position(index):.2f}" y="{height-18:.2f}" text-anchor="middle">{record["generation"]}</text>'
        for index, record in enumerate(records)
        if index % label_stride == 0 or index == len(records) - 1
    ]
    point_markup = [
        f'<circle class="chart-point-previous" cx="{x:.2f}" cy="{y:.2f}" r="3.5"></circle>'
        for x, y in previous_points
    ] + [
        f'<circle class="chart-point-baseline" cx="{x:.2f}" cy="{y:.2f}" r="3.5"></circle>'
        for x, y in baseline_points
    ]
    hit_width = plot_width / max(1, len(records) - 1)
    hits: list[str] = []
    for index, record in enumerate(records):
        x = x_position(index)
        previous = _drift_value(record, "previous")
        baseline = _drift_value(record, "baseline")
        hits.append(
            f'<rect class="chart-hover-hit" x="{max(left, x-hit_width/2):.2f}" y="{top:.2f}" '
            f'width="{min(width-right, x+hit_width/2)-max(left, x-hit_width/2):.2f}" height="{plot_height:.2f}" '
            f'data-x="{x:.2f}" data-generation="{record["generation"]}" '
            f'data-previous="{"" if previous is None else f"{previous:.6f}"}" '
            f'data-previous-y="{"" if previous is None else f"{y_position(previous):.2f}"}" '
            f'data-baseline="{"" if baseline is None else f"{baseline:.6f}"}" '
            f'data-baseline-y="{"" if baseline is None else f"{y_position(baseline):.2f}"}"></rect>'
        )

    return f"""
<section class="drift-study" aria-labelledby="drift-chart-title">
  <header class="study-heading"><div><div class="eyebrow">Image analysis</div><h2 id="drift-chart-title">Visual drift across the run</h2></div><div class="legend"><span><i></i>From previous image</span><span class="baseline"><i></i>From baseline</span></div></header>
  <div class="chart-wrap">
    <svg viewBox="0 0 900 250" role="img" aria-labelledby="drift-chart-title drift-chart-description">
      <desc id="drift-chart-description">DreamSim raw distance for each image compared with the previous image and the first image in this run.</desc>
      <rect class="chart-frame" x="{left:.2f}" y="{top:.2f}" width="{plot_width:.2f}" height="{plot_height:.2f}"></rect>
      {"".join(grid)}
      <text class="chart-title" transform="translate(15 150) rotate(-90)" text-anchor="middle">DreamSim raw distance</text>
      <text class="chart-title" x="{left + plot_width/2:.2f}" y="{height-2:.2f}" text-anchor="middle">Generation</text>
      {"".join(x_labels)}
      <path class="chart-previous" d="{_polyline(previous_points)}"></path>
      <path class="chart-baseline" d="{_polyline(baseline_points)}"></path>
      {"".join(point_markup)}
      <line class="chart-guide" x1="0" y1="{top:.2f}" x2="0" y2="{top+plot_height:.2f}"></line>
      <circle class="chart-hover-marker chart-point-previous" r="5"></circle>
      <circle class="chart-hover-marker chart-point-baseline" r="5"></circle>
      {"".join(hits)}
    </svg>
    <div class="chart-tooltip" role="tooltip"></div>
  </div>
  <details class="method"><summary>How visual drift is measured</summary><p>These values compare images only; generated and source text are not included. The displayed raw distance uses the single-branch <a href="{DREAMSIM_PROJECT_URL}">DreamSim</a> OpenCLIP ViT-B/32 model. DreamSim compares learned visual features that reflect both overall meaning and lower-level appearance, producing a smaller distance when two images look more alike.</p></details>
</section>"""


def _facts_markup(manifest: dict[str, Any], artifact_count: int) -> str:
    summary = manifest.get("summary") or {}
    return f"""<dl class="run-facts">
  <div><dt>Date</dt><dd>{escape(_display_date(str(manifest.get("created_at", ""))))}</dd></div>
  <div><dt>Estimated cost</dt><dd>{_format_cost(summary.get("estimated_cost_usd"))}</dd></div>
  <div><dt>Elapsed</dt><dd>{_format_duration(summary.get("wall_time_seconds"))}</dd></div>
  <div><dt>Artifacts</dt><dd>{artifact_count} including seed</dd></div>
</dl>"""


def generate_run_gallery(run_dir: Path, manifest: dict[str, Any] | None = None) -> Path:
    run_dir = run_dir.resolve()
    if manifest is None:
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    items = _gallery_items(run_dir, manifest)
    steps = manifest.get("steps", [])
    image_count = sum(item["kind"] == "image" for item in items)
    run_title = str(manifest.get("title") or run_dir.name)
    description = _run_description(run_dir, manifest)
    facts = _facts_markup(manifest, len(steps) + 1)
    drift = load_current_drift(run_dir, manifest)
    drift_records = _drift_records(drift)

    thumbnails: list[str] = []
    generation_pages: list[str] = []
    for index, item in enumerate(items):
        generation = int(item["number"])
        path = str(item["path"])
        kind = str(item["kind"])
        if kind == "image":
            thumbnail_visual = f'<img src="{escape(path, quote=True)}" alt="">'
            main_visual = f'<div class="frame"><img src="{escape(path, quote=True)}" alt="Generation {generation}"></div>'
            input_label = "Text that produced this image"
            output_label = "Text produced from this image"
            output_text = item["output_text"] or "No description was generated after this image."
            record = drift_records.get(generation)
            previous_drift = _drift_value(record, "previous") if record else None
            thumbnail_note = (
                f"{previous_drift:.3f} drift"
                if previous_drift is not None
                else "Baseline" if record else "Image"
            )
            drift_markup = _drift_record_markup(record)
        else:
            seed_text = str(item["input_text"])
            thumbnail_visual = f'<div class="text-thumb">{escape(seed_text)}</div>'
            main_visual = f'<div class="seed-text"><p>{escape(seed_text)}</p></div>'
            input_label = "Starting text"
            output_label = "What followed"
            output_text = "The first generated image follows this seed."
            thumbnail_note = "Text"
            drift_markup = ""

        thumbnails.append(
            f'<a class="thumb" href="#generation-{generation}">'
            f'<div class="thumb-frame">{thumbnail_visual}</div>'
            f'<span class="thumb-label"><strong>Generation {generation}</strong><span>{escape(thumbnail_note)}</span></span>'
            "</a>"
        )
        previous_link = (
            f'<a rel="prev" href="#generation-{items[index - 1]["number"]}">Previous work</a>'
            if index else '<span class="disabled">Previous work</span>'
        )
        next_link = (
            f'<a rel="next" href="#generation-{items[index + 1]["number"]}">Next work</a>'
            if index + 1 < len(items) else '<span class="disabled">Next work</span>'
        )
        generation_pages.append(f"""
<section class="generation-page" id="generation-{generation}" data-generation="{generation}">
  <header class="site-header"><a class="run-link" href="#run-index">{escape(run_title)}</a><a class="collection-link" href="../">Roomtone Study Collection</a></header>
  <main class="work">
    <header class="object-heading"><div class="eyebrow">{escape(kind.title())}</div><h1>Generation {generation} of {escape(str(manifest.get("generations_requested", "?")))}</h1></header>
    {main_visual}
{drift_markup}
    <section class="comparison" aria-label="Text before and after this artifact"><article class="text-record"><h2>{input_label}</h2><p>{escape(str(item["input_text"]))}</p></article><article class="text-record"><h2>{output_label}</h2><p>{escape(str(output_text))}</p></article></section>
    <nav class="work-nav" aria-label="Generation navigation">{previous_link}<span>{index + 1} / {len(items)}</span>{next_link}</nav>
  </main>
  <footer class="run-footer"><div class="run-footer-inner"><section class="footer-context"><div class="eyebrow">About this run</div><h2>{escape(run_title)}</h2><p>{escape(description)}</p></section>{facts}</div></footer>
</section>""")

    listing = (
        f'<div class="thumbs">{"".join(thumbnails)}</div>'
        if thumbnails
        else '<div class="empty">No images have been completed in this run.</div>'
    )
    body = f"""
<section class="run-index active" id="run-index">
  <header class="site-header"><a class="run-link" href="#run-index" aria-current="page">{escape(run_title)}</a><a class="collection-link" href="../">Roomtone Study Collection</a></header>
  <div class="run-hero"><div class="eyebrow">Roomtone run</div><h1>{escape(run_title)}</h1><p>{escape(description)}</p></div>
  <main class="sequence"><header class="sequence-head"><span>The complete image sequence</span><span>{image_count} images · {len(items)} views including seed</span></header>{listing}</main>
{_drift_chart(drift)}
  <footer class="run-footer"><div class="run-footer-inner">{facts}</div></footer>
</section>
{"".join(generation_pages)}
"""
    script = """<script>
(() => {
  const runIndex=document.querySelector('.run-index'), pages=[...document.querySelectorAll('.generation-page')];
  const show=()=>{const match=location.hash.match(/^#generation-(\\d+)$/), target=match&&document.querySelector(location.hash); runIndex.classList.toggle('active',!target); pages.forEach(page=>page.classList.toggle('active',page===target)); window.scrollTo(0,0);};
  window.addEventListener('hashchange',show); document.addEventListener('keydown',event=>{const active=document.querySelector('.generation-page.active'); if(!active)return; const target=active.querySelector(event.key==='ArrowLeft'?'a[rel="prev"]':event.key==='ArrowRight'?'a[rel="next"]':'none'); if(target)location.hash=target.hash;}); show();
  const chart=document.querySelector('.chart-wrap');
  if(chart){
    const svg=chart.querySelector('svg'),guide=chart.querySelector('.chart-guide'),tooltip=chart.querySelector('.chart-tooltip'),markers=[...chart.querySelectorAll('.chart-hover-marker')];
    chart.querySelectorAll('.chart-hover-hit').forEach(hit=>hit.addEventListener('pointermove',event=>{
      const x=hit.dataset.x, previous=hit.dataset.previous, baseline=hit.dataset.baseline;
      guide.setAttribute('x1',x); guide.setAttribute('x2',x); guide.style.display='block';
      [[previous,hit.dataset.previousY],[baseline,hit.dataset.baselineY]].forEach(([value,y],index)=>{const marker=markers[index]; if(value&&y){marker.setAttribute('cx',x); marker.setAttribute('cy',y); marker.style.display='block';}else marker.style.display='none';});
      tooltip.innerHTML=`<strong>Generation ${hit.dataset.generation}</strong>${previous?`Previous: ${Number(previous).toFixed(3)}<br>`:''}Baseline: ${Number(baseline).toFixed(3)}`;
      const bounds=chart.getBoundingClientRect(); tooltip.style.left=`${Math.min(event.clientX-bounds.left+12,bounds.width-150)}px`; tooltip.style.top=`${Math.max(4,event.clientY-bounds.top-54)}px`; tooltip.style.display='block';
    }));
    chart.addEventListener('pointerleave',()=>{guide.style.display='none'; markers.forEach(marker=>marker.style.display='none'); tooltip.style.display='none';});
  }
})();
</script>"""
    destination = run_dir / "index.html"
    destination.write_text(
        _page_shell(f"{run_title} · Roomtone", body, script=script), encoding="utf-8"
    )
    return destination


def generate_runs_index(output_dir: Path) -> Path:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / ".nojekyll").touch()
    cards: list[str] = []
    for run_dir in sorted(output_dir.iterdir(), reverse=True):
        manifest_path = run_dir / "manifest.json"
        if not run_dir.is_dir() or not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        images = [step for step in manifest.get("steps", []) if step.get("output_kind") == "image"]
        summary = manifest.get("summary") or {}
        seed = manifest.get("start") or {}
        seed_preview = seed.get("archived_path") if seed.get("kind") == "image" else None
        preview_path = seed_preview or (images[0]["output_path"] if images else None)
        preview = (
            f'<img src="{escape(run_dir.name + "/" + preview_path, quote=True)}" alt="">'
            if preview_path
            else '<div class="placeholder">Text seed</div>'
        )
        run_title = str(manifest.get("title") or run_dir.name)
        description = _run_description(run_dir, manifest)
        status = str(manifest.get("status", "unknown")).replace("_", " ").title()
        cards.append(f"""
<a class="run" href="{escape(run_dir.name, quote=True)}/">
  <div class="run-frame">{preview}</div>
  <div class="run-copy">
    <div class="eyebrow">{escape(_display_timestamp(str(manifest.get("created_at", ""))))}</div>
    <h2>{escape(run_title)}</h2>
    <p class="run-description">{escape(description)}</p>
    <div class="run-meta">{escape(status)} · {len(images)} generated images · {_format_duration(summary.get("wall_time_seconds"))} · {_format_cost(summary.get("estimated_cost_usd"))}</div>
  </div>
</a>""")
    listing = f'<div class="runs">{"".join(cards)}</div>' if cards else '<div class="empty">No runs yet.</div>'
    body = f"""
<header class="site-header"><a class="run-link" href="./">Roomtone Study Collection</a><a class="collection-link" href="https://github.com/jmcguire/can_ai_do_art">visit roomtone on github</a></header>
<main class="archive"><header class="archive-header"><div class="eyebrow">The complete archive</div><h1>Roomtone Study Collection</h1><p>Text becomes image; image becomes text. Each step knows only the artifact immediately before it.</p></header>{listing}</main>
"""
    destination = output_dir / "index.html"
    destination.write_text(_page_shell("Roomtone Study Collection", body), encoding="utf-8")
    return destination


def refresh_galleries(run_dir: Path, manifest: dict[str, Any]) -> None:
    generate_run_gallery(run_dir, manifest)
    generate_runs_index(run_dir.parent)
