from __future__ import annotations

from datetime import datetime
from html import escape
import json
from pathlib import Path
from typing import Any


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


def _page_shell(title: str, body: str, *, script: str = "") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>{escape(title)}</title>
  <style>
    :root {{ --ink:#f4efe6; --muted:#aaa49a; --paper:#11110f; --panel:#1b1a17; --line:#38352f; --accent:#d8b77a; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--paper); color:var(--ink); font:16px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; }}
    a {{ color:var(--accent); }}
    main {{ width:min(1120px, calc(100% - 32px)); margin:0 auto; padding:42px 0 64px; }}
    header {{ margin-bottom:30px; }}
    h1 {{ margin:.15em 0; font:clamp(2rem,6vw,4.6rem)/.95 Georgia,serif; font-weight:400; letter-spacing:-.04em; }}
    h2 {{ font:1.4rem/1.2 Georgia,serif; font-weight:400; }}
    .eyebrow,.meta {{ color:var(--muted); text-transform:uppercase; letter-spacing:.08em; font-size:.78rem; }}
    .deck {{ color:#cbc5ba; max-width:68ch; }}
    .facts {{ display:flex; flex-wrap:wrap; gap:8px; margin:22px 0; }}
    .fact {{ min-width:150px; padding:10px 12px; border:1px solid var(--line); background:var(--panel); }}
    .fact strong {{ display:block; color:var(--ink); font-size:1.1rem; }}
    .stage {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(260px,360px); gap:24px; align-items:start; }}
    .stage > * {{ min-width:0; }}
    .frame {{ background:var(--panel); border:1px solid var(--line); border-radius:4px; overflow:hidden; }}
    .slide,.slide-notes {{ display:none; }} .slide.active,.slide-notes.active {{ display:block; }}
    .slide {{ margin:0; }}
    .slide img {{ display:block; width:100%; height:auto; aspect-ratio:1; object-fit:contain; background:#090908; }}
    .text-seed {{ display:grid; place-items:center; min-height:min(70vh,760px); padding:clamp(24px,7vw,80px); background:#171612; }}
    .text-seed pre {{ margin:0; max-width:42ch; white-space:pre-wrap; overflow-wrap:anywhere; font:clamp(1.2rem,3vw,2.2rem)/1.45 Georgia,serif; }}
    .caption {{ padding:14px 16px; border-top:1px solid var(--line); }}
    .notes {{ background:var(--panel); border:1px solid var(--line); padding:18px; max-height:72vh; overflow:auto; }}
    .notes pre {{ color:#d2ccc1; white-space:pre-wrap; overflow-wrap:anywhere; font:13px/1.55 inherit; margin:8px 0 22px; }}
    .controls {{ display:flex; gap:10px; align-items:center; margin:16px 0; }}
    button {{ appearance:none; border:1px solid var(--line); background:var(--panel); color:var(--ink); padding:10px 14px; font:inherit; cursor:pointer; }}
    button:hover,button:focus-visible {{ border-color:var(--accent); }}
    #counter {{ margin-left:auto; color:var(--muted); }}
    .thumbs {{ display:flex; gap:8px; max-width:100%; overflow-x:auto; padding-bottom:8px; }}
    .thumb {{ padding:0; flex:0 0 72px; opacity:.55; }} .thumb.active {{ opacity:1; border-color:var(--accent); }}
    .thumb img {{ width:70px; height:70px; display:block; object-fit:cover; }}
    .text-thumb {{ display:grid; place-items:center; width:70px; height:70px; color:var(--accent); font-weight:700; }}
    .runs {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(270px,1fr)); gap:18px; }}
    .run {{ display:block; color:inherit; text-decoration:none; border:1px solid var(--line); background:var(--panel); }}
    .run:hover {{ border-color:var(--accent); }} .run img,.placeholder {{ display:block; width:100%; aspect-ratio:1.6; object-fit:cover; background:#0a0a09; }}
    .placeholder {{ display:grid; place-items:center; color:var(--muted); }}
    .run-copy {{ padding:16px; }} .run-copy h2 {{ margin:0 0 8px; }}
    .status {{ display:inline-block; padding:2px 6px; border:1px solid var(--line); margin-top:10px; }}
    .empty {{ padding:48px; border:1px solid var(--line); color:var(--muted); text-align:center; }}
    @media (max-width:760px) {{ .stage {{ grid-template-columns:1fr; }} .notes {{ max-height:none; }} main {{ padding-top:26px; }} }}
  </style>
</head>
<body><main>{body}</main>{script}</body>
</html>
"""


def generate_run_gallery(run_dir: Path, manifest: dict[str, Any] | None = None) -> Path:
    run_dir = run_dir.resolve()
    if manifest is None:
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    steps = manifest.get("steps", [])
    images = [step for step in steps if step.get("output_kind") == "image"]
    seed = manifest["start"]
    gallery_items = [
        {
            "number": 0,
            "kind": seed["kind"],
            "path": seed["archived_path"],
            "input_text": _read_text(run_dir / seed["archived_path"])
            if seed["kind"] == "text"
            else "Original image seed.",
        }
    ]
    gallery_items.extend(
        {
            "number": step["number"],
            "kind": "image",
            "path": step["output_path"],
            "input_text": _read_text(run_dir / step["input_path"]),
        }
        for step in images
    )
    slides: list[str] = []
    thumbs: list[str] = []
    note_sections: list[str] = []
    for index, item in enumerate(gallery_items):
        artifact_path = item["path"]
        generation = item["number"]
        next_description = ""
        for candidate in steps:
            if (
                candidate.get("input_path") == artifact_path
                and candidate.get("output_kind") == "text"
            ):
                next_description = _read_text(run_dir / candidate["output_path"])
                break
        active = " active" if index == 0 else ""
        if item["kind"] == "image":
            visual = f'<img src="{escape(artifact_path, quote=True)}" alt="Generation {generation}">'
            thumbnail = f'<img src="{escape(artifact_path, quote=True)}" alt="">'
        else:
            visual = f'<div class="text-seed"><pre>{escape(item["input_text"])}</pre></div>'
            thumbnail = '<span class="text-thumb">TXT</span>'
        slides.append(
            f'<figure class="slide{active}" data-index="{index}" data-generation="{generation}">'
            f'{visual}<figcaption class="caption">Generation {generation} · {escape(artifact_path)}</figcaption>'
            "</figure>"
        )
        thumbs.append(
            f'<button class="thumb{active}" data-index="{index}" aria-label="Show generation {generation}">'
            f'{thumbnail}</button>'
        )
        if generation == 0:
            input_label = "Starting text" if item["kind"] == "text" else "Starting image"
        else:
            input_label = f"Input to generation {generation}"
        result_label = (
            "First generated artifact"
            if generation == 0 and item["kind"] == "text"
            else "Description produced from this image"
        )
        result_text = next_description or (
            "The first generated image follows this seed."
            if generation == 0 and item["kind"] == "text"
            else "Not generated in this run."
        )
        note_sections.append(
            f'<section class="slide-notes{active}" data-index="{index}">'
            f'<div class="eyebrow">{input_label}</div>'
            f'<pre>{escape(item["input_text"])}</pre>'
            f'<div class="eyebrow">{result_label}</div>'
            f'<pre>{escape(result_text)}</pre>'
            "</section>"
        )

    if gallery_items:
        notes = "".join(note_sections)
        gallery = (
            '<div class="stage"><div><div class="frame">'
            + "".join(slides)
            + '</div><div class="controls"><button id="prev">← Previous</button>'
            + '<button id="next">Next →</button><span id="counter"></span></div>'
            + f'<nav class="thumbs" aria-label="Generations">{"".join(thumbs)}</nav></div>'
            + f'<aside class="notes">{notes}</aside></div>'
        )
    else:
        gallery = '<div class="empty">No images have been completed in this run.</div>'

    run_title = str(manifest.get("title") or run_dir.name)
    title = f"{run_title} · Roomtone"
    summary = manifest.get("summary") or {}
    tokens = (summary.get("tokens") or {}).get("total")
    facts = ""
    if summary:
        facts = f"""<div class="facts">
    <div class="fact"><span class="eyebrow">Elapsed</span><strong>{_format_duration(summary.get("wall_time_seconds"))}</strong></div>
    <div class="fact"><span class="eyebrow">Tokens</span><strong>{tokens:,}</strong></div>
    <div class="fact"><span class="eyebrow">Est. cost</span><strong>{_format_cost(summary.get("estimated_cost_usd"))}</strong></div>
    <div class="fact"><span class="eyebrow">Artifacts</span><strong>{len(images)} images</strong></div>
  </div>"""
    body = f"""
<header>
  <div class="eyebrow"><a href="../">Roomtone runs</a> / {escape(run_dir.name)}</div>
  <h1>{escape(run_title)}</h1>
  <p class="deck">{len(images)} images across {len(steps)} completed transformations. Status: {escape(str(manifest.get("status", "unknown")))}.</p>
  <p class="meta">Started {_display_timestamp(str(manifest.get("created_at", "")))} · {escape(str(manifest.get("effective_settings", {}).get("image_model", "")))} ↔ {escape(str(manifest.get("effective_settings", {}).get("vision_model", "")))}</p>
{facts}
</header>
{gallery}
"""
    script = ""
    if gallery_items:
        script = """<script>
(() => {
  const slides=[...document.querySelectorAll('.slide')], notes=[...document.querySelectorAll('.slide-notes')], thumbs=[...document.querySelectorAll('.thumb')];
  let current=0;
  const show=(n)=>{ current=(n+slides.length)%slides.length; [...slides,...notes,...thumbs].forEach(el=>el.classList.toggle('active',Number(el.dataset.index)===current)); document.querySelector('#counter').textContent=`Generation ${slides[current].dataset.generation} · ${current+1} / ${slides.length}`; thumbs[current].scrollIntoView({behavior:'smooth',block:'nearest',inline:'center'}); };
  document.querySelector('#prev').addEventListener('click',()=>show(current-1)); document.querySelector('#next').addEventListener('click',()=>show(current+1)); thumbs.forEach(el=>el.addEventListener('click',()=>show(Number(el.dataset.index)))); document.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')show(current-1);if(e.key==='ArrowRight')show(current+1)}); show(0);
})();
</script>"""
    destination = run_dir / "index.html"
    destination.write_text(_page_shell(title, body, script=script), encoding="utf-8")
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
        images = [s for s in manifest.get("steps", []) if s.get("output_kind") == "image"]
        summary = manifest.get("summary") or {}
        seed = manifest.get("start") or {}
        seed_preview = seed.get("archived_path") if seed.get("kind") == "image" else None
        preview_path = seed_preview or (images[0]["output_path"] if images else None)
        preview = (
            f'<img src="{escape(run_dir.name + "/" + preview_path, quote=True)}" alt="">'
            if preview_path else '<div class="placeholder">Text seed</div>'
        )
        run_title = str(manifest.get("title") or run_dir.name)
        cards.append(f"""
<a class="run" href="{escape(run_dir.name, quote=True)}/">
  {preview}
  <div class="run-copy">
    <div class="eyebrow">{_display_timestamp(str(manifest.get("created_at", "")))}</div>
    <h2>{escape(run_title)}</h2>
    <div>{len(images)} images · {len(manifest.get("steps", []))} / {manifest.get("generations_requested", "?")} transformations</div>
    <div>{_format_duration(summary.get("wall_time_seconds"))} · {_format_cost(summary.get("estimated_cost_usd"))}</div>
    <span class="status">{escape(str(manifest.get("status", "unknown")))}</span>
  </div>
</a>""")
    listing = '<div class="runs">' + "".join(cards) + "</div>" if cards else '<div class="empty">No runs yet.</div>'
    body = f"""
<header>
  <div class="eyebrow">Roomtone archive</div>
  <h1>Every image leaves an echo.</h1>
  <p class="deck">Text becomes image; image becomes text. Each step knows only the artifact immediately before it.</p>
</header>
{listing}
"""
    destination = output_dir / "index.html"
    destination.write_text(_page_shell("Roomtone runs", body), encoding="utf-8")
    return destination


def refresh_galleries(run_dir: Path, manifest: dict[str, Any]) -> None:
    generate_run_gallery(run_dir, manifest)
    generate_runs_index(run_dir.parent)
