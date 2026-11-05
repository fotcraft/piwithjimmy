"""Vision-language model OCR, used for handwriting (Greek in particular).

Azure's OCR does not support Greek handwriting. Large vision-language models
read it well, so the pipeline sends the image here when Azure reports
handwriting, low confidence or no text.

Providers (set vlm.provider in config.yaml):
- azure_openai: an Azure OpenAI vision deployment (keeps billing on Azure)
                key: AZURE_OPENAI_KEY
- openai:       OpenAI API                          key: OPENAI_API_KEY
- anthropic:    Anthropic API                       key: ANTHROPIC_API_KEY

The model returns no confidence score, so results get vlm.assumed_confidence.
"""
import base64
import logging
import os
from typing import Any, Dict, Optional

import requests

from app.vision.cloud_ocr import encode_jpeg
from app.vision.types import OcrResult

logger = logging.getLogger(__name__)

NO_TEXT = "NO_TEXT"

PROMPT = (
    "You are the OCR engine of a reading device for blind and visually impaired "
    "people. Transcribe all readable text in this photo exactly as written, in "
    "natural reading order. The text may be printed or handwritten, in Greek, "
    "English or both. Keep the original language and spelling; do not translate, "
    "summarise, correct or describe anything. Ignore text that is cut off at the "
    "image edge if it cannot be read. Output only the transcribed text. If there "
    f"is no readable text, output exactly {NO_TEXT}."
)

_DEFAULT_KEY_ENV = {
    "azure_openai": "AZURE_OPENAI_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


class VlmOcr:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.enabled = bool(config.get("enabled", False))
        self.provider = config.get("provider", "azure_openai")
        key_env = config.get("key_env") or _DEFAULT_KEY_ENV.get(self.provider, "")
        self.key = config.get("key") or (os.getenv(key_env, "") if key_env else "")
        self.endpoint = config.get("endpoint", "")
        self.deployment = config.get("deployment", "")
        self.api_version = config.get("api_version", "2024-10-21")
        self.model = config.get("model", "")
        self.timeout = float(config.get("timeout_seconds", 20))
        self.max_side = int(config.get("max_image_side", 1600))
        self.max_tokens = int(config.get("max_tokens", 2000))
        self.assumed_confidence = float(config.get("assumed_confidence", 80.0))

    def is_configured(self) -> bool:
        if not (self.enabled and self.key):
            return False
        if self.provider == "azure_openai":
            return bool(self.endpoint and self.deployment)
        return bool(self.model)

    def base_url(self) -> str:
        if self.provider == "azure_openai":
            return self.endpoint
        if self.provider == "anthropic":
            return "https://api.anthropic.com"
        return "https://api.openai.com"

    def run(self, image) -> Optional[OcrResult]:
        if not self.is_configured():
            return None
        jpeg = encode_jpeg(image, max_bytes=3 * 1024 * 1024, max_side=self.max_side)
        if jpeg is None:
            logger.error("VLM OCR: failed to encode image")
            return None
        b64 = base64.b64encode(jpeg).decode("ascii")
        try:
            if self.provider == "anthropic":
                text = self._call_anthropic(b64)
            else:
                text = self._call_openai_style(b64)
        except requests.RequestException as exc:
            logger.error("VLM OCR request failed: %s", exc)
            return None
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            logger.error("VLM OCR: unexpected response format: %s", exc)
            return None
        if text is None:
            return None
        text = text.strip()
        if not text or text == NO_TEXT:
            logger.info("VLM OCR: no text")
            return OcrResult("", 0.0, False, f"vlm_{self.provider}")
        logger.info("VLM OCR (%s): %d chars", self.provider, len(text))
        return OcrResult(text, self.assumed_confidence, True, f"vlm_{self.provider}")

    # ------------------------------------------------------------ providers
    def _call_openai_style(self, b64: str) -> Optional[str]:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"},
                    },
                ],
            }
        ]
        body: Dict[str, Any] = {"messages": messages, "max_tokens": self.max_tokens, "temperature": 0}
        if self.provider == "azure_openai":
            url = (
                f"{self.endpoint.rstrip('/')}/openai/deployments/{self.deployment}"
                f"/chat/completions?api-version={self.api_version}"
            )
            headers = {"api-key": self.key, "Content-Type": "application/json"}
        else:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
            body["model"] = self.model
        resp = requests.post(url, headers=headers, json=body, timeout=self.timeout)
        if resp.status_code != 200:
            logger.error("VLM OCR HTTP %d: %s", resp.status_code, resp.text[:200])
            return None
        return resp.json()["choices"][0]["message"]["content"] or ""

    def _call_anthropic(self, b64: str) -> Optional[str]:
        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
                        },
                        {"type": "text", "text": PROMPT},
                    ],
                }
            ],
        }
        headers = {
            "x-api-key": self.key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        resp = requests.post(
            "https://api.anthropic.com/v1/messages", headers=headers, json=body, timeout=self.timeout
        )
        if resp.status_code != 200:
            logger.error("VLM OCR HTTP %d: %s", resp.status_code, resp.text[:200])
            return None
        parts = resp.json()["content"]
        return "".join(p.get("text", "") for p in parts if p.get("type") == "text")
