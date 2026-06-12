<div align="center">
  <p>
    <a href="./README.md">English</a> |
    <a href="./README.zh-TW.md">繁體中文</a> |
    <a href="./README.cantonese.md">廣東話</a>
  </p>
  <h1>check-please</h1>
  <p><strong>把 AI Token 用量變成一張有梗的收據。</strong></p>
</div>

## 這是什麼

check-please 會把 AI Token 使用量整理成一張等寬字體收據。

你可以直接貼到聊天室、輸出成 HTML，或立刻截圖分享。
它會優先讀取本機紀錄，再根據官方價格估算成本；遇到缺少的資料時，會如實標示，而不是自行猜測。

## 預覽

```text
                    ▐▛███▜▌
                   ▝▜█████▛▘
                     ▘▘ ▝▝
                  CLAUDE CODE

                感謝使用 Claude
      收據號碼: CC_20260427_151928_7CE382
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
總計                               15,702 Tokens
────────────────────────────────────────────────
USD 預估                               $0.064771
價格對應                       claude-sonnet-4.5
價格日期                              2026-04-25
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
             畫面對齊了，預算沒有。

        ||| ||||| || ||| | | || |||  | |
           CC_20260427_151928_7CE382
```

## 安裝

推薦透過 Skills CLI 安裝：

```bash
npx skills add https://github.com/chelswcs/check-please -g -y
```

如果只想安裝到特定工具：

```bash
npx skills add https://github.com/chelswcs/check-please -a codex -y
npx skills add https://github.com/chelswcs/check-please -a claude-code -y
npx skills add https://github.com/chelswcs/check-please -a opencode -y
```

本機 CLI 使用方式：

```bash
python3 -m pip install -e .
check-please --agent-tool codex --chat-reply
```

## 使用方式

直接在聊天中輸入以下任一指令，或透過 CLI 執行：

- `token receipt`
- `token bill`
- `usage receipt`
- `token 收據`
- `AI 用量帳單`
- `把這次對話打成收據`
- `看看這輪 token 消耗`
- `查看本次對話 Token 消耗`

範例：

```bash
python3 scripts/check_please.py --agent-tool codex --chat-reply
python3 scripts/check_please.py --agent-tool claude-code --chat-reply
python3 scripts/check_please.py --agent-tool opencode --chat-reply
```

輸出可列印的 HTML，並用預設瀏覽器打開：

```bash
python3 scripts/check_please.py --agent-tool claude-code --output html --write ./receipt.html --open-html
```

## 支援軟體

| 軟體 | 狀態 | 資料來源 | 備註 |
| --- | --- | --- | --- |
| Codex | `已支援` | Codex JSONL Session | 直接讀取本機 Session 紀錄 |
| Claude Code | `已支援` | Claude usage-data + projects | Token 來自 usage log，Model 來自對話紀錄 |
| Trae | `目前手動模式` | Trae App Storage | 尚未支援自動匯入對話紀錄 |
| Cursor / Manus / Antigravity / 其他 agent | `手動模式` | 無穩定本地用量日誌 | Agent 自行帶 `--input-tokens` / `--output-tokens`，配 `--agent-tool <host>` 顯示宿主標識 |
| OpenCode | `已支援` | OpenCode SQLite Database | 支援 `latest-turn` 與 `session` 統計 |

## 注意事項

- 部分 Trae 版本使用 `Trae CN` 或 `.trae-cn` 路徑。
- 在 Codex 內執行時，會自動偵測並讀取 Codex 紀錄。
- 在 Claude Code SessionEnd Hook 中執行時，會自動讀取 Claude Code Usage Log。
- 若系統偵測到多個工具的本機紀錄，請使用 `--agent-tool` 指定來源。

## Footer

靈感來自：[Hchen1218/token-receipt](https://github.com/Hchen1218/token-receipt) 及 [chrishutchinson/claude-receipts](https://github.com/chrishutchinson/claude-receipts)。
