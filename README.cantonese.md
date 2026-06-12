<div align="center">
  <p>
    <a href="./README.md">English</a> |
    <a href="./README.zh-TW.md">繁體中文</a> |
    <a href="./README.cantonese.md">Cantonese</a>
  </p>
  <h1>check-please</h1>
  <p><strong>將 AI 用量，印成一張識得補刀嘅單。</strong></p>
</div>

## 呢個係咩

`check-please` 會將今次 AI 對話用咗幾多 token / context，打成一張 monospace 熱敏紙單。

佢唔係 dashboard，亦唔係 spreadsheet。佢會先讀本機真實日誌，再用 `check_please/pricing.json` 入面嘅價格表估算成本；如果模型未對應到價格，就會老老實實顯示未對應，唔會扮識計。

## 預覽

```text
                    ▐▛███▜▌
                   ▝▜█████▛▘
                     ▘▘ ▝▝
                  CLAUDE CODE

                多謝使用 Claude
        單號: CC_20260427_151928_7CE382
            日期: 2026-04-27 15:19:28
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
供應商                                 ANTHROPIC
模型                           claude-sonnet-4.5
已用上下文                                12,487
────────────────────────────────────────────────
項目                                       TOKEN
────────────────────────────────────────────────
輸入 Tokens                               12,487
輸出 Tokens                                3,215
快取讀取                                   8,742
推理 Tokens                                  128
快取寫入                                   1,024
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
總數                               15,702 Tokens
────────────────────────────────────────────────
USD 估算                               $0.064771
價格對應                       claude-sonnet-4.5
價格日期                              2026-04-25
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                畫面順，銀包震。

        ||| ||||| || ||| | | || |||  | |
           CC_20260427_151928_7CE382
```

## 安裝

建議用 Skills CLI 安裝：

```bash
npx skills add https://github.com/chelswcs/check-please -g -y
```

只想裝到指定工具都得：

```bash
npx skills add https://github.com/chelswcs/check-please -a codex -y
npx skills add https://github.com/chelswcs/check-please -a claude-code -y
npx skills add https://github.com/chelswcs/check-please -a opencode -y
```

本機 CLI 用法：

```bash
python3 -m pip install -e .
check-please --agent-tool codex --chat-reply
```

## 用法

喺 chat 入面講以下任一句，或者直接跑 CLI：

- `token receipt`
- `token 單`
- `token 小票`
- `AI 用量帳單`
- `把今次對話打成單`
- `把今次對話打成小票`
- `睇下今輪 token 消耗`
- `廣東話 token 單`
- `廣東話 token 小票`
- `用廣東話出單`
- `用廣東話出小票`
- `廣東話 token receipt`

例子：

```bash
python3 scripts/check_please.py --agent-tool codex --chat-reply --language cantonese
python3 scripts/check_please.py --agent-tool claude-code --chat-reply --language cantonese
python3 scripts/check_please.py --agent-tool opencode --chat-reply --language cantonese
```

輸出可打印 HTML，並用預設瀏覽器打開：

```bash
python3 scripts/check_please.py --agent-tool claude-code --output html --write ./receipt.html --open-html --language cantonese
```

## 支援軟件

| 軟件 | 狀態 | 資料來源 | 備註 |
| --- | --- | --- | --- |
| Codex | `已支援` | Codex JSONL Session | 直接讀本機 Session 紀錄 |
| Claude Code | `已支援` | Claude usage-data + projects | Token 用 usage log，Model 用對話紀錄查 |
| Trae | `而家手動模式` | Trae App Storage | 自動匯入對話紀錄未出 |
| Cursor / Manus / Antigravity / 其他 agent | `手動模式` | 冇穩定本地用量日誌 | Agent 自己帶 `--input-tokens` / `--output-tokens`，配 `--agent-tool <host>` 顯示宿主名 |
| OpenCode | `已支援` | `opencode*.db` SQLite（`~/.local/share/opencode/`，見 `OPENCODE_DATA_DIR`、`XDG_DATA_HOME`） | 讀 `session`/`message` 行；支援 `--scope latest-turn` \| `session` |

## 注意事項

- 部分 Trae 版本用 `Trae CN` / `.trae-cn` 而唔係 `Trae`。
- 喺 Codex 入面跑，runtime 會自動識別，`check-please` 會讀 Codex logs。
- 喺 Claude Code 嘅 SessionEnd hook 入面跑，`check-please` 會讀 Claude Code usage logs。
- 如果係喺普通 shell 跑，而且本機有多個工具嘅 log，記得用 `--agent-tool` 指定邊個。

## 頁腳

靈感來自：[Hchen1218/token-receipt](https://github.com/Hchen1218/token-receipt) 同 [chrishutchinson/claude-receipts](https://github.com/chrishutchinson/claude-receipts)。
