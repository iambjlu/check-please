"""Claude Code SessionEnd hook helpers for token receipt."""

from __future__ import annotations

import datetime as dt
import json
import shlex
from pathlib import Path
from typing import Any, Dict, Optional

from .cli import format_chat_reply, open_in_default_browser
from .data import (
    estimate_cost,
    find_claude_transcript_for_session,
    load_daily_snapshot_claude,
    load_snapshot_from_claude_transcript,
)
from .html_render import render_receipt_html
from .models import DEFAULT_PRICING
from .render import render_receipt


DEFAULT_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
DEFAULT_HOOK_ROOT = Path.home() / ".codex" / "skills" / "check-please"
HOOK_SCRIPT_RELATIVE = Path("scripts") / "claude_session_end_hook.py"
HOOK_MARKER = str(HOOK_SCRIPT_RELATIVE)
DEFAULT_HTML_EXPORT = Path("/tmp/check-please.html")
DAILY_HTML_EXPORT = Path("/tmp/check-please-daily.html")
DEFAULT_RECEIPT_CONFIG_PATH = Path.home() / ".claude" / "check-please.json"
# session_receipt: print a receipt for the closing session on SessionEnd.
# daily_receipt: also print the running total for the current local day.
DEFAULT_RECEIPT_CONFIG = {"session_receipt": True, "daily_receipt": False}


def load_receipt_config(path: Optional[Path] = None) -> Dict[str, bool]:
    config = dict(DEFAULT_RECEIPT_CONFIG)
    target = path or DEFAULT_RECEIPT_CONFIG_PATH
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return config
    if isinstance(data, dict):
        for key in config:
            if isinstance(data.get(key), bool):
                config[key] = data[key]
    return config


def save_receipt_config(updates: Dict[str, bool], path: Optional[Path] = None) -> Dict[str, bool]:
    target = path or DEFAULT_RECEIPT_CONFIG_PATH
    config = load_receipt_config(target)
    for key, value in updates.items():
        if key in config and isinstance(value, bool):
            config[key] = value
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return config


def build_claude_hook_command(hook_root: Optional[Path] = None, python_bin: str = "python3") -> str:
    root = (hook_root or DEFAULT_HOOK_ROOT).expanduser()
    script_path = root / HOOK_SCRIPT_RELATIVE
    return f"{python_bin} {shlex.quote(str(script_path))}"


def build_session_end_hook_entry(command: str) -> Dict[str, Any]:
    return {
        "matcher": "*",
        "hooks": [
            {
                "type": "command",
                "command": command,
                "timeout": 30,
            }
        ],
    }


def load_settings(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise SystemExit(f"Expected a JSON object in {path}")
    return data


def save_settings(path: Path, settings: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def _strip_existing_check_please_hooks(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for entry in entries:
        hooks = entry.get("hooks")
        if not isinstance(hooks, list):
            kept.append(entry)
            continue
        commands = [
            hook.get("command", "")
            for hook in hooks
            if isinstance(hook, dict) and hook.get("type") == "command"
        ]
        if any(HOOK_MARKER in str(command) for command in commands):
            continue
        kept.append(entry)
    return kept


def install_session_end_hook(
    settings_path: Path = DEFAULT_SETTINGS_PATH,
    hook_root: Optional[Path] = None,
    python_bin: str = "python3",
) -> Dict[str, Any]:
    settings = load_settings(settings_path)
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise SystemExit(f"'hooks' must be an object in {settings_path}")
    existing = hooks.get("SessionEnd") or []
    if not isinstance(existing, list):
        raise SystemExit(f"'hooks.SessionEnd' must be a list in {settings_path}")
    command = build_claude_hook_command(hook_root, python_bin)
    hooks["SessionEnd"] = _strip_existing_check_please_hooks(existing) + [
        build_session_end_hook_entry(command)
    ]
    save_settings(settings_path, settings)
    return {
        "settings_path": str(settings_path),
        "installed": True,
        "command": command,
    }


def uninstall_session_end_hook(settings_path: Path = DEFAULT_SETTINGS_PATH) -> Dict[str, Any]:
    settings = load_settings(settings_path)
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return {
            "settings_path": str(settings_path),
            "removed": False,
            "reason": "hooks_missing",
        }
    existing = hooks.get("SessionEnd") or []
    if not isinstance(existing, list):
        return {
            "settings_path": str(settings_path),
            "removed": False,
            "reason": "session_end_not_list",
        }
    cleaned = _strip_existing_check_please_hooks(existing)
    if cleaned:
        hooks["SessionEnd"] = cleaned
    else:
        hooks.pop("SessionEnd", None)
    save_settings(settings_path, settings)
    return {
        "settings_path": str(settings_path),
        "removed": len(cleaned) != len(existing),
    }


def _render_receipt_pair(snapshot, pricing_path: Path, width: int, html_target: Path) -> str:
    estimate = estimate_cost(snapshot, pricing_path)
    receipt_text = render_receipt(
        snapshot=snapshot,
        estimate=estimate,
        width=width,
        agent_tool="claude-code",
        footer="auto",
        footer_tone="auto",
        conversation_hint="",
    )
    html_receipt = render_receipt_html(
        snapshot=snapshot,
        estimate=estimate,
        width=width,
        agent_tool="claude-code",
        footer="auto",
        footer_tone="auto",
        conversation_hint="",
        language="en",
    )
    html_target.write_text(html_receipt + "\n", encoding="utf-8")
    open_in_default_browser(html_target)
    return format_chat_reply(receipt_text, html_target)


def build_session_end_system_message(
    hook_input: Dict[str, Any],
    pricing_path: Path = DEFAULT_PRICING,
    width: int = 48,
    config: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    receipt_config = config or load_receipt_config()
    if not receipt_config.get("session_receipt") and not receipt_config.get("daily_receipt"):
        return {"continue": True, "suppressOutput": True}

    session_id = str(hook_input.get("session_id") or "")
    transcript_path = hook_input.get("transcript_path")
    transcript = Path(transcript_path) if isinstance(transcript_path, str) and transcript_path else None
    if transcript is None or not transcript.exists():
        transcript = find_claude_transcript_for_session(session_id)

    sections = []

    if receipt_config.get("session_receipt") and transcript and transcript.exists():
        try:
            snapshot = load_snapshot_from_claude_transcript(
                transcript, "session", model_override=None, provider_override=None
            )
        except SystemExit:
            snapshot = None
        if snapshot is not None:
            sections.append(_render_receipt_pair(snapshot, pricing_path, width, DEFAULT_HTML_EXPORT))

    if receipt_config.get("daily_receipt"):
        try:
            daily_snapshot = load_daily_snapshot_claude(dt.date.today(), None, None)
        except SystemExit:
            daily_snapshot = None
        if daily_snapshot is not None:
            sections.append(_render_receipt_pair(daily_snapshot, pricing_path, width, DAILY_HTML_EXPORT))

    if not sections:
        return {
            "continue": True,
            "suppressOutput": True,
            "systemMessage": "Check Please skipped: no Claude transcript or usage log found.",
        }
    return {
        "continue": True,
        "suppressOutput": True,
        "systemMessage": "\n\n".join(sections),
    }
