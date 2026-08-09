from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
import mimetypes
from pathlib import Path
import random
import time
from typing import Any, Callable, TypeVar

from .config import Settings


T = TypeVar("T")


def _jsonable(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if isinstance(response, dict):
        return deepcopy(response)
    raise TypeError(f"Cannot serialize response type: {type(response).__name__}")


def _retry(
    call: Callable[[], T], settings: Settings, retryable: tuple[type[Exception], ...]
) -> T:
    delay = settings.retry_initial_delay_seconds
    for attempt in range(1, settings.retry_attempts + 1):
        try:
            return call()
        except (KeyboardInterrupt, SystemExit):
            raise
        except retryable:
            if attempt == settings.retry_attempts:
                raise
            time.sleep(min(delay, settings.retry_max_delay_seconds) * random.uniform(0.8, 1.2))
            delay = min(delay * 2, settings.retry_max_delay_seconds)
    raise RuntimeError("unreachable")


class OpenAIProvider:
    def __init__(self, settings: Settings):
        try:
            from openai import (
                APIConnectionError,
                APITimeoutError,
                InternalServerError,
                OpenAI,
                RateLimitError,
            )
        except ImportError as exc:
            raise RuntimeError(
                "The OpenAI package is not installed. Run `python -m pip install -e .`."
            ) from exc
        self.settings = settings
        self.client = OpenAI(timeout=settings.timeout_seconds)
        self.retryable = (
            APIConnectionError,
            APITimeoutError,
            InternalServerError,
            RateLimitError,
        )

    def text_to_image(
        self, prompt: str, destination: Path
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        request = {
            "model": self.settings.image_model,
            "prompt": prompt,
            "size": self.settings.image_size,
            "quality": self.settings.image_quality,
            "output_format": self.settings.image_format,
            "n": 1,
        }
        response = _retry(
            lambda: self.client.images.generate(**request),
            self.settings,
            self.retryable,
        )
        raw = _jsonable(response)
        data = raw.get("data") or []
        if not data or not data[0].get("b64_json"):
            raise RuntimeError("OpenAI returned no base64 image data")
        image_bytes = base64.b64decode(data[0]["b64_json"], validate=True)
        destination.write_bytes(image_bytes)

        preserved = deepcopy(raw)
        preserved["data"][0]["b64_json"] = {
            "saved_to": destination.name,
            "bytes": len(image_bytes),
            "sha256": hashlib.sha256(image_bytes).hexdigest(),
            "encoding_note": "Original base64 decoded into the saved image file.",
        }
        return request, preserved

    def image_to_text(
        self, image_path: Path, prompt: str
    ) -> tuple[dict[str, Any], dict[str, Any], str]:
        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
        image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        api_request = {
            "model": self.settings.vision_model,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_image",
                            "image_url": f"data:{mime_type};base64,{image_b64}",
                            "detail": self.settings.vision_detail,
                        },
                    ],
                }
            ],
            "reasoning": {"effort": self.settings.reasoning_effort},
            "max_output_tokens": self.settings.max_output_tokens,
        }
        response = _retry(
            lambda: self.client.responses.create(**api_request),
            self.settings,
            self.retryable,
        )
        text = getattr(response, "output_text", "").strip()
        if not text:
            raise RuntimeError("OpenAI returned no image description")

        archived_request = deepcopy(api_request)
        archived_request["input"][0]["content"][1]["image_url"] = {
            "source_file": str(image_path),
            "sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
            "encoding_note": "Sent as a base64 data URL; duplicate bytes omitted here.",
        }
        return archived_request, _jsonable(response), text


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
