"""Receipt rendering for token receipt."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
import time
from typing import List, Tuple

from .models import (
    ALLOWED_WIDTHS,
    DEFAULT_LANGUAGE,
    PriceEstimate,
    UsageSnapshot,
    canonical_language,
    center_text_visual,
    display_time,
    fmt_int,
    normalize,
    parse_iso,
    printable_receipt_char,
    truncate_visual,
    visual_char_width,
    visual_display_width,
)


FOOTER_COPY_PATH = Path(__file__).with_name("footer_copy.json")


LABELS = {
    "en": {
        "generic_logo": "[ AI CHECKOUT ]",
        "thanks": "THANK YOU FOR CODING WITH {product}",
        "receipt_id": "RECEIPT #: {rid}",
        "date": "DATE: {date}",
        "provider": "PROVIDER",
        "model": "MODEL",
        "context": "CONTEXT USED",
        "item": "ITEM",
        "tokens": "TOKENS",
        "input": "Input Tokens",
        "output": "Output Tokens",
        "cached": "Cache Read Tokens",
        "reasoning": "Reasoning Tokens",
        "cache_write": "Cache Write Tokens",
        "total": "TOTAL",
        "token_unit": "TOKENS",
        "estimate": "{currency} ESTIMATE",
        "price": "PRICE",
        "price_date": "PRICE DATE",
        "rate_note": "RATE NOTE",
        "unmapped": "UNMAPPED",
        "sessions": "SESSIONS",
        "models": "{count} MODELS",
        "daily_logo": "DAILY TOTAL",
        "daily_thanks": "THANK YOU FOR CODING TODAY",
        "alltime_logo": "ALL-TIME TOTAL",
        "alltime_thanks": "THANK YOU FOR ALL THE CODE",
    },
    "zh-TW": {
        "generic_logo": "[ AI 結帳 ]",
        "thanks": "感謝使用 {product}",
        "receipt_id": "收據號碼: {rid}",
        "date": "日期: {date}",
        "provider": "供應商",
        "model": "模型",
        "context": "已用上下文",
        "item": "項目",
        "tokens": "TOKEN",
        "input": "輸入 Tokens",
        "output": "輸出 Tokens",
        "cached": "快取讀取",
        "reasoning": "推理 Tokens",
        "cache_write": "快取寫入",
        "total": "總計",
        "token_unit": "Tokens",
        "estimate": "{currency} 預估",
        "price": "價格對應",
        "price_date": "價格日期",
        "rate_note": "價格說明",
        "unmapped": "未對應",
        "sessions": "會話數",
        "models": "{count} 個模型",
        "daily_logo": "全日帳單",
        "daily_thanks": "感謝今天也好好寫了 code",
        "alltime_logo": "歷史總帳單",
        "alltime_thanks": "感謝這台電腦上每一行 code",
    },
    "cantonese": {
        "generic_logo": "[ AI 埋單 ]",
        "thanks": "多謝使用 {product}",
        "receipt_id": "單號: {rid}",
        "date": "日期: {date}",
        "provider": "供應商",
        "model": "模型",
        "context": "已用上下文",
        "item": "項目",
        "tokens": "TOKEN",
        "input": "輸入 Tokens",
        "output": "輸出 Tokens",
        "cached": "快取讀取",
        "reasoning": "推理 Tokens",
        "cache_write": "快取寫入",
        "total": "總數",
        "token_unit": "Tokens",
        "estimate": "{currency} 估算",
        "price": "價格對應",
        "price_date": "價格日期",
        "rate_note": "價格說明",
        "unmapped": "未對應",
        "sessions": "傾咗幾多場",
        "models": "{count} 個模型",
        "daily_logo": "全日埋單",
        "daily_thanks": "多謝今日咁勤力寫 code",
        "alltime_logo": "歷史總埋單",
        "alltime_thanks": "多謝你呢台電腦每行 code",
    },
}


@dataclass(frozen=True)
class ReceiptRow:
    label: str
    value: str
    separator: str = ""  # "" = normal row, "blank" = empty line, "light" = light rule


@dataclass(frozen=True)
class ReceiptView:
    language: str
    width: int
    logo_lines: Tuple[str, ...]
    logo_label: str
    thanks_line: str
    receipt_id_line: str
    date_line: str
    summary_rows: Tuple[ReceiptRow, ...]
    item_header: ReceiptRow
    token_rows: Tuple[ReceiptRow, ...]
    total_row: ReceiptRow
    pricing_rows: Tuple[ReceiptRow, ...]
    footer_lines: Tuple[str, ...]
    barcode_line: str
    barcode_id_line: str


class Receipt:
    def __init__(self, width: int, language: str = DEFAULT_LANGUAGE) -> None:
        if width not in ALLOWED_WIDTHS:
            raise SystemExit(f"--width must be one of {ALLOWED_WIDTHS}")
        self.width = width
        self.language = canonical_language(language)
        self.lines: List[str] = []

    def add(self, text: str = "") -> None:
        self.lines.append(truncate_visual(text, self.width, self.language))

    def center(self, text: str = "") -> None:
        self.add(center_text_visual(text, self.width, self.language))

    def rule(self, char: str = "-") -> None:
        self.add(char * self.width)

    def strong_rule(self) -> None:
        self.rule("━")

    def light_rule(self) -> None:
        self.rule("─")

    def kv(self, left: str, right: str) -> None:
        right = str(right)
        right_width = visual_display_width(right, self.language)
        max_left = max(1, int(self.width - right_width - 1))
        left = truncate_visual(left, max_left, self.language)
        left_width = visual_display_width(left, self.language)
        spaces = max(1, int(math.floor(self.width - left_width - right_width)))
        self.add(left + " " * spaces + right)

    def blank(self) -> None:
        self.add("")

    def text(self) -> str:
        for line in self.lines:
            if visual_display_width(line, self.language) > self.width + 0.51:
                raise AssertionError(f"line exceeds width: {line!r}")
            for char in line:
                if not printable_receipt_char(char):
                    raise AssertionError(f"unsupported control character: {line!r}")
        return "\n".join(self.lines)


def labels_for(language: str) -> dict[str, str]:
    return LABELS[canonical_language(language)]


def receipt_id(snapshot: UsageSnapshot, provider: str) -> str:
    stamp = parse_iso(snapshot.timestamp)
    if stamp:
        date_part = stamp.strftime("%Y%m%d_%H%M%S")
    else:
        date_part = time.strftime("%Y%m%d_%H%M%S")
    seed = f"{snapshot.session_id}:{snapshot.provider}:{snapshot.model}:{snapshot.total_tokens}:{snapshot.source}:{date_part}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:6].upper()
    nk = normalize(provider)
    prefix = (
        "CC"
        if nk == "anthropic"
        else "CX"
        if nk == "openai"
        else "AI"
    )
    return f"{prefix}_{date_part}_{digest}"


def barcode(seed: str, width: int) -> str:
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    patterns = ["|", "||", "| ", " ||", "|||", " |"]
    raw = "".join(patterns[int(char, 16) % len(patterns)] for char in digest)
    target = min(width - 8, max(24, width - 16))
    return center_text_visual(raw[:target], width, "en")


def auto_brand(provider: str, source: str, explicit: str) -> str:
    if explicit != "auto":
        return explicit
    provider_key = normalize(provider)
    source_key = normalize(source)
    src_slash = source.replace("\\", "/").lower()
    if "#ses_" in source or source.startswith("opencode://"):
        return "opencode"
    if provider_key == "trae" or "trae" in source_key:
        return "trae"
    if provider_key == "openai" or "codex" in source_key:
        return "codex"
    if provider_key == "anthropic" or "claude" in source_key:
        return "claude-code"
    return "generic"


def add_centered_block(receipt: Receipt, lines: List[str], offset: int = 0) -> None:
    nonempty = [line for line in lines if line.strip()]
    shared_indent = min((len(line) - len(line.lstrip(" ")) for line in nonempty), default=0)
    normalized = [line[shared_indent:] for line in lines]
    block_width = max(visual_display_width(line.rstrip(), receipt.language) for line in normalized)
    left_pad = max(int(round((receipt.width - block_width) / 2)) + offset, 0)
    for line in normalized:
        receipt.add(" " * left_pad + line.rstrip())


def logo_block(agent_tool: str, language: str) -> tuple[Tuple[str, ...], str, int]:
    if agent_tool == "codex":
        return (
            (
                "      █████",
                "    █    ██   ███",
                "  ███ ██    ██   █",
                "██ ██ ██████   ███",
                "█  ██ ██    ███   █",
                "██   ███    █  ██  █",
                "  ███   █████  ██ ██",
                "  █   ██    █  ███",
                "   ███   ██    █",
                "         █████",
            ),
            "CODEX",
            0,
        )
    if agent_tool == "trae":
        return (
            (
                "   ██████████████",
                "███▒▒▒▒▒▒▒▒▒▒▒▒▒▒███",
                "███▒▒██████████▒▒███",
                "███▒▒██▒▒▒█▒▒▒█▒▒███",
                "███▒▒██████████▒▒███",
                "█████▒▒▒▒▒▒▒▒▒▒▒▒███",
                "   █████████████",
            ),
            "TRAE",
            0,
        )
    if agent_tool == "claude-code":
        return (
            (
                " ▐▛███▜▌",
                "▝▜█████▛▘",
                "  ▘▘ ▝▝",
            ),
            "CLAUDE CODE",
            -1,
        )
    if agent_tool == "opencode":
        return (
            (
                "       ███████████████",
                "       █       █    ██",
                "       █ ████ ██ ████",
                "       █       █    ██",
                "       ███████████████",
            ),
            "OPENCODE",
            0,
        )
    # Hosts without their own pixel logo still get a branded label band.
    label_only = {
        "cursor": "CURSOR",
        "manus": "MANUS",
        "antigravity": "ANTIGRAVITY",
    }
    if agent_tool in label_only:
        return ((), f"[ {label_only[agent_tool]} ]", 0)
    return ((), labels_for(language)["generic_logo"], 0)


def add_logo(receipt: Receipt, agent_tool: str, language: str) -> None:
    lines, label, offset = logo_block(agent_tool, language)
    if lines:
        add_centered_block(receipt, list(lines), offset=offset)
        receipt.center(label)
        return
    receipt.center(label)


def product_name(snapshot: UsageSnapshot) -> str:
    model_key = normalize(snapshot.model)
    provider_key = normalize(snapshot.provider)
    if "claude" in model_key:
        return "Claude"
    if "codex" in model_key:
        return "Codex"
    if "gpt" in model_key:
        return "ChatGPT"
    if "gemini" in model_key or provider_key == "google":
        return "Gemini"
    if "deepseek" in model_key or provider_key == "deepseek":
        return "DeepSeek"
    if "glm" in model_key or provider_key in ("zhipu", "bigmodel"):
        return "GLM"
    if "mimo" in model_key or provider_key == "xiaomi":
        return "MiMo"
    if "qwen" in model_key or provider_key in ("qwen", "dashscope", "alibaba"):
        return "Qwen"
    if "minimax" in model_key or provider_key == "minimax":
        return "MiniMax"
    if "trae" in model_key:
        return "Trae"
    if snapshot.model and snapshot.model != "UNRECORDED":
        return truncate_visual(snapshot.model, 16, "en")
    if provider_key == "anthropic":
        return "Claude"
    if provider_key == "openai":
        return "ChatGPT"
    return "AI"


def context_used(snapshot: UsageSnapshot) -> str:
    if snapshot.context_tokens is not None:
        used_src = snapshot.context_tokens
    else:
        used_src = snapshot.input_tokens
    used = fmt_int(used_src)
    if snapshot.context_window:
        return f"{used}/{fmt_int(snapshot.context_window)}"
    return used


def tip_tier(percent: float | int | None) -> str:
    value = float(percent or 0.0)
    if value >= 25:
        return "tip_25"
    if value >= 20:
        return "tip_20"
    return "tip_15"


def localized_tip_footer_line(language: str, tip_percent: float | int, digest: int) -> str:
    tip_copy = load_footer_copy().get("tip")
    if not isinstance(tip_copy, dict):
        raise KeyError("Missing tip footer copy")
    tier = tip_tier(tip_percent)
    rows = [
        row
        for row in tip_copy.get(tier, [])
        if isinstance(row, dict) and isinstance(row.get(language), str)
    ]
    if not rows:
        raise KeyError(f"Missing tip footer copy for {tier!r}/{language!r}")
    return str(rows[(digest >> 6) % len(rows)][language])


def auto_tip_footer(
    snapshot: UsageSnapshot,
    estimate: PriceEstimate,
    tone: str,
    width: int,
    language: str,
    hint: str = "",
    tip_percent: float | int = 0,
) -> str:
    return fit_footer_text(
        auto_tip_footer_line(snapshot, estimate, tone, language, hint, tip_percent),
        width,
        language,
    )


def auto_tip_footer_line(
    snapshot: UsageSnapshot,
    estimate: PriceEstimate,
    tone: str,
    language: str,
    hint: str = "",
    tip_percent: float | int = 0,
) -> str:
    language = canonical_language(language)
    if float(tip_percent or 0.0) <= 0:
        return auto_footer_line(snapshot, estimate, tone, language, hint)

    key = (
        f"tip:{snapshot.provider}:{snapshot.model}:{snapshot.total_tokens}:"
        f"{snapshot.cached_input_tokens}:{snapshot.reasoning_output_tokens}:{hint}:{tone}:"
        f"{estimate.status}:{estimate.amount}:{tip_percent}"
    )
    digest = int(hashlib.sha1(key.encode("utf-8")).hexdigest()[:8], 16)
    return localized_tip_footer_line(language, tip_percent, digest)


@lru_cache(maxsize=1)
def load_footer_copy() -> dict[str, object]:
    with FOOTER_COPY_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("footer"), (dict, list)):
        raise ValueError(f"Invalid footer copy data in {FOOTER_COPY_PATH}")
    return data


def localized_footer_line(language: str, digest: int) -> str:
    footer = load_footer_copy()["footer"]
    if not isinstance(footer, list):
        raise KeyError("Footer copy is not row-based")
    rows = [row for row in footer if isinstance(row, dict) and isinstance(row.get(language), str)]
    if not rows:
        raise KeyError(f"Missing footer copy for language {language!r}")
    return str(rows[(digest >> 14) % len(rows)][language])


def split_display_text(text: str, max_width: int, language: str) -> tuple[str, str]:
    left: list[str] = []
    width = 0.0
    index = 0
    for index, char in enumerate(text):
        char_width = visual_char_width(char, language)
        if width + char_width > max_width:
            break
        left.append(char)
        width += char_width
    else:
        return text, ""
    return "".join(left).rstrip(), text[index:].lstrip()


def fit_footer_text(text: str, width: int, language: str) -> str:
    language = canonical_language(language)
    max_line = min(width, 40)
    normalized = re.sub(r"\s+", " ", text.strip())
    if visual_display_width(normalized, language) <= max_line:
        return normalized

    words = normalized.split()
    if len(words) > 1:
        for split_at in range(len(words) - 1, 0, -1):
            left = " ".join(words[:split_at])
            right = " ".join(words[split_at:])
            if visual_display_width(left, language) <= max_line and visual_display_width(right, language) <= max_line:
                return left + "\n" + right

    left, right = split_display_text(normalized, max_line, language)
    if not right:
        return left
    return left + "\n" + truncate_visual(right, max_line, language)


def auto_footer_line(snapshot: UsageSnapshot, estimate: PriceEstimate, tone: str, language: str, hint: str = "") -> str:
    language = canonical_language(language)
    key = f"{snapshot.provider}:{snapshot.model}:{snapshot.total_tokens}:{snapshot.cached_input_tokens}:{snapshot.reasoning_output_tokens}:{hint}:{tone}:{estimate.status}"
    digest = int(hashlib.sha1(key.encode("utf-8")).hexdigest()[:8], 16)
    return localized_footer_line(language, digest)


def auto_footer(snapshot: UsageSnapshot, estimate: PriceEstimate, tone: str, width: int, language: str, hint: str = "") -> str:
    return fit_footer_text(auto_footer_line(snapshot, estimate, tone, language, hint), width, language)


def footer_lines(text: str, width: int, language: str) -> List[str]:
    language = canonical_language(language)
    normalized = text.replace("\\n", "\n")
    lines: List[str] = []
    for raw in normalized.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        if language == "en":
            raw = raw.upper()
        lines.append(truncate_visual(raw, width, language))
    return lines or [""]


def source_has(snapshot: UsageSnapshot, field: str) -> bool:
    return field in snapshot.available_fields


def currency_symbol(currency: str) -> str:
    key = currency.upper()
    if key == "USD":
        return "$"
    if key in ("CNY", "RMB"):
        return "¥"
    if key == "TWD":
        return "NT$"
    return f"{key} "


def money(amount: float | None, currency: str = "USD") -> str:
    if amount is None:
        return "UNMAPPED"
    if currency.upper() == "TWD":
        return f"{currency_symbol(currency)}{amount:.2f}"
    if 0 < amount < 0.000001:
        return f"<{currency_symbol(currency)}0.000001"
    return f"{currency_symbol(currency)}{amount:.6f}"


def build_receipt_view(
    snapshot: UsageSnapshot,
    estimate: PriceEstimate,
    width: int,
    agent_tool: str,
    footer: str,
    footer_tone: str,
    conversation_hint: str,
    language: str = DEFAULT_LANGUAGE,
) -> ReceiptView:
    language = canonical_language(language)
    labels = labels_for(language)
    provider = snapshot.provider.upper() if snapshot.provider else "UNKNOWN"
    rid = receipt_id(snapshot, snapshot.provider)
    footer_text = auto_footer(snapshot, estimate, footer_tone, width, language, conversation_hint) if footer == "auto" else footer

    breakdown = snapshot.model_breakdown
    if breakdown:
        providers = []
        for usage in breakdown:
            name = (usage.provider or "unknown").upper()
            if name not in providers:
                providers.append(name)
        model_value = breakdown[0].model if len(breakdown) == 1 else labels["models"].format(count=len(breakdown))
        summary_rows = (
            ReceiptRow(labels["provider"], "/".join(providers[:3])),
            ReceiptRow(labels["model"], model_value),
            ReceiptRow(labels["sessions"], fmt_int(snapshot.session_count)),
        )
        token_rows = [ReceiptRow(usage.model, fmt_int(usage.total_tokens)) for usage in breakdown]
    else:
        summary_rows = (
            ReceiptRow(labels["provider"], provider),
            ReceiptRow(labels["model"], snapshot.model),
            ReceiptRow(labels["context"], context_used(snapshot)),
        )
        token_rows = []
        if source_has(snapshot, "input_tokens"):
            token_rows.append(ReceiptRow(labels["input"], fmt_int(snapshot.input_tokens)))
        if source_has(snapshot, "output_tokens"):
            token_rows.append(ReceiptRow(labels["output"], fmt_int(snapshot.output_tokens)))
        if source_has(snapshot, "cached_input_tokens"):
            token_rows.append(ReceiptRow(labels["cached"], fmt_int(snapshot.cached_input_tokens)))
        if source_has(snapshot, "reasoning_output_tokens"):
            token_rows.append(ReceiptRow(labels["reasoning"], fmt_int(snapshot.reasoning_output_tokens)))
        if source_has(snapshot, "cache_write_tokens"):
            token_rows.append(ReceiptRow(labels["cache_write"], fmt_int(snapshot.cache_write_tokens)))

    pricing_rows = []
    if len(breakdown) > 1 and estimate.breakdown:
        # One price line per model (+ TWD inline), blank between models, light rule before totals.
        for i, cost in enumerate(estimate.breakdown):
            if i > 0:
                pricing_rows.append(ReceiptRow("", "", separator="blank"))
            value = money(cost.amount, cost.currency) if cost.amount is not None else labels["unmapped"]
            pricing_rows.append(ReceiptRow(cost.model, value))
            if cost.amount is not None and cost.currency == "USD" and estimate.twd_rate:
                twd_val = round(cost.amount * estimate.twd_rate, 2)
                pricing_rows.append(ReceiptRow(f"  ({labels['estimate'].format(currency='TWD')})", money(twd_val, "TWD")))
        currency_totals: dict[str, float] = {}
        for cost in estimate.breakdown:
            if cost.amount is not None:
                currency_totals[cost.currency] = currency_totals.get(cost.currency, 0.0) + cost.amount
        if currency_totals:
            pricing_rows.append(ReceiptRow("", "", separator="light"))
            for cur, amount in currency_totals.items():
                pricing_rows.append(ReceiptRow(labels["estimate"].format(currency=cur), money(amount, cur)))
            if estimate.twd_amount is not None:
                pricing_rows.append(ReceiptRow(labels["estimate"].format(currency="TWD"), money(estimate.twd_amount, "TWD")))
        else:
            pricing_rows.append(
                ReceiptRow(labels["estimate"].format(currency=estimate.currency), money(None))
            )
    else:
        pricing_rows.append(
            ReceiptRow(labels["estimate"].format(currency=estimate.currency), money(estimate.amount, estimate.currency))
        )
        if estimate.twd_amount is not None:
            pricing_rows.append(
                ReceiptRow(labels["estimate"].format(currency="TWD"), money(estimate.twd_amount, "TWD"))
            )
        pricing_rows.append(
            ReceiptRow(labels["price"], labels["unmapped"] if estimate.status == "UNMAPPED" else estimate.model)
        )
        if estimate.status != "UNMAPPED":
            if estimate.source_checked_at:
                pricing_rows.append(ReceiptRow(labels["price_date"], estimate.source_checked_at))
            if estimate.rate_note:
                pricing_rows.append(ReceiptRow(labels["rate_note"], estimate.rate_note))

    if snapshot.scope == "today":
        # A whole-day bill spans sessions (and possibly models), so the host
        # logo would be misleading — use a daily masthead instead.
        logo_lines: Tuple[str, ...] = ()
        logo_label = labels["daily_logo"]
        thanks_line = labels["daily_thanks"]
    elif snapshot.scope == "all-time":
        logo_lines = ()
        logo_label = labels["alltime_logo"]
        thanks_line = labels["alltime_thanks"]
    else:
        logo_lines, logo_label, _ = logo_block(agent_tool, language)
        thanks_line = labels["thanks"].format(product=product_name(snapshot))
    return ReceiptView(
        language=language,
        width=width,
        logo_lines=logo_lines,
        logo_label=logo_label,
        thanks_line=thanks_line,
        receipt_id_line=labels["receipt_id"].format(rid=rid),
        date_line=labels["date"].format(date=display_time(snapshot.timestamp)),
        summary_rows=summary_rows,
        item_header=ReceiptRow(labels["item"], labels["tokens"]),
        token_rows=tuple(token_rows),
        total_row=ReceiptRow(labels["total"], f"{fmt_int(snapshot.total_tokens)} {labels['token_unit']}"),
        pricing_rows=tuple(pricing_rows),
        footer_lines=tuple(footer_lines(footer_text, width, language)),
        barcode_line=barcode(rid, width),
        barcode_id_line=rid,
    )


def render_receipt(
    snapshot: UsageSnapshot,
    estimate: PriceEstimate,
    width: int,
    agent_tool: str,
    footer: str,
    footer_tone: str,
    conversation_hint: str,
    language: str = DEFAULT_LANGUAGE,
) -> str:
    view = build_receipt_view(snapshot, estimate, width, agent_tool, footer, footer_tone, conversation_hint, language)
    receipt = Receipt(width, view.language)

    add_logo(receipt, agent_tool, view.language)
    receipt.blank()
    receipt.center(view.thanks_line)
    receipt.center(view.receipt_id_line)
    receipt.center(view.date_line)
    receipt.strong_rule()
    for row in view.summary_rows:
        receipt.kv(row.label, row.value)
    receipt.light_rule()
    receipt.kv(view.item_header.label, view.item_header.value)
    receipt.light_rule()
    for row in view.token_rows:
        receipt.kv(row.label, row.value)
    receipt.strong_rule()
    receipt.kv(view.total_row.label, view.total_row.value)
    receipt.light_rule()
    for row in view.pricing_rows:
        if row.separator == "blank":
            receipt.blank()
        elif row.separator == "light":
            receipt.light_rule()
        else:
            receipt.kv(row.label, row.value)
    receipt.strong_rule()
    for line in view.footer_lines:
        receipt.center(line)
    receipt.blank()
    receipt.add(view.barcode_line)
    receipt.center(view.barcode_id_line)
    return receipt.text()


def print_receipt(text: str, stream: bool, delay: float) -> None:
    width = max((len(line) for line in text.splitlines()), default=48)
    border = "─" * width
    if not stream:
        print(f"\n{border}")
        print(text)
        print(f"{border}\n")
        return
    print(f"\n{border}")
    for line in text.splitlines():
        print(line, flush=True)
        if delay > 0:
            time.sleep(delay)
    print(f"{border}\n")
