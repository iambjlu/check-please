"""Printable HTML rendering for token receipt."""

from __future__ import annotations

from base64 import b64encode
from functools import lru_cache
from html import escape
import json
from pathlib import Path

from .models import DEFAULT_LANGUAGE, PriceEstimate, SKILL_DIR, UsageSnapshot, canonical_language
from .render import ReceiptRow, auto_footer_line, auto_tip_footer_line, build_receipt_view, money


def _render_rows(rows: tuple[ReceiptRow, ...]) -> str:
    return "\n".join(
        f'        <div class="receipt-row"><span class="receipt-label">{escape(row.label)}</span><span class="receipt-value">{escape(row.value)}</span></div>'
        for row in rows
    )


HTML_LOGO_ASSETS = {
    "codex": SKILL_DIR / "check_please" / "assets" / "codex-logo.png",
    "trae": SKILL_DIR / "check_please" / "assets" / "trae-logo.png",
}

HTML_LANGUAGES = ("en", "zh-TW", "cantonese")
TIP_PRESETS = (15, 18, 20, 25)
TIP_UI_LABELS = {
    "en": {
        "toggle": "Add tip",
        "subtotal": "SUBTOTAL",
        "tip": "TIP",
        "grand_total": "GRAND TOTAL",
        "language_button": "EN",
    },
    "zh-TW": {
        "toggle": "加一點小費",
        "subtotal": "小計",
        "tip": "小費",
        "grand_total": "應付總額",
        "language_button": "繁中",
    },
    "cantonese": {
        "toggle": "加少少貼士",
        "subtotal": "小計",
        "tip": "貼士",
        "grand_total": "埋單總數",
        "language_button": "廣東話",
    },
}


CLAUDE_CODE_SVG = """
<svg class="receipt-logo-svg receipt-logo-svg--claude-code" viewBox="0 0 128 76" aria-hidden="true" focusable="false">
  <g fill="currentColor" shape-rendering="crispEdges">
    <rect x="22" y="4" width="84" height="22" />
    <rect x="10" y="30" width="108" height="14" />
    <rect x="24" y="44" width="80" height="14" />
    <rect x="30" y="60" width="8" height="12" />
    <rect x="48" y="60" width="8" height="12" />
    <rect x="78" y="60" width="8" height="12" />
    <rect x="96" y="60" width="8" height="12" />
  </g>
  <g fill="#ffffff" shape-rendering="crispEdges">
    <rect x="38" y="12" width="10" height="14" />
    <rect x="80" y="12" width="10" height="14" />
  </g>
</svg>
""".strip()


def _normalize_footer_for_html(text: str, language: str) -> str:
    parts = [part.strip() for part in text.replace("\\n", "\n").splitlines() if part.strip()]
    if not parts:
        return ""
    if canonical_language(language) in {"zh-TW", "cantonese"}:
        return "".join(parts)
    return " ".join(parts).upper()


def _json_script_payload(data: object) -> str:
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


@lru_cache(maxsize=None)
def _asset_data_uri(path: Path) -> str | None:
    if not path.exists():
        return None
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/svg+xml" if suffix == ".svg" else None
    if mime is None:
        return None
    return f"data:{mime};base64,{b64encode(path.read_bytes()).decode('ascii')}"


def _logo_markup(agent_tool: str, logo_lines: tuple[str, ...]) -> str:
    if agent_tool == "claude-code":
        return f'          <div class="receipt-logo-shell">{CLAUDE_CODE_SVG}</div>\n'
    asset = HTML_LOGO_ASSETS.get(agent_tool)
    if asset:
        data_uri = _asset_data_uri(asset)
        if data_uri:
            return (
                '          <div class="receipt-logo-shell">'
                f'<img class="receipt-logo-image receipt-logo-image--{escape(agent_tool)}" src="{data_uri}" alt="" aria-hidden="true" />'
                "</div>\n"
            )
    if not logo_lines:
        return ""
    return (
        '          <div class="receipt-logo-shell">\n'
        '            <pre class="receipt-logo" aria-hidden="true">'
        + escape("\n".join(logo_lines))
        + "</pre>\n"
        "          </div>\n"
    )


def _tip_config(
    snapshot: UsageSnapshot,
    estimate: PriceEstimate,
    footer_tone: str,
    width: int,
    language: str,
    conversation_hint: str,
    default_footer_text: str,
) -> dict[str, object] | None:
    if estimate.status != "ESTIMATE" or estimate.amount is None:
        return None
    labels = TIP_UI_LABELS[canonical_language(language)]
    options: list[dict[str, object]] = []
    for percent in TIP_PRESETS:
        tip_amount = estimate.amount * (percent / 100.0)
        grand_total = estimate.amount + tip_amount
        options.append(
            {
                "percent": percent,
                "tipAmount": money(tip_amount, estimate.currency),
                "grandTotal": money(grand_total, estimate.currency),
                "footer": _normalize_footer_for_html(
                    auto_tip_footer_line(
                        snapshot,
                        estimate,
                        footer_tone,
                        language,
                        conversation_hint,
                        tip_percent=percent,
                    )
                , language),
            }
        )
    return {
        "language": canonical_language(language),
        "defaultFooter": default_footer_text,
        "subtotal": money(estimate.amount, estimate.currency),
        "subtotalLabel": labels["subtotal"],
        "tipLabel": labels["tip"],
        "grandTotalLabel": labels["grand_total"],
        "options": options,
    }


