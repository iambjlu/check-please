# Share Payload Schema

`check-please` single-receipt share links are zero-storage links. The CLI encodes the receipt payload into the URL hash fragment:

```text
https://<host>/r#<base64url(zlib(json))>
```

Browsers do not send the `#...` fragment to the server, so the web app can restore the receipt client-side without uploading the payload.

## CLI

```text
check-please --output share-url --share-base https://example.com
check-please --share-url
```

`--share-base` defaults to `CHECK_PLEASE_WEB_BASE`, then `https://check-please.example`. The CLI always appends `/r` before the hash.

## Encoding

1. JSON with compact separators and UTF-8.
2. `zlib.compress(..., level=9)`.
3. URL-safe base64 without `=` padding.
4. Put the token after `#`, never in the path or query string.

## Version 1

Top-level payload:

```json
{
  "v": 1,
  "kind": "single-receipt",
  "language": "zh-TW",
  "agentTool": "codex",
  "receiptId": "CX_20260521_153000_ABC123",
  "date": "2026-05-21T15:30:00+08:00",
  "snapshot": {},
  "estimate": {},
  "receipt": {}
}
```

`snapshot` is a sanitized `UsageSnapshot`. It intentionally excludes `source`, because source can contain local paths or other host-specific details. `available_fields` is encoded as an array.

`estimate` is `PriceEstimate` as JSON: `status`, `amount`, `model`, `currency`, `source_url`, `source_checked_at`, and `rate_note`.

`receipt` is the rendered web component payload consumed by `web/lib/receipt.ts`: `agentTool`, `receiptId`, `barcode`, `languages`, and `tip`.

Supported languages are `en`, `zh-TW`, and `cantonese`. The alias `zh` is normalized by the CLI before payload creation.

## Size

The CLI warns when a generated share URL is over 8,000 characters. A normal single receipt should be well below that after compression.
