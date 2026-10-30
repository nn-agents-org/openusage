# Agent Usage Probe

A Linux-side helper that reports remaining AI provider limits as JSON, so containerised
agents can pick an executor by available quota. It is a port of the *network* part of
OpenUsage's providers (see `Sources/OpenUsage/Providers/...`); OpenUsage's own
`openusage` CLI is macOS-only and only reads the app cache.

## Output

Default (all providers):

```json
{
  "generatedAt": "...",
  "threshold_percent": 5.0,
  "providers": { ... },
  "models": [
    {"provider": "codex", "model": "codex", "limit_left": 58, "limit_reset_in_sec": 12345}
  ],
  "recommended": "codex",
  "errors": []
}
```

`--models` prints only the sorted array:

```json
[
  {"provider": "codex", "model": "codex", "limit_left": 58, "limit_reset_in_sec": 12345}
]
```

Sorted by `limit_left` descending.

## Providers and endpoints

| Provider | Auth source | Endpoint | Notes |
|---|---|---|---|
| Codex | `~/.codex/auth.json` (`tokens.access_token`) or `CODEX_ACCESS_TOKEN` | `GET https://chatgpt.com/backend-api/wham/usage` | Header `ChatGPT-Account-Id` if present. Refresh via `https://auth.openai.com/oauth/token` (client id `app_EMoamEEZ73f0CkXaXp7hrann`). `used_percent` is 0-100. Entries: `codex` (primary window), `codex-spark` (additional_rate_limits spark). |
| Claude | `~/.claude/.credentials.json` (`claudeAiOauth.accessToken`) or `CLAUDE_ACCESS_TOKEN` | `GET https://api.anthropic.com/api/oauth/usage` | Headers include `anthropic-beta: oauth-2025-04-20`, `User-Agent: claude-cli/2.1.294 (external, cli)`. Refresh via `https://platform.claude.com/v1/oauth/token` (client id `9d1c250a-e61b-44d9-88ed-5944d1962f5e`). `utilization` is 0-100. Entries: `claude` (five_hour), `claude-sonnet`, scoped `limits` (e.g. fable). |
| Antigravity | `~/.antigravity/auth.json` or `ANTIGRAVITY_ACCESS_TOKEN` | `POST https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary` | Bearer token; refresh via `https://oauth2.googleapis.com/token` (client id/secret from `BrowserProviderLogins`). `remainingFraction` is 0-1. Entries: `gemini`, `claude` (session buckets), `gemini-argon` (weekly). |
| OpenCode Go | `OPENCODE_API_KEY` or `~/.local/share/opencode/auth.json` | `GET https://opencode.ai/zen/go/v1/usage` | Bearer token. `percent` is 0-100; `resetsAt` ISO8601. Entry: `opencode-go` (rolling). |

## Re-creating the probe

1. Implement HTTP calls above with the same headers.
2. Read tokens from agent configs first, then env overrides `*_ACCESS_TOKEN` / `*_AUTH_FILE`.
3. Refresh access tokens on 401/403 using the documented client ids/secrets.
4. Normalise each provider to entries `{provider, model, limit_left, limit_reset_in_sec}`.
5. Sort entries by `limit_left` desc.
6. Print JSON.

## Agent selection convention

Callers pass a preferred model. If its `limit_left` >= threshold (default 5%), use it; otherwise
pick the first entry whose `model` differs from the preferred one.