def _tip_summary_markup(labels: dict[str, str], subtotal: str) -> str:
    return (
        '        <section class="receipt-tip-summary" hidden>\n'
        '          <div class="receipt-rule"></div>\n'
        '          <div class="receipt-row">'
        f'<span class="receipt-label">{escape(labels["subtotal"])}</span>'
        f'<span class="receipt-value" data-tip-subtotal>{escape(subtotal)}</span>'
        "</div>\n"
        '          <div class="receipt-row">'
        f'<span class="receipt-label" data-tip-line-label>{escape(labels["tip"])} (0%)</span>'
        '<span class="receipt-value" data-tip-amount></span>'
        "</div>\n"
        '          <div class="receipt-row receipt-total">'
        f'<span class="receipt-label">{escape(labels["grand_total"])}</span>'
        '<span class="receipt-value" data-tip-grand-total></span>'
        "</div>\n"
        "        </section>\n"
    )


def _render_receipt_article(
    view,
    agent_tool: str,
    footer_text: str,
    tip_summary_markup: str,
    active: bool,
) -> str:
    logo_art = _logo_markup(agent_tool, view.logo_lines)
    hidden_class = "" if active else " receipt--hidden"
    return (
        # The shell carries the drop-shadow: filter must live on a parent, because
        # filter is applied before mask on the same element — the torn-edge mask
        # would erase a shadow declared on .receipt itself.
        '      <div class="receipt-shell">\n'
        f'      <article class="receipt{hidden_class}" data-language="{escape(view.language)}">\n'
        '        <header class="receipt-header">\n'
        f"{logo_art}"
        f'          <div class="receipt-logo-label">{escape(view.logo_label)}</div>\n'
        f'          <div class="receipt-thanks">{escape(view.thanks_line)}</div>\n'
        f'          <div class="receipt-meta">{escape(view.receipt_id_line)}</div>\n'
        f'          <div class="receipt-meta">{escape(view.date_line)}</div>\n'
        "        </header>\n"
        '        <div class="receipt-rule strong"></div>\n'
        f"{_render_rows(view.summary_rows)}\n"
        '        <div class="receipt-rule"></div>\n'
        f"{_render_rows((view.item_header,))}\n"
        '        <div class="receipt-rule"></div>\n'
        f"{_render_rows(view.token_rows)}\n"
        '        <div class="receipt-rule strong"></div>\n'
        '        <div class="receipt-total">\n'
        f"{_render_rows((view.total_row,))}\n"
        "        </div>\n"
        '        <div class="receipt-rule"></div>\n'
        f"{_render_rows(view.pricing_rows)}\n"
        f"{tip_summary_markup}"
        '        <footer class="receipt-footer">\n'
        '          <div class="receipt-rule strong"></div>\n'
        f'          <div class="receipt-footer-line" data-receipt-footer>{escape(footer_text)}</div>\n'
        f'          <pre class="receipt-barcode" aria-hidden="true">{escape(view.barcode_line.strip())}</pre>\n'
        f'          <div class="receipt-barcode-id">{escape(view.barcode_id_line)}</div>\n'
        "        </footer>\n"
        "      </article>\n"
        "      </div>\n"
    )


