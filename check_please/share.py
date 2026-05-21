"""Zero-storage share URL payloads for check-please."""

from __future__ import annotations

import base64
import datetime as dt
import json
import os
import sys
import zlib
from dataclasses import asdict, replace
from typing import Any, Mapping, Optional
from urllib.parse import urlsplit, urlunsplit

from .html_render import HTML_LANGUAGES, _normalize_footer_for_html, _tip_config
from .models import PriceEstimate, UsageSnapshot, canonical_language
from .render import build_receipt_view, receipt_id


SHARE_PAYLOAD_VERSION = 1
DEFAULT_SHARE_BASE = "https://check-please.example"
SHARE_URL_SIZE_WARNING = 8000


def _clean_base_url(base_url: Optional[str]) -> str:
    base = (base_url or os.environ.get("CHECK_PLEASE_WEB_BASE") or DEFAULT_SHARE_BASE).strip()
    if not base:
        base = DEFAULT_SHARE_BASE
    if "://" not in base:
        base = f"https://{base}"
    parts = urlsplit(base)
    path = parts.path.rstrip("/")
    if not path.endswith("/r"):
        path = f"{path}/r" if path else "/r"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _row(row: Any) -> dict[str, str]:
    return {"label": row.label, "value": row.value}


def _snapshot_payload(snapshot: UsageSnapshot) -> dict[str, Any]:
    data = asdict(snapshot)
    data.pop("source", None)
    data["available_fields"] = list(snapshot.available_fields)
    return data


def _estimate_payload(estimate: PriceEstimate) -> dict[str, Any]:
    return asdict(estimate)


def _receipt_view_payload(view: Any, footer_text: str) -> dict[str, Any]:
    return {
        "language": view.language,
        "logoLabel": view.logo_label,
        "thanksLine": view.thanks_line,
        "receiptIdLine": view.receipt_id_line,
        "dateLine": view.date_line,
        "summaryRows": [_row(row) for row in view.summary_rows],
        "itemHeader": _row(view.item_header),
        "tokenRows": [_row(row) for row in view.token_rows],
        "totalRow": _row(view.total_row),
        "pricingRows": [_row(row) for row in view.pricing_rows],
        "footer": footer_text,
    }


def _receipt_payload(
    snapshot: UsageSnapshot,
    estimate: PriceEstimate,
    width: int,
    agent_tool: str,
    footer: str,
    footer_tone: str,
    conversation_hint: str,
) -> dict[str, Any]:
    views = {
        lang: build_receipt_view(snapshot, estimate, width, agent_tool, footer, footer_tone, conversation_hint, lang)
        for lang in HTML_LANGUAGES
    }
    footer_texts = {}
    for lang in HTML_LANGUAGES:
        footer_text = "\n".join(views[lang].footer_lines)
        footer_texts[lang] = _normalize_footer_for_html(footer_text, lang)
    tip = {
        lang: _tip_config(snapshot, estimate, footer_tone, width, lang, conversation_hint, footer_texts[lang])
        for lang in HTML_LANGUAGES
    }
    receipt = {
        "agentTool": agent_tool if agent_tool in {"claude-code", "codex", "gemini", "generic"} else "generic",
        "receiptId": views["en"].barcode_id_line,
        "barcode": views["en"].barcode_line.strip(),
        "languages": {
            lang: _receipt_view_payload(views[lang], footer_texts[lang])
            for lang in HTML_LANGUAGES
        },
        "tip": tip,
    }
    return receipt


def build_share_payload(
    snapshot: UsageSnapshot,
    estimate: PriceEstimate,
    width: int,
    agent_tool: str,
    footer: str,
    footer_tone: str,
    conversation_hint: str,
    language: str,
) -> dict[str, Any]:
    payload_timestamp = snapshot.timestamp or dt.datetime.now(dt.timezone.utc).isoformat()
    payload_snapshot = snapshot if snapshot.timestamp else replace(snapshot, timestamp=payload_timestamp)
    rid = receipt_id(payload_snapshot, payload_snapshot.provider)
    return {
        "v": SHARE_PAYLOAD_VERSION,
        "kind": "single-receipt",
        "language": canonical_language(language),
        "agentTool": agent_tool,
        "receiptId": rid,
        "date": payload_timestamp,
        "snapshot": _snapshot_payload(payload_snapshot),
        "estimate": _estimate_payload(estimate),
        "receipt": _receipt_payload(payload_snapshot, estimate, width, agent_tool, footer, footer_tone, conversation_hint),
    }


def encode_share_payload(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    compressed = zlib.compress(raw, level=9)
    return base64.urlsafe_b64encode(compressed).decode("ascii").rstrip("=")


def decode_share_payload(fragment: str) -> dict[str, Any]:
    token = fragment.strip()
    if token.startswith("#"):
        token = token[1:]
    padding = "=" * (-len(token) % 4)
    compressed = base64.urlsafe_b64decode((token + padding).encode("ascii"))
    data = zlib.decompress(compressed)
    payload = json.loads(data.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("share payload must decode to an object")
    return payload


def build_share_url(payload: Mapping[str, Any], base_url: Optional[str] = None) -> str:
    return f"{_clean_base_url(base_url)}#{encode_share_payload(payload)}"


def warn_if_large_share_url(url: str) -> None:
    if len(url) > SHARE_URL_SIZE_WARNING:
        print(
            f"warning: share URL is {len(url)} characters; some apps may truncate very long URLs",
            file=sys.stderr,
        )
