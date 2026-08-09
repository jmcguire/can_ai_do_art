from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any


PRICING_AS_OF = "2026-08-09"
PRICING_RATES_PER_MILLION_TOKENS = {
    "gpt-image-2": {
        "text_input": 5.00,
        "image_input": 8.00,
        "image_output": 30.00,
    },
    "gpt-5.6-sol": {
        "uncached_input": 5.00,
        "cached_input": 0.50,
        "cache_write_input": 6.25,
        "output": 30.00,
    },
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _seconds_between(start: str, end: str) -> float | None:
    try:
        return round(
            (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds(),
            3,
        )
    except (TypeError, ValueError):
        return None


def _token_cost(model: str, usage: dict[str, Any]) -> float | None:
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    input_details = usage.get("input_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or {}

    if model == "gpt-image-2":
        rates = PRICING_RATES_PER_MILLION_TOKENS["gpt-image-2"]
        image_input = int(input_details.get("image_tokens") or 0)
        text_input = int(input_details.get("text_tokens") or (input_tokens - image_input))
        image_output = int(output_details.get("image_tokens") or output_tokens)
        return (
            text_input * rates["text_input"]
            + image_input * rates["image_input"]
            + image_output * rates["image_output"]
        ) / 1_000_000

    if model in {"gpt-5.6", "gpt-5.6-sol"}:
        rates = PRICING_RATES_PER_MILLION_TOKENS["gpt-5.6-sol"]
        cached = int(input_details.get("cached_tokens") or 0)
        cache_writes = int(input_details.get("cache_write_tokens") or 0)
        regular = max(input_tokens - cached - cache_writes, 0)
        return (
            regular * rates["uncached_input"]
            + cached * rates["cached_input"]
            + cache_writes * rates["cache_write_input"]
            + output_tokens * rates["output"]
        ) / 1_000_000

    return None


def summarize_run(
    run_dir: Path, manifest: dict[str, Any], completed_at: str
) -> dict[str, Any]:
    by_model: dict[str, dict[str, int]] = {}
    total_input = 0
    total_output = 0
    total_tokens = 0
    estimated_cost = 0.0
    priced_requests = 0
    unpriced_models: set[str] = set()
    generated_bytes = 0
    elapsed_values: list[float] = []

    for step in manifest.get("steps", []):
        step_dir = run_dir / Path(step["output_path"]).parent
        request = _read_json(step_dir / "request.json")
        response = _read_json(step_dir / "response.json")
        usage = response.get("usage") or {}
        model = str(response.get("model") or request.get("model") or "unknown")
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        tokens = int(usage.get("total_tokens") or (input_tokens + output_tokens))
        if tokens:
            model_usage = by_model.setdefault(
                model, {"requests": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            )
            model_usage["requests"] += 1
            model_usage["input_tokens"] += input_tokens
            model_usage["output_tokens"] += output_tokens
            model_usage["total_tokens"] += tokens
            total_input += input_tokens
            total_output += output_tokens
            total_tokens += tokens
            cost = _token_cost(model, usage)
            if cost is None:
                unpriced_models.add(model)
            else:
                priced_requests += 1
                estimated_cost += cost

        output_path = run_dir / step["output_path"]
        try:
            generated_bytes += output_path.stat().st_size
        except OSError:
            pass
        elapsed = step.get("elapsed_seconds")
        if isinstance(elapsed, (int, float)):
            elapsed_values.append(float(elapsed))

    wall_time = _seconds_between(str(manifest.get("created_at", "")), completed_at)
    image_count = sum(s.get("output_kind") == "image" for s in manifest.get("steps", []))
    text_count = sum(s.get("output_kind") == "text" for s in manifest.get("steps", []))
    return {
        "completed_at": completed_at,
        "wall_time_seconds": wall_time,
        "transformations_completed": len(manifest.get("steps", [])),
        "successful_api_requests": len(manifest.get("steps", [])),
        "images_generated": image_count,
        "descriptions_generated": text_count,
        "generated_artifact_bytes": generated_bytes,
        "timed_transformations": len(elapsed_values),
        "measured_processing_seconds": round(sum(elapsed_values), 3),
        "average_measured_transformation_seconds": (
            round(sum(elapsed_values) / len(elapsed_values), 3)
            if elapsed_values
            else None
        ),
        "tokens": {
            "input": total_input,
            "output": total_output,
            "total": total_tokens,
            "by_model": by_model,
        },
        "estimated_cost_usd": (
            round(estimated_cost, 6) if priced_requests else None
        ),
        "pricing": {
            "as_of": PRICING_AS_OF,
            "basis": "OpenAI standard API token pricing; regional or service-tier uplifts are not included.",
            "currency": "USD",
            "is_estimate": True,
            "rates_per_million_tokens": PRICING_RATES_PER_MILLION_TOKENS,
            "unpriced_models": sorted(unpriced_models),
        },
    }