def render_receipt_html(
    snapshot: UsageSnapshot,
    estimate: PriceEstimate,
    width: int,
    agent_tool: str,
    footer: str,
    footer_tone: str,
    conversation_hint: str,
    language: str = DEFAULT_LANGUAGE,
) -> str:
    page_lang = canonical_language(language)
    views = {
        lang: build_receipt_view(snapshot, estimate, width, agent_tool, footer, footer_tone, conversation_hint, lang)
        for lang in HTML_LANGUAGES
    }
    active_view = views[page_lang]
    title = escape(active_view.barcode_id_line)
    tip_labels = TIP_UI_LABELS[page_lang]
    footer_texts = {}
    for lang in HTML_LANGUAGES:
        raw_footer = (
            auto_footer_line(snapshot, estimate, footer_tone, lang, conversation_hint)
            if footer == "auto"
            else footer
        )
        footer_texts[lang] = _normalize_footer_for_html(raw_footer, lang)
    tip_configs = {
        lang: _tip_config(snapshot, estimate, footer_tone, width, lang, conversation_hint, footer_texts[lang])
        for lang in HTML_LANGUAGES
    }
    config_payload = {
        "defaultLanguage": page_lang,
        "uiLabels": TIP_UI_LABELS,
        "tip": tip_configs,
    }
    language_buttons = "\n".join(
        f'        <button class="language-option{" is-selected" if lang == page_lang else ""}" type="button" data-language-button="{lang}" aria-pressed="{"true" if lang == page_lang else "false"}">{escape(TIP_UI_LABELS[lang]["language_button"])}</button>'
        for lang in HTML_LANGUAGES
    )
    topbar = (
        '    <nav class="topbar">\n'
        '      <div class="topbar-left">\n'
        '        <button class="btn-print" type="button" onclick="window.print()">Print receipt</button>\n'
        '        <button class="btn-ghost" type="button" data-save-png>Save PNG</button>\n'
        "      </div>\n"
        f'      <div class="lang" data-active="{HTML_LANGUAGES.index(page_lang)}">\n'
        f"{language_buttons}\n"
        "      </div>\n"
        "    </nav>\n"
    )
    tip_panel = ""
    if tip_configs[page_lang] is not None:
        option_buttons = "\n".join(
            f'            <button class="tip-option" type="button" data-tip-percent="{percent}">{percent}%</button>'
            for percent in TIP_PRESETS
        )
        tip_panel = (
            '      <section class="receipt-tip-panel">\n'
            '        <section class="receipt-tip-controls">\n'
            '          <label class="tip-toggle">\n'
            '            <input id="tip-toggle" type="checkbox" />\n'
            f'            <span id="tip-toggle-label">{escape(tip_labels["toggle"])}</span>\n'
            '          </label>\n'
            '          <div class="tip-options" id="tip-options" hidden>\n'
            f"{option_buttons}\n"
            "          </div>\n"
            "        </section>\n"
            "      </section>\n"
        )
    # The script always ships: language switching must work even when there is
    # no price estimate (tip handlers no-op when their elements are absent).
    tip_script = (
            f'    <script id="tip-config" type="application/json">{_json_script_payload(config_payload)}</script>\n'
            "    <script>\n"
            "      (() => {\n"
            "        const node = document.getElementById('tip-config');\n"
            "        if (!node) return;\n"
            "        const config = JSON.parse(node.textContent || '{}');\n"
            "        let activeLanguage = config.defaultLanguage || document.documentElement.lang || 'en';\n"
            "        const toggle = document.getElementById('tip-toggle');\n"
            "        const optionsWrap = document.getElementById('tip-options');\n"
            "        const buttons = Array.from(document.querySelectorAll('[data-tip-percent]'));\n"
            "        const languageButtons = Array.from(document.querySelectorAll('[data-language-button]'));\n"
            "        const receipts = Array.from(document.querySelectorAll('.receipt[data-language]'));\n"
            "        const tipToggleLabel = document.getElementById('tip-toggle-label');\n"
            "        let selectedPercent = null;\n"
            "        const tipConfigFor = (lang) => (config.tip || {})[lang] || null;\n"
            "        const receiptFor = (lang) => document.querySelector(`.receipt[data-language=\"${lang}\"]`);\n"
            "        const optionMapFor = (lang) => new Map(((tipConfigFor(lang) || {}).options || []).map((item) => [String(item.percent), item]));\n"
            "        const resetReceipt = (lang) => {\n"
            "          const receipt = receiptFor(lang);\n"
            "          const tipConfig = tipConfigFor(lang);\n"
            "          if (!receipt || !tipConfig) return;\n"
            "          const summary = receipt.querySelector('.receipt-tip-summary');\n"
            "          const footer = receipt.querySelector('[data-receipt-footer]');\n"
            "          const lineLabel = receipt.querySelector('[data-tip-line-label]');\n"
            "          const tipAmount = receipt.querySelector('[data-tip-amount]');\n"
            "          const grandTotal = receipt.querySelector('[data-tip-grand-total]');\n"
            "          if (footer) footer.textContent = tipConfig.defaultFooter || '';\n"
            "          if (summary) summary.hidden = true;\n"
            "          if (tipAmount) tipAmount.textContent = '';\n"
            "          if (grandTotal) grandTotal.textContent = '';\n"
            "          if (lineLabel) lineLabel.textContent = `${tipConfig.tipLabel} (0%)`;\n"
            "        };\n"
            "        const applySelectionToReceipt = (lang, percent) => {\n"
            "          const receipt = receiptFor(lang);\n"
            "          const tipConfig = tipConfigFor(lang);\n"
            "          if (!receipt || !tipConfig) return;\n"
            "          const optionMap = optionMapFor(lang);\n"
            "          const option = optionMap.get(String(percent));\n"
            "          if (!option) return;\n"
            "          const summary = receipt.querySelector('.receipt-tip-summary');\n"
            "          const footer = receipt.querySelector('[data-receipt-footer]');\n"
            "          const lineLabel = receipt.querySelector('[data-tip-line-label]');\n"
            "          const tipAmount = receipt.querySelector('[data-tip-amount]');\n"
            "          const grandTotal = receipt.querySelector('[data-tip-grand-total]');\n"
            "          if (summary) summary.hidden = false;\n"
            "          if (lineLabel) lineLabel.textContent = `${tipConfig.tipLabel} (${option.percent}%)`;\n"
            "          if (tipAmount) tipAmount.textContent = option.tipAmount;\n"
            "          if (grandTotal) grandTotal.textContent = option.grandTotal;\n"
            "          if (footer) footer.textContent = option.footer;\n"
            "        };\n"
            "        const syncVisibleState = () => {\n"
            "          receipts.forEach((receipt) => {\n"
            "            const lang = receipt.dataset.language;\n"
            "            if (!lang) return;\n"
            "            if (toggle && toggle.checked && selectedPercent) {\n"
            "              applySelectionToReceipt(lang, selectedPercent);\n"
            "            } else {\n"
            "              resetReceipt(lang);\n"
            "            }\n"
            "          });\n"
            "        };\n"
            "        const applyLanguage = (lang) => {\n"
            "          activeLanguage = lang;\n"
            "          document.documentElement.lang = lang;\n"
            "          receipts.forEach((receipt) => {\n"
            "            const active = receipt.dataset.language === lang;\n"
            "            receipt.classList.toggle('receipt--hidden', !active);\n"
            "          });\n"
            "          languageButtons.forEach((button) => {\n"
            "            const active = button.dataset.languageButton === lang;\n"
            "            button.classList.toggle('is-selected', active);\n"
            "            button.setAttribute('aria-pressed', active ? 'true' : 'false');\n"
            "          });\n"
            "          const langWrap = document.querySelector('.lang');\n"
            "          const langIndex = languageButtons.findIndex((button) => button.dataset.languageButton === lang);\n"
            "          if (langWrap && langIndex >= 0) langWrap.dataset.active = String(langIndex);\n"
            "          if (tipToggleLabel && config.uiLabels && config.uiLabels[lang]) {\n"
            "            tipToggleLabel.textContent = config.uiLabels[lang].toggle;\n"
            "          }\n"
            "        };\n"
            "        buttons.forEach((button) => {\n"
            "          button.setAttribute('aria-pressed', 'false');\n"
            "          button.addEventListener('click', () => {\n"
            "            selectedPercent = button.dataset.tipPercent;\n"
            "            buttons.forEach((candidate) => {\n"
            "              const active = candidate.dataset.tipPercent === selectedPercent;\n"
            "              candidate.classList.toggle('is-selected', active);\n"
            "              candidate.setAttribute('aria-pressed', active ? 'true' : 'false');\n"
            "            });\n"
            "            syncVisibleState();\n"
            "          });\n"
            "        });\n"
            "        languageButtons.forEach((button) => {\n"
            "          button.addEventListener('click', () => applyLanguage(button.dataset.languageButton));\n"
            "        });\n"
            "        if (toggle) {\n"
            "          toggle.addEventListener('change', () => {\n"
            "            const enabled = !!toggle.checked;\n"
            "            if (optionsWrap) optionsWrap.hidden = !enabled;\n"
            "            if (!enabled) {\n"
            "              selectedPercent = null;\n"
            "              buttons.forEach((candidate) => {\n"
            "                candidate.classList.remove('is-selected');\n"
            "                candidate.setAttribute('aria-pressed', 'false');\n"
            "              });\n"
            "            }\n"
            "            syncVisibleState();\n"
            "          });\n"
            "        }\n"
            "        const pngButton = document.querySelector('[data-save-png]');\n"
            "        const saveReceiptPng = () => {\n"
            "          const receipt = document.querySelector('.receipt:not(.receipt--hidden)');\n"
            "          if (!receipt) return;\n"
            "          const pad = 48;\n"
            "          const width = receipt.offsetWidth + pad * 2;\n"
            "          const height = receipt.offsetHeight + pad * 2;\n"
            "          const xhtmlNS = 'http://www.w3.org/1999/xhtml';\n"
            "          const svgNS = 'http://www.w3.org/2000/svg';\n"
            "          const clone = receipt.cloneNode(true);\n"
            "          clone.style.width = receipt.offsetWidth + 'px';\n"
            "          const css = Array.from(document.querySelectorAll('style')).map((node) => node.textContent).join('\\n');\n"
            "          const stage = document.createElementNS(xhtmlNS, 'div');\n"
            "          stage.setAttribute('class', 'png-stage');\n"
            "          const shell = document.createElementNS(xhtmlNS, 'div');\n"
            "          shell.setAttribute('class', 'receipt-shell');\n"
            "          const stageStyle = document.createElementNS(xhtmlNS, 'style');\n"
            "          stageStyle.textContent = css + '\\n.png-stage{margin:0;padding:' + pad + 'px;background:#faf9f6;}' +\n"
            "            '\\n.png-stage .receipt{animation:none !important;transform:none !important;margin:0;}' +\n"
            "            '\\n.png-stage .receipt-shell{animation:none !important;transform:none !important;}';\n"
            "          stage.appendChild(stageStyle);\n"
            "          shell.appendChild(clone);\n"
            "          stage.appendChild(shell);\n"
            "          const svg = document.createElementNS(svgNS, 'svg');\n"
            "          svg.setAttribute('width', String(width));\n"
            "          svg.setAttribute('height', String(height));\n"
            "          const fo = document.createElementNS(svgNS, 'foreignObject');\n"
            "          fo.setAttribute('width', '100%');\n"
            "          fo.setAttribute('height', '100%');\n"
            "          fo.appendChild(stage);\n"
            "          svg.appendChild(fo);\n"
            "          const markup = new XMLSerializer().serializeToString(svg);\n"
            "          if (pngButton) pngButton.disabled = true;\n"
            "          const output = document.querySelector('.printer-output');\n"
            "          receipt.classList.add('is-torn');\n"
            "          if (output) output.classList.add('is-tearing');\n"
            "          const reprint = () => {\n"
            "            receipt.classList.remove('is-torn');\n"
            "            if (output) output.classList.remove('is-tearing');\n"
            "            receipt.style.animation = 'none';\n"
            "            void receipt.offsetWidth;\n"
            "            receipt.style.animation = '';\n"
            "            if (pngButton) pngButton.disabled = false;\n"
            "          };\n"
            "          setTimeout(reprint, 1150);\n"
            "          const img = new Image();\n"
            "          img.onload = () => {\n"
            "            const scale = 3;\n"
            "            const canvas = document.createElement('canvas');\n"
            "            canvas.width = width * scale;\n"
            "            canvas.height = height * scale;\n"
            "            const ctx = canvas.getContext('2d');\n"
            "            ctx.scale(scale, scale);\n"
            "            ctx.drawImage(img, 0, 0);\n"
            "            const url = canvas.toDataURL('image/png');\n"
            "            window.__lastReceiptPng = url;\n"
            "            const link = document.createElement('a');\n"
            "            link.download = (document.title.split(' ')[0] || 'check-please') + '.png';\n"
            "            link.href = url;\n"
            "            link.click();\n"
            "          };\n"
            "          img.onerror = () => {\n"
            "            alert('PNG export failed in this browser; use Print receipt instead.');\n"
            "          };\n"
            "          img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(markup);\n"
            "        };\n"
            "        if (pngButton) pngButton.addEventListener('click', saveReceiptPng);\n"
            "        applyLanguage(activeLanguage);\n"
            "        syncVisibleState();\n"
            "      })();\n"
            "    </script>\n"
        )
    # Daily totals span sessions/models, so the host logo is replaced by the
    # daily masthead (the view already carries the right label).
    logo_agent = "generic" if snapshot.scope == "today" else agent_tool
    receipt_articles = "".join(
        _render_receipt_article(
            view,
            logo_agent,
            footer_texts[lang],
            _tip_summary_markup(TIP_UI_LABELS[lang], str(tip_configs[lang]["subtotal"])) if tip_configs[lang] is not None else "",
            active=(lang == page_lang),
        )
        for lang, view in views.items()
    )
    return f"""<!DOCTYPE html>
<html lang="{escape(page_lang)}">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title} · check-please</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Mona+Sans:wght@400;500;600;700&amp;family=Space+Grotesk:wght@400;500;600&amp;family=Noto+Sans+TC:wght@400;500;700&amp;display=swap" rel="stylesheet" />
    <style>
      :root {{
        color-scheme: light;
        --page-bg: #faf9f6;
        --bg-2: #f1efe8;
        --paper: #ffffff;
        --ink: #18170f;
        --ink-soft: #3a382f;
        --muted: #6f6c61;
        --line: rgba(24, 23, 15, 0.13);
        --accent: #c2f03a;
        --accent-d: #a9d91f;
        --on-accent: #18170f;
        --surface: #ffffff;
        --nav-bg: rgba(250, 249, 246, 0.88);
        --font: 'Mona Sans', 'Helvetica Neue', Helvetica, Arial, sans-serif;
        --label: 'Space Grotesk', system-ui, sans-serif;
        --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
        --ease: cubic-bezier(0.22, 1, 0.36, 1);
        --rule: #232323;
        --receipt-width: 80mm;
        --pad-x: 4mm;
        --pad-top: 7mm;
        --pad-bottom: 6.2mm;
        --logo-width: 24mm;
        --logo-shell-height: 26mm;
        --logo-label-size: 4.3mm;
        --meta-size: 3.2mm;
        --row-size: 3.45mm;
        --footer-size: 3.55mm;
        --barcode-size: 3.15mm;
        --barcode-id-size: 3.15mm;
      }}
      * {{
        box-sizing: border-box;
      }}
      html, body {{
        margin: 0;
        padding: 0;
        background: var(--page-bg);
        color: var(--ink);
        font-family: var(--font);
        -webkit-font-smoothing: antialiased;
      }}
      body {{
        min-height: 100vh;
        padding: 72px 0 24px;
      }}
      .topbar {{
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        z-index: 100;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        padding: 16px;
        background: var(--nav-bg);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border-bottom: 1px solid var(--line);
      }}
      .btn-print {{
        appearance: none;
        background: var(--accent);
        color: var(--on-accent);
        font-family: var(--font);
        font-size: 13px;
        font-weight: 600;
        border: 1.5px solid transparent;
        border-radius: 13px;
        height: 40px;
        min-width: 89px;
        padding: 0 14px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        line-height: 1;
        white-space: nowrap;
        cursor: pointer;
        transition: background 0.15s;
      }}
      @media (hover: hover) {{
        .btn-print:hover {{
          background: var(--accent-d);
        }}
      }}
      .topbar-left {{
        display: flex;
        align-items: center;
        gap: 8px;
      }}
      .btn-ghost {{
        appearance: none;
        background: none;
        color: var(--ink);
        font-family: var(--font);
        font-size: 13px;
        font-weight: 600;
        border: 1.5px solid var(--line);
        border-radius: 13px;
        height: 40px;
        padding: 0 14px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        line-height: 1;
        white-space: nowrap;
        cursor: pointer;
        transition: border-color 0.15s, color 0.15s;
      }}
      @media (hover: hover) {{
        .btn-ghost:hover {{
          border-color: var(--ink);
        }}
      }}
      .btn-ghost:disabled {{
        opacity: 0.5;
        cursor: progress;
      }}
      .lang {{
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        align-items: stretch;
        position: relative;
        height: 40px;
        padding: 3px;
        border: 1px solid var(--line);
        border-radius: 13px;
      }}
      .lang::before {{
        content: "";
        position: absolute;
        top: 3px;
        left: 3px;
        width: calc((100% - 6px) / 3);
        height: calc(100% - 6px);
        background: var(--ink);
        border-radius: 10px;
        pointer-events: none;
        transition: transform 0.2s var(--ease);
      }}
      .lang[data-active="1"]::before {{
        transform: translateX(100%);
      }}
      .lang[data-active="2"]::before {{
        transform: translateX(200%);
      }}
      .lang button {{
        appearance: none;
        border: 0;
        background: none;
        font-family: var(--font);
        font-size: 13px;
        font-weight: 500;
        letter-spacing: 0.04em;
        padding: 0 12px;
        color: var(--muted);
        border-radius: 10px;
        position: relative;
        z-index: 1;
        cursor: pointer;
        transition: color 0.2s var(--ease);
      }}
      .lang button.is-selected {{
        color: var(--page-bg);
      }}
      .receipt-page {{
        display: flex;
        flex-direction: column;
        align-items: center;
        padding: 20px 0 28px;
        background: var(--page-bg);
        gap: 10px;
      }}
      .printer {{
        position: relative;
        z-index: 2;
        width: min(calc(var(--receipt-width) + 18mm), calc(100vw - 16px));
        height: 15mm;
        border-radius: 4.5mm;
        background: linear-gradient(180deg, #34332a 0%, #201f17 45%, #15140d 100%);
        box-shadow: 0 10px 18px rgba(24, 23, 15, 0.22), inset 0 1px 0 rgba(255, 255, 255, 0.12);
        display: flex;
        align-items: center;
        justify-content: center;
      }}
      .printer::after {{
        content: "";
        position: absolute;
        left: 7mm;
        right: 7mm;
        bottom: 2mm;
        height: 1.3mm;
        border-radius: 0.8mm;
        background: #050506;
        box-shadow: inset 0 0.5mm 0.8mm rgba(0, 0, 0, 0.9);
      }}
      .printer-label {{
        color: #f4f2ea;
        font-family: var(--label);
        font-size: 12px;
        font-weight: 500;
        letter-spacing: 0.24em;
        text-transform: uppercase;
        user-select: none;
      }}
      .printer-led {{
        position: absolute;
        right: 5.5mm;
        top: 50%;
        width: 1.8mm;
        height: 1.8mm;
        border-radius: 50%;
        transform: translateY(-50%);
        background: var(--accent);
        box-shadow: 0 0 2mm rgba(194, 240, 58, 0.85);
        animation: led-pulse 1.2s ease-in-out infinite alternate;
      }}
      .printer-output {{
        position: relative;
        z-index: 3;
        margin-top: -18px;
        clip-path: inset(0 -64px -64px);
        display: flex;
        flex-direction: column;
        align-items: center;
        perspective: 1000px;
      }}
      .printer-output::before {{
        content: "";
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 6px;
        background: linear-gradient(180deg, rgba(0, 0, 0, 0.25), rgba(0, 0, 0, 0));
        z-index: 2;
        pointer-events: none;
      }}
      .receipt {{
        width: min(var(--receipt-width), calc(100vw - 24px));
        background: var(--paper);
        padding: var(--pad-top) var(--pad-x) var(--pad-bottom);
        position: relative;
        overflow: hidden;
        font-family: var(--mono);
        /* Real torn edge: the zigzag is cut out of the paper (transparent),
           and drop-shadow follows the resulting silhouette. */
        -webkit-mask:
          linear-gradient(#000 0 0) top / 100% calc(100% - 8px) no-repeat,
          conic-gradient(from -45deg at 50% 100%, #000 90deg, #0000 0) bottom / 16px 8px repeat-x;
        mask:
          linear-gradient(#000 0 0) top / 100% calc(100% - 8px) no-repeat,
          conic-gradient(from -45deg at 50% 100%, #000 90deg, #0000 0) bottom / 16px 8px repeat-x;
        animation: printer-feed 4.6s 0.2s both;
      }}
      .receipt::after {{
        content: "";
        position: absolute;
        inset: 0;
        pointer-events: none;
        /* Cylindrical shading so the flat paper reads as slightly curled. */
        background:
          linear-gradient(90deg, rgba(24, 23, 15, 0.06), rgba(255, 255, 255, 0) 15%, rgba(255, 255, 255, 0) 85%, rgba(24, 23, 15, 0.07)),
          linear-gradient(180deg, rgba(24, 23, 15, 0.05), rgba(255, 255, 255, 0) 7%);
      }}
      .receipt-shell {{
        filter: drop-shadow(0 2px 4px rgba(24, 23, 15, 0.14)) drop-shadow(0 14px 28px rgba(24, 23, 15, 0.22));
        transform-origin: 50% 0;
        /* Gentle hanging-paper sway; starts once the feed animation has finished. */
        animation: paper-sway 7s ease-in-out 5s infinite;
      }}
      @keyframes paper-sway {{
        0%, 100% {{
          transform: rotateX(0deg) rotateZ(0deg);
        }}
        30% {{
          transform: rotateX(5deg) rotateZ(0.4deg);
        }}
        65% {{
          transform: rotateX(1.5deg) rotateZ(-0.35deg);
        }}
      }}
      /* Save PNG: rip the receipt off the printer, let it drop, then reprint. */
      .printer-output.is-tearing {{
        clip-path: inset(0 -64px -2000px);
      }}
      .receipt.is-torn {{
        animation: paper-tear 1s cubic-bezier(0.45, 0.05, 0.75, 0.4) both;
      }}
      @keyframes paper-tear {{
        0% {{
          transform: translateY(0) rotateZ(0deg);
        }}
        14% {{
          transform: translateY(9px) rotateZ(-2.6deg);
        }}
        28% {{
          transform: translateY(4px) rotateZ(2deg);
        }}
        100% {{
          transform: translateY(115vh) rotateZ(-9deg);
        }}
      }}
      @keyframes printer-feed {{
        0% {{
          transform: translateY(-101%);
          animation-timing-function: cubic-bezier(0.4, 0.1, 0.6, 0.9);
        }}
        70% {{
          transform: translateY(0);
          animation-timing-function: ease-in-out;
        }}
        81% {{
          transform: translateY(-2.2%);
          animation-timing-function: ease-in-out;
        }}
        90% {{
          transform: translateY(0);
          animation-timing-function: ease-in-out;
        }}
        96% {{
          transform: translateY(-0.6%);
          animation-timing-function: ease-in-out;
        }}
        100% {{
          transform: translateY(0);
        }}
      }}
      @keyframes led-pulse {{
        from {{ opacity: 1; }}
        to {{ opacity: 0.35; }}
      }}
      @media (prefers-reduced-motion: reduce) {{
        .receipt,
        .receipt-shell,
        .printer-led {{
          animation: none;
        }}
      }}
      .receipt--hidden {{
        display: none;
      }}
      .receipt-header,
      .receipt-footer {{
        text-align: center;
      }}
      .receipt-logo-shell {{
        display: flex;
        justify-content: center;
        align-items: center;
        min-height: var(--logo-shell-height);
      }}
      .receipt-logo {{
        display: block;
        margin: 0;
        white-space: pre;
        line-height: 1.02;
        font-size: 4.25mm;
      }}
      .receipt-logo-image {{
        display: block;
        width: var(--logo-width);
        height: auto;
        image-rendering: pixelated;
      }}
      .receipt-logo-svg {{
        display: block;
        width: var(--logo-width);
        height: auto;
        color: var(--ink);
      }}
      .receipt-logo-svg--claude-code {{
        width: calc(var(--logo-width) - 0.8mm);
        transform: translateX(-0.45mm);
      }}
      .receipt-logo-image--codex,
      .receipt-logo-image--trae {{
        width: var(--logo-width);
        max-height: var(--logo-shell-height);
      }}
      .receipt-logo-label {{
        margin-top: 3mm;
        font-size: var(--logo-label-size);
        letter-spacing: 0.08em;
      }}
      .receipt-thanks,
      .receipt-meta {{
        margin-top: 2.7mm;
        font-size: var(--meta-size);
        line-height: 1.35;
      }}
      .receipt-meta {{
        margin-top: 0.9mm;
      }}
      .receipt-rule {{
        border-top: 0.35mm solid var(--rule);
        margin: 3.5mm 0;
      }}
      .receipt-rule.strong {{
        border-top-width: 0.55mm;
      }}
      .receipt-tip-panel {{
        width: min(var(--receipt-width), calc(100vw - 24px));
        display: flex;
        justify-content: center;
        margin-top: 10px;
      }}
      .receipt-tip-controls {{
        width: 100%;
        padding: 14px 16px;
        text-align: center;
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 16px;
      }}
      .receipt-tip-controls,
      .receipt-tip-controls * {{
        user-select: none;
      }}
      .receipt-tip-summary {{
        margin-top: 2.8mm;
      }}
      .tip-toggle {{
        display: inline-flex;
        align-items: center;
        gap: 10px;
        font-family: var(--font);
        font-size: 13px;
        font-weight: 600;
        color: var(--ink);
        cursor: pointer;
      }}
      .tip-toggle input {{
        appearance: none;
        -webkit-appearance: none;
        width: 36px;
        height: 22px;
        margin: 0;
        border: 1.5px solid var(--line);
        border-radius: 999px;
        background: var(--bg-2);
        position: relative;
        cursor: pointer;
        transition: background 0.2s var(--ease), border-color 0.2s var(--ease);
      }}
      .tip-toggle input::after {{
        content: "";
        position: absolute;
        top: 2px;
        left: 2px;
        width: 15px;
        height: 15px;
        border-radius: 50%;
        background: var(--surface);
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.18);
        transition: transform 0.2s var(--ease);
      }}
      .tip-toggle input:checked {{
        background: var(--accent);
        border-color: var(--accent-d);
      }}
      .tip-toggle input:checked::after {{
        transform: translateX(14px);
      }}
      .tip-options {{
        display: flex;
        justify-content: center;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 12px;
      }}
      .tip-options[hidden],
      .receipt-tip-summary[hidden] {{
        display: none !important;
      }}
      .tip-option {{
        appearance: none;
        font-family: var(--font);
        font-size: 13px;
        font-weight: 600;
        line-height: 1;
        color: var(--muted);
        background: var(--surface);
        border: 1.5px solid var(--line);
        border-radius: 10px;
        padding: 9px 14px;
        cursor: pointer;
        transition: border-color 0.15s, color 0.15s, background 0.15s;
      }}
      @media (hover: hover) {{
        .tip-option:hover {{
          border-color: var(--ink);
          color: var(--ink);
        }}
      }}
      .tip-option.is-selected {{
        background: var(--ink);
        color: var(--page-bg);
        border-color: var(--ink);
      }}
      .receipt-row {{
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        gap: 4mm;
        align-items: baseline;
        font-size: var(--row-size);
        line-height: 1.32;
      }}
      .receipt-label {{
        padding-right: 2mm;
        min-width: 0;
      }}
      .receipt-value {{
        text-align: right;
        white-space: nowrap;
      }}
      .receipt-total {{
        font-size: calc(var(--row-size) + 0.15mm);
      }}
      .receipt-footer {{
        margin-top: 3.2mm;
        padding: 0 0.6mm;
      }}
      .receipt-footer-line {{
        font-size: var(--footer-size);
        line-height: 1.35;
        white-space: normal;
        overflow-wrap: break-word;
        text-wrap: balance;
      }}
      .receipt-barcode {{
        margin: 3.6mm 0 1.4mm;
        white-space: pre;
        font-size: var(--barcode-size);
        line-height: 1;
        overflow: hidden;
      }}
      .receipt-barcode-id {{
        font-size: var(--barcode-id-size);
        line-height: 1.25;
        word-break: break-all;
      }}
      @page {{
        size: 80mm auto;
        margin: 0;
      }}
      @media print {{
        body {{
          background: #fff;
          padding: 0;
          -webkit-print-color-adjust: exact;
          print-color-adjust: exact;
        }}
        .topbar,
        .receipt-note,
        .printer,
        .receipt-tip-panel,
        .receipt-tip-controls {{
          display: none;
        }}
        .receipt-page {{
          display: block;
          padding: 0;
          background: transparent;
        }}
        .printer-output {{
          display: block;
          margin-top: 0;
          clip-path: none;
        }}
        .printer-output::before {{
          display: none;
        }}
        .receipt-shell {{
          filter: none;
          animation: none;
        }}
        .receipt {{
          width: var(--receipt-width);
          margin: 0 auto;
          -webkit-mask: none;
          mask: none;
          animation: none;
        }}
        .receipt::after {{
          display: none;
        }}
      }}
    </style>
  </head>
  <body>
{topbar}
    <main class="receipt-page">
      <div class="printer" aria-hidden="true">
        <span class="printer-label">Check, Please!</span>
        <span class="printer-led"></span>
      </div>
      <div class="printer-output">
{receipt_articles}
      </div>
{tip_panel}
    </main>
{tip_script}
  </body>
</html>
"""
