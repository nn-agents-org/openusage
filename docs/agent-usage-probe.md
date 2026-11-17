# Agent Usage Probe

A helper that reports remaining AI provider limits as JSON, so containerised agents can pick an
executor by available quota. Runs on Linux (container) and macOS (reads the agents' own config files,
and Claude's Keychain item). It is a port of the *network* part of OpenUsage's providers (see
`Sources/OpenUsage/Providers/...`); OpenUsage's own `openusage` CLI is macOS-only and only reads the
app cache.

## Output

Default output (short list):

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
| Codex | `~/.codex/auth.json` (`tokens.access_token`) or `CODEX_ACCESS_TOKEN` | `GET https://chatgpt.com/backend-api/wham/usage` | Header `ChatGPT-Account-Id` if present. Refresh via `https://auth.openai.com/oauth/token` (client id `app_EMoamEEZ73f0CkXaXp7hrann`). `used_percent` is 0-100. Windows are matched by `limit_window_seconds` (5h session, weekly), not by slot: Codex can move a sole weekly limit into `primary_window`; header percents `x-codex-primary-used-percent` / `x-codex-secondary-used-percent` back empty slots. Entries: `codex`, `codex-weekly`, `codex-spark`, `codex-spark-weekly`, `codex-credits` (workspace `spend_control.individual_limit`); `reset_credits_available` (count of on-demand resets) rides on the provider object. |
| Claude | `~/.claude/.credentials.json` (`claudeAiOauth.accessToken`) or `CLAUDE_ACCESS_TOKEN` | `GET https://api.anthropic.com/api/oauth/usage` | Headers include `anthropic-beta: oauth-2025-04-20`, `User-Agent: claude-cli/2.1.294 (external, cli)`. Refresh via `https://platform.claude.com/v1/oauth/token` (client id `9d1c250a-e61b-44d9-88ed-5944d1962f5e`). `utilization` is 0-100. Entries: `claude` (five_hour), `claude-sonnet`, scoped `limits` (e.g. fable). |
| Antigravity | `~/.gemini/antigravity-cli/antigravity-oauth-token`, `~/.antigravity/auth.json` or `ANTIGRAVITY_ACCESS_TOKEN` | `POST …/v1internal:retrieveUserQuotaSummary` on `daily-cloudcode-pa.googleapis.com` first, then `cloudcode-pa.googleapis.com` | Bearer token; refresh via `https://oauth2.googleapis.com/token` (client id/secret from `BrowserProviderLogins`). `remainingFraction` is 0-1. User-Agent must be the hub client identity (`antigravity/hub/2.24.0 (aidev_client; …)`); the IDE identity omits the Argon quota. Production can return untouched Gemini windows, so daily is read first and production only fills missing buckets (first-wins pooling). Entries: `gemini`, `gemini-weekly`, `claude`, `claude-weekly` (3p models), `gemini-argon` (the separate weekly Argon quota), plus one entry per unknown bucket id — so new model quotas (e.g. Hydrogen) surface without a script change. |
| OpenCode Go | `OPENCODE_API_KEY` or `~/.local/share/opencode/auth.json` | `GET https://opencode.ai/zen/go/v1/usage` | Bearer token. `percent` is 0-100; `resetsAt` ISO8601. Entry: `opencode-go` (rolling). |

## Auth sources per platform

The probe reads each agent's own config, with env overrides (`*_ACCESS_TOKEN` / `*_AUTH_FILE`) taking
precedence. Linux paths come first, then macOS:

- **Codex:** `~/.codex/auth.json`, `~/.config/codex/auth.json`, `~/Library/Application Support/Codex/auth.json`, `~/Library/Application Support/com.openai.codex/auth.json`.
- **Claude:** `~/.claude/.credentials.json`, `~/.claude/credentials.json`, `~/.config/claude/credentials.json`, `~/Library/Application Support/Claude/credentials.json`; on macOS also the Keychain via `security find-generic-password -s <svc> -w` for services `Claude Code-credentials`, `Claude Code`, `claude-code` (the item holds the same `claudeAiOauth` JSON).
- **Antigravity:** `~/.gemini/antigravity-cli/antigravity-oauth-token` (plain token or `access_token\nrefresh_token`), `~/.gemini/jetski-standalone-oauth-token`, `~/.gemini/antigravity-oauth-token`, `~/.gemini/antigravity/antigravity-oauth-token`, `~/.antigravity/auth.json`, `~/.config/antigravity/{auth,credentials}.json`, `~/Library/Application Support/Antigravity{, IDE}/{auth,credentials}.json`.
- **OpenCode:** `~/.local/share/opencode/auth.json`, `~/.config/opencode/auth.json`, `~/.opencode/auth.json`, `~/Library/Application Support/opencode/auth.json`, or an `.env` file with `API_KEY`/`TOKEN`.

Refreshed access tokens are written back to the file they came from (never to a Keychain item). When
Claude's token can't be found or refreshed at all, the probe falls back to Claude Code's cached
utilization in `~/.claude.json` (`cachedUsageUtilization`).

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
