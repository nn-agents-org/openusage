#!/usr/bin/env python3
"""Probe AI provider usage limits on Linux and macOS.

Port of the network part of OpenUsage's providers. Tokens come from each agent's
own config files (plus Claude's macOS Keychain item) or *_ACCESS_TOKEN overrides;
refreshed tokens are written back to the file they came from.
"""
import argparse, json, os, sys, time, urllib.request, urllib.parse

def http(method, url, headers=None, body=None, timeout=15):
    req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        try:
            hdrs = {k.lower(): v for k, v in e.headers.items()}
        except Exception:
            hdrs = {}
        return e.code, e.read(), hdrs
    except Exception as e:
        return 0, str(e).encode(), {}

def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None

def to_epoch(v):
    if v is None: return None
    if isinstance(v,(int,float)):
        # seconds or ms
        if v > 1e12: return v/1000.0
        if v > 1e10: return v/1000.0
        return float(v)
    if isinstance(v,str):
        # ISO8601
        try:
            # python 3.7+ fromisoformat handles Z if replaced
            s = v.replace("Z","+00:00")
            import datetime
            dt = datetime.datetime.fromisoformat(s)
            return dt.timestamp()
        except Exception:
            try:
                return float(v)
            except Exception:
                return None
    return None

def now_epoch():
    return time.time()

def num(v):
    return v if isinstance(v,(int,float)) and not isinstance(v,bool) else None

# ---------- token loading ----------
def codex_token():
    if os.environ.get("CODEX_ACCESS_TOKEN"):
        return os.environ["CODEX_ACCESS_TOKEN"], os.environ.get("CODEX_REFRESH_TOKEN"), os.environ.get("CODEX_ACCOUNT_ID"), None
    for p in [
        os.environ.get("CODEX_AUTH_FILE"),
        os.path.expanduser("~/.codex/auth.json"),
        os.path.expanduser("~/.config/codex/auth.json"),
        os.path.expanduser("~/Library/Application Support/Codex/auth.json"),
        os.path.expanduser("~/Library/Application Support/com.openai.codex/auth.json"),
    ]:
        if not p: continue
        d = load_json(p)
        if not d: continue
        t = d.get("tokens") or d
        at = t.get("access_token") or t.get("accessToken")
        rt = t.get("refresh_token") or t.get("refreshToken")
        aid = t.get("account_id") or t.get("accountId") or d.get("account_id")
        if at: return at, rt, aid, p
    return None, None, None, None

def claude_token():
    if os.environ.get("CLAUDE_ACCESS_TOKEN"):
        return os.environ["CLAUDE_ACCESS_TOKEN"], os.environ.get("CLAUDE_REFRESH_TOKEN"), None
    for p in [
        os.environ.get("CLAUDE_AUTH_FILE"),
        os.path.expanduser("~/.claude/.credentials.json"),
        os.path.expanduser("~/.claude/credentials.json"),
        os.path.expanduser("~/.config/claude/credentials.json"),
        os.path.expanduser("~/Library/Application Support/Claude/credentials.json"),
        os.path.expanduser("~/Library/Application Support/claude/credentials.json"),
    ]:
        if not p: continue
        d = load_json(p)
        if not d: continue
        o = d.get("claudeAiOauth") or d.get("oauth") or d
        at = o.get("accessToken") or o.get("access_token")
        rt = o.get("refreshToken") or o.get("refresh_token")
        if at or rt: return at, rt, p
    # macOS stores Claude Code's credentials in the Keychain
    if sys.platform == "darwin":
        import subprocess
        for svc in ["Claude Code-credentials", "Claude Code", "claude-code"]:
            try:
                res = subprocess.run(
                    ["security", "find-generic-password", "-s", svc, "-w"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5
                )
                if res.returncode == 0 and res.stdout.strip():
                    d = json.loads(res.stdout.strip())
                    o = d.get("claudeAiOauth") or d.get("oauth") or d
                    at = o.get("accessToken") or o.get("access_token")
                    rt = o.get("refreshToken") or o.get("refresh_token")
                    if at or rt: return at, rt, "keychain:" + svc
            except Exception:
                pass
    return None, None, None

def antigravity_token():
    if os.environ.get("ANTIGRAVITY_ACCESS_TOKEN"):
        return os.environ["ANTIGRAVITY_ACCESS_TOKEN"], os.environ.get("ANTIGRAVITY_REFRESH_TOKEN"), None
    for p in [
        os.environ.get("ANTIGRAVITY_AUTH_FILE"),
        os.path.expanduser("~/.gemini/antigravity-cli/antigravity-oauth-token"),
        os.path.expanduser("~/.gemini/jetski-standalone-oauth-token"),
        os.path.expanduser("~/.gemini/antigravity-oauth-token"),
        os.path.expanduser("~/.gemini/antigravity/antigravity-oauth-token"),
        os.path.expanduser("~/.antigravity/auth.json"),
        os.path.expanduser("~/.config/antigravity/auth.json"),
        os.path.expanduser("~/.config/antigravity/credentials.json"),
        os.path.expanduser("~/Library/Application Support/Antigravity/credentials.json"),
        os.path.expanduser("~/Library/Application Support/Antigravity/auth.json"),
        os.path.expanduser("~/Library/Application Support/Antigravity IDE/credentials.json"),
    ]:
        if not p: continue
        d = load_json(p)
        if d:
            t = d.get("token") or d.get("tokens") or d.get("oauth") or d
            if isinstance(t, dict):
                at = t.get("access_token") or t.get("accessToken")
                rt = t.get("refresh_token") or t.get("refreshToken")
            elif isinstance(t, str):
                at, rt = t, None
            else:
                at, rt = None, None
            if at or rt: return at, rt, p
        else:
            # plain token file (e.g. ~/.gemini/antigravity-cli/antigravity-oauth-token)
            try:
                raw = open(p).read().strip()
            except Exception:
                raw = ""
            if raw:
                # support "access_token" or "access_token\nrefresh_token"
                lines = [x.strip() for x in raw.split() if x.strip()]
                if len(lines) >= 2:
                    return lines[0], lines[1], p
                return lines[0], None, p
    return None, None, None

def opencode_token():
    if os.environ.get("OPENCODE_API_KEY") or os.environ.get("OPENCODE_ACCESS_TOKEN"):
        return (os.environ.get("OPENCODE_API_KEY") or os.environ.get("OPENCODE_ACCESS_TOKEN")), None
    # opencode cli config
    for p in [
        os.environ.get("OPENCODE_AUTH_FILE"),
        os.path.expanduser("~/.local/share/opencode/auth.json"),
        os.path.expanduser("~/.config/opencode/auth.json"),
        os.path.expanduser("~/.opencode/auth.json"),
        os.path.expanduser("~/Library/Application Support/opencode/auth.json"),
    ]:
        if not p: continue
        d = load_json(p)
        if not d: continue
        # try common keys
        for key in ("opencode","openai","apiKey","api_key","token","access_token"):
            v = d.get(key)
            if isinstance(v, str) and v: return v, p
            if isinstance(v, dict):
                for kk in ("apiKey","api_key","token","access_token","key"):
                    if isinstance(v.get(kk),str) and v.get(kk): return v.get(kk), p
    # env file style
    for p in [os.path.expanduser("~/.config/opencode/.env"), os.path.expanduser("~/.opencode/.env")]:
        if os.path.exists(p):
            for line in open(p):
                if "API_KEY" in line or "TOKEN" in line:
                    parts = line.strip().split("=",1)
                    if len(parts)==2 and parts[1]: return parts[1].strip().strip('"').strip("'"), p
    return None, None

# ---------- persistence (write refreshed tokens back to their source file) ----------
def save_ag_token(p, new_at, rt=None):
    if not p or str(p).startswith("keychain:"): return
    try:
        d = load_json(p)
        if d and isinstance(d, dict):
            if "token" in d and isinstance(d["token"], dict):
                d["token"]["access_token"] = new_at
            else:
                d["access_token"] = new_at
            with open(p, "w", encoding="utf-8") as f:
                json.dump(d, f, indent=2)
        elif os.path.exists(p):
            with open(p, "w", encoding="utf-8") as f:
                if rt:
                    f.write(f"{new_at}\n{rt}\n")
                else:
                    f.write(f"{new_at}\n")
    except Exception:
        pass

def save_claude_token(p, new_at, new_rt=None):
    if not p or str(p).startswith("keychain:"): return
    try:
        d = load_json(p)
        if d and isinstance(d, dict):
            target = d.get("claudeAiOauth") if isinstance(d.get("claudeAiOauth"), dict) else d
            target["accessToken"] = new_at
            if new_rt:
                target["refreshToken"] = new_rt
            with open(p, "w", encoding="utf-8") as f:
                json.dump(d, f, indent=2)
    except Exception:
        pass

# ---------- refresh ----------
CLAUDE_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
AG_CLIENT_ID = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
AG_CLIENT_SECRET = "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"

def refresh_claude(rt):
    if not rt: return None, None
    data = urllib.parse.urlencode({"grant_type":"refresh_token","refresh_token":rt,"client_id":CLAUDE_CLIENT_ID}).encode()
    st, body, _ = http("POST","https://platform.claude.com/v1/oauth/token", {"Content-Type":"application/x-www-form-urlencoded", "User-Agent":"claude-cli/2.1.294 (external, cli)"}, data)
    if st//100 != 2: return None, None
    try:
        j = json.loads(body)
        return j.get("access_token"), j.get("refresh_token")
    except Exception:
        return None, None

def refresh_codex(rt):
    if not rt: return None
    data = urllib.parse.urlencode({"grant_type":"refresh_token","client_id":CODEX_CLIENT_ID,"refresh_token":rt}).encode()
    st, body, _ = http("POST","https://auth.openai.com/oauth/token", {"Content-Type":"application/x-www-form-urlencoded"}, data)
    if st//100 != 2: return None
    try: return json.loads(body)["access_token"]
    except Exception: return None

def refresh_ag(rt):
    if not rt: return None
    data = urllib.parse.urlencode({"client_id":AG_CLIENT_ID,"client_secret":AG_CLIENT_SECRET,"refresh_token":rt,"grant_type":"refresh_token"}).encode()
    st, body, _ = http("POST","https://oauth2.googleapis.com/token", {"Content-Type":"application/x-www-form-urlencoded"}, data)
    if st//100 != 2: return None
    try: return json.loads(body)["access_token"]
    except Exception: return None

# ---------- shared window parsing (Codex rate_limit shape) ----------
SESSION_SEC = 5*3600
WEEK_SEC = 7*24*3600
FAMILIAR_PERIODS = {SESSION_SEC, WEEK_SEC}

def _period_sec(w):
    if not isinstance(w, dict): return None
    s = num(w.get("limit_window_seconds"))
    return float(s) if s is not None else None

def _window_entry(provider, model, used, w):
    left = 100 - used
    reset = to_epoch(w.get("reset_at")) if isinstance(w, dict) else None
    if reset is None and isinstance(w, dict) and w.get("reset_after_seconds") is not None:
        reset = now_epoch() + float(w["reset_after_seconds"])
    return {
        "provider": provider, "model": model,
        "limit_left": max(0.0, left),
        "limit_reset_in_sec": int(max(0,(reset or now_epoch())-now_epoch())) if reset else None,
    }

def window_entries(rate_limit, resp_headers, provider, base_model):
    """Port of CodexUsageMapper.windowLines: the five-hour window normally sits in
    primary_window and the weekly one in secondary_window, but Codex can move a temporarily
    sole weekly limit into the primary slot. Each meter takes the window whose explicit
    limit_window_seconds is its own; failing that, the window in its own slot when that
    window's duration is absent or unfamiliar. A slot known only from its header percent is
    a window with no fields."""
    rl = rate_limit if isinstance(rate_limit, dict) else {}
    slots = []
    for key, hdr in (("primary_window","x-codex-primary-used-percent"),
                     ("secondary_window","x-codex-secondary-used-percent")):
        w = rl.get(key)
        hpct = None
        hv = (resp_headers or {}).get(hdr)
        if hv is not None:
            try: hpct = float(hv)
            except Exception: hpct = None
        if isinstance(w, dict):
            up = num(w.get("used_percent"))
            slots.append((w, up if up is not None else hpct))
        elif hpct is not None:
            slots.append(({}, hpct))
        else:
            slots.append(None)
    meters = [("session", SESSION_SEC, base_model), ("weekly", WEEK_SEC, base_model + "-weekly")]
    entries = []
    for slot_index, (_label, period, model) in enumerate(meters):
        exact = next((s for s in slots if s and _period_sec(s[0]) == period), None)
        candidate = exact
        if candidate is None:
            own = slots[slot_index]
            if own is not None:
                p = _period_sec(own[0])
                if p is None or p not in FAMILIAR_PERIODS:
                    candidate = own
        if candidate is None or num(candidate[1]) is None:
            continue
        entries.append(_window_entry(provider, model, candidate[1], candidate[0]))
    return entries

# ---------- probes ----------
def probe_codex(at, aid):
    headers = {"Authorization":"Bearer "+at, "Accept":"application/json", "User-Agent":"OpenUsage"}
    if aid: headers["ChatGPT-Account-Id"] = aid
    st, body, resp_headers = http("GET","https://chatgpt.com/backend-api/wham/usage", headers)
    raw = body.decode(errors="replace")
    try: j = json.loads(raw)
    except Exception: j = None
    entries = []
    remaining = None
    extra = {}
    if j:
        rl = j.get("rate_limit") or {}
        entries.extend(window_entries(rl, resp_headers, "codex", "codex"))
        # spark entries carry their own rate_limit with the same window shape
        for ar in j.get("additional_rate_limits",[]) or []:
            if not isinstance(ar,dict): continue
            name = str(ar.get("limit_name") or ar.get("metered_feature") or "").lower()
            if "spark" not in name: continue
            entries.extend(window_entries(ar.get("rate_limit") or {}, None, "codex", "codex-spark"))
            break
        # credit cap a workspace sets on the member
        sc = (j.get("spend_control") or {}).get("individual_limit")
        if isinstance(sc, dict):
            used, cap = num(sc.get("used")), num(sc.get("limit"))
            if used is not None and cap is not None and used >= 0 and cap > 0:
                reset = to_epoch(sc.get("reset_at"))
                entries.append({
                    "provider":"codex","model":"codex-credits",
                    "limit_left": max(0.0, (cap-used)/cap*100),
                    "limit_reset_in_sec": int(max(0,(reset or now_epoch())-now_epoch())) if reset else None,
                })
                extra["credit_limit"] = {"used": used, "limit": cap}
        # on-demand rate-limit reset credits (count only in the usage body)
        rlc = j.get("rate_limit_reset_credits")
        if isinstance(rlc, dict):
            cnt = num(rlc.get("available_count"))
            if cnt is not None and cnt >= 0:
                extra["reset_credits_available"] = int(cnt)
    lefts = [e["limit_left"] for e in entries]
    if lefts:
        remaining = min(lefts)
    out = {"provider":"codex","status":st,"remaining_percent":remaining,"entries":entries,"raw":j if j is not None else raw}
    out.update(extra)
    return out

def probe_claude_cached():
    """Fallback: Claude Code's cached utilization from ~/.claude.json, used when no token
    could be found or refreshed (e.g. a Keychain item this process can't read)."""
    for p in [
        os.path.expanduser("~/.claude.json"),
        os.path.expanduser("~/.claude/.claude.json"),
        os.path.expanduser("~/Library/Application Support/Claude/.claude.json"),
    ]:
        d = load_json(p)
        if not d or not isinstance(d, dict): continue
        cu = d.get("cachedUsageUtilization")
        if not isinstance(cu, dict): continue
        raw = cu.get("utilization")
        if not isinstance(raw, dict): continue
        entries = []
        utils = []
        fh = raw.get("five_hour")
        if isinstance(fh, dict) and isinstance(fh.get("utilization"), (int, float)):
            left = 100 - fh["utilization"]
            reset = to_epoch(fh.get("resets_at"))
            entries.append({"provider": "claude", "model": "claude", "limit_left": left, "limit_reset_in_sec": int(max(0, (reset or now_epoch()) - now_epoch())) if reset else None})
            utils.append(fh["utilization"])
        sd = raw.get("seven_day")
        if isinstance(sd, dict) and isinstance(sd.get("utilization"), (int, float)):
            left = 100 - sd["utilization"]
            reset = to_epoch(sd.get("resets_at"))
            entries.append({"provider": "claude", "model": "claude-sonnet", "limit_left": left, "limit_reset_in_sec": int(max(0, (reset or now_epoch()) - now_epoch())) if reset else None})
            utils.append(sd["utilization"])
        ss = raw.get("seven_day_sonnet")
        if isinstance(ss, dict) and isinstance(ss.get("utilization"), (int, float)):
            left = 100 - ss["utilization"]
            reset = to_epoch(ss.get("resets_at"))
            entries.append({"provider": "claude", "model": "claude-sonnet", "limit_left": left, "limit_reset_in_sec": int(max(0, (reset or now_epoch()) - now_epoch())) if reset else None})
            utils.append(ss["utilization"])
        if not entries: continue
        return {
            "provider": "claude",
            "status": 200,
            "remaining_percent": (100 - max(utils)) if utils else None,
            "entries": entries,
            "raw": raw,
        }
    return None

def probe_claude(at):
    headers = {"Authorization":"Bearer "+at.strip(), "Accept":"application/json", "Content-Type":"application/json", "anthropic-beta":"oauth-2025-04-20", "User-Agent":"claude-cli/2.1.294 (external, cli)"}
    st, body, _ = http("GET","https://api.anthropic.com/api/oauth/usage", headers)
    raw = body.decode(errors="replace")
    try: j = json.loads(raw)
    except Exception: j = None
    entries = []
    remaining = None
    utils = []
    if j:
        # session
        fh = j.get("five_hour")
        if isinstance(fh,dict) and isinstance(fh.get("utilization"),(int,float)):
            left = 100 - fh["utilization"]
            reset = to_epoch(fh.get("resets_at"))
            entries.append({"provider":"claude","model":"claude","limit_left":left,"limit_reset_in_sec": int(max(0,(reset or now_epoch())-now_epoch())) if reset else None})
            utils.append(fh["utilization"])
        # sonnet weekly scoped
        ss = j.get("seven_day_sonnet")
        if isinstance(ss,dict) and isinstance(ss.get("utilization"),(int,float)):
            left = 100 - ss["utilization"]
            reset = to_epoch(ss.get("resets_at"))
            entries.append({"provider":"claude","model":"claude-sonnet","limit_left":left,"limit_reset_in_sec": int(max(0,(reset or now_epoch())-now_epoch())) if reset else None})
            utils.append(ss["utilization"])
        # scoped limits (fable etc.)
        for lim in j.get("limits",[]) or []:
            if not isinstance(lim,dict): continue
            if lim.get("kind") != "weekly_scoped": continue
            scope = lim.get("scope") or {}
            model = (scope.get("model") or {}).get("display_name")
            if not model: continue
            pct = lim.get("percent")
            if not isinstance(pct,(int,float)): continue
            left = 100 - pct
            reset = to_epoch(lim.get("resets_at"))
            entries.append({"provider":"claude","model":model.lower().replace(" ","-"),"limit_left":left,"limit_reset_in_sec": int(max(0,(reset or now_epoch())-now_epoch())) if reset else None})
            utils.append(pct)
        if utils:
            remaining = 100 - max(utils)
    return {"provider":"claude","status":st,"remaining_percent":remaining,"entries":entries,"raw":j if j is not None else raw}

# Antigravity quota summary: production can return untouched Gemini windows; the daily
# endpoint has the active counters. Read daily first, and only fall back to production for
# missing buckets or a failed daily read (mirrors AntigravityUsageClient.quotaSummaryURLs).
AG_QUOTA_URLS = [
    "https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary",
    "https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary",
]
# The hub client identity exposes the separate Argon quota; the IDE identity omits it.
def _ag_user_agent():
    os_name = "darwin" if sys.platform == "darwin" else "linux"
    import platform
    arch = "arm64" if platform.machine() in ("arm64", "aarch64") else "amd64"
    return f"antigravity/hub/2.24.0 (aidev_client; os_type={os_name}; arch={arch})"
AG_KNOWN_BUCKETS = {
    "gemini-5h": "gemini",
    "gemini-weekly": "gemini-weekly",
    "3p-5h": "claude",
    "3p-weekly": "claude-weekly",
}
AG_ARGON_GROUP = "Gemini 4 Argon"

def _ag_groups(j):
    if not isinstance(j, dict): return []
    if isinstance(j.get("response"), dict):
        return j["response"].get("groups") or []
    if isinstance(j.get("groups"), list):
        return j["groups"]
    return []

def _ag_complete(j):
    usable = set()
    for g in _ag_groups(j):
        if not isinstance(g, dict) or g.get("displayName") == AG_ARGON_GROUP: continue
        for b in (g.get("buckets") or []):
            if not isinstance(b, dict): continue
            if isinstance(b.get("remainingFraction"), (int, float)) and b.get("bucketId"):
                usable.add(b["bucketId"])
    return all(bid in usable for bid in AG_KNOWN_BUCKETS)

def _ag_entry(model, frac, b):
    reset = to_epoch(b.get("resetTime"))
    return {
        "provider":"antigravity","model":model,
        "limit_left": max(0.0, min(1.0, frac))*100,
        "limit_reset_in_sec": int(max(0,(reset or now_epoch())-now_epoch())) if reset else None,
    }

def probe_antigravity(at):
    headers = {"Authorization":"Bearer "+at, "Accept":"application/json", "Content-Type":"application/json", "User-Agent":_ag_user_agent()}
    bodies = []
    status = 0
    last_raw = ""
    for index, url in enumerate(AG_QUOTA_URLS):
        st, body, _ = http("POST", url, headers, b"{}")
        status = st
        raw = body.decode(errors="replace")
        try: j = json.loads(raw)
        except Exception: j = None
        if j is None:
            last_raw = raw
            continue
        if st//100 != 2:
            last_raw = raw
            continue
        bodies.append(j)
        if index == 0 and _ag_complete(j):
            break
    entries = []
    remaining = None
    fracs = []
    if bodies:
        # pool buckets first-wins across responses, like AntigravityUsageMapper
        pooled = {}
        for j in bodies:
            for g in _ag_groups(j):
                if not isinstance(g, dict) or g.get("displayName") == AG_ARGON_GROUP: continue
                for b in (g.get("buckets") or []):
                    if not isinstance(b, dict): continue
                    bid = b.get("bucketId")
                    frac = b.get("remainingFraction")
                    if not bid or not isinstance(frac,(int,float)) or bid in pooled:
                        continue
                    pooled[bid] = (frac, b)
        for bid, model in AG_KNOWN_BUCKETS.items():
            if bid not in pooled: continue
            frac, b = pooled[bid]
            entries.append(_ag_entry(model, frac, b))
            fracs.append(min(1.0, max(0.0, frac)))
        # unknown buckets (new model quotas, e.g. a future Hydrogen group) still surface
        for bid, (frac, b) in pooled.items():
            if bid in AG_KNOWN_BUCKETS: continue
            model = str(bid).strip().lower().replace("_","-")
            entries.append(_ag_entry(model, frac, b))
            fracs.append(min(1.0, max(0.0, frac)))
        # the separate Argon weekly quota: only an unambiguous single weekly bucket counts
        for j in bodies:
            weekly = []
            for g in _ag_groups(j):
                if not isinstance(g, dict) or g.get("displayName") != AG_ARGON_GROUP: continue
                for b in (g.get("buckets") or []):
                    if not isinstance(b, dict) or b.get("window") != "weekly": continue
                    if b.get("disabled") is True: continue
                    if not isinstance(b.get("remainingFraction"), (int,float)): continue
                    if b.get("bucketId") in AG_KNOWN_BUCKETS: continue
                    weekly.append(b)
            if len(weekly) == 1:
                entries.append(_ag_entry("gemini-argon", weekly[0]["remainingFraction"], weekly[0]))
                fracs.append(min(1.0, max(0.0, weekly[0]["remainingFraction"])))
                break
        if fracs:
            remaining = min(fracs)*100
    raw_out = bodies[0] if len(bodies) == 1 else bodies
    if not bodies:
        raw_out = last_raw
    return {"provider":"antigravity","status":status,"remaining_percent":remaining,"entries":entries,"raw":raw_out}

def probe_opencode(at):
    headers = {"Authorization":"Bearer "+at, "Accept":"application/json"}
    st, body, _ = http("GET","https://opencode.ai/zen/go/v1/usage", headers)
    raw = body.decode(errors="replace")
    try: j = json.loads(raw)
    except Exception: j = None
    entries = []
    remaining = None
    if j:
        usage = j.get("usage") or {}
        rolling = usage.get("rolling")
        if isinstance(rolling,dict) and isinstance(rolling.get("percent"),(int,float)):
            left = 100 - rolling["percent"]
            reset = to_epoch(rolling.get("resetsAt"))
            entries.append({"provider":"opencode","model":"opencode-go","limit_left":left,"limit_reset_in_sec": int(max(0,(reset or now_epoch())-now_epoch())) if reset else None})
            remaining = left
    return {"provider":"opencode","status":st,"remaining_percent":remaining,"entries":entries,"raw":j if j is not None else raw}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pick", action="store_true")
    ap.add_argument("--threshold", type=float, default=5.0)
    ap.add_argument("--models", action="store_true", help="alias for default short output")
    ap.add_argument("--raw", action="store_true", help="print full provider details")
    args = ap.parse_args()

    results = []

    # Codex
    at, rt, aid, _src = codex_token()
    if at:
        r = probe_codex(at, aid)
        if r["status"] not in (200,201) and rt:
            new = refresh_codex(rt)
            if new: r = probe_codex(new, aid)
        results.append(r)

    # Claude
    at, rt, src = claude_token()
    r_claude = None
    if at:
        r_claude = probe_claude(at)
    if (not r_claude or r_claude["status"] not in (200,201)) and rt:
        new_at, new_rt = refresh_claude(rt)
        if new_at:
            r_claude = probe_claude(new_at)
            save_claude_token(src, new_at, new_rt)
    if not r_claude or r_claude["status"] not in (200, 201):
        cached_r = probe_claude_cached()
        if cached_r:
            r_claude = cached_r
    if r_claude:
        results.append(r_claude)

    # Antigravity
    at, rt, src = antigravity_token()
    r_ag = None
    if at:
        r_ag = probe_antigravity(at)
    if (not r_ag or r_ag["status"] not in (200,201)) and rt:
        new = refresh_ag(rt)
        if new:
            r_ag = probe_antigravity(new)
            save_ag_token(src, new, rt)
    if r_ag:
        results.append(r_ag)

    # OpenCode Go
    at, _src = opencode_token()
    if at:
        r = probe_opencode(at)
        results.append(r)

    # collect entries
    all_entries = []
    for r in results:
        all_entries.extend(r.get("entries",[]))
    all_entries.sort(key=lambda e: (e.get("limit_left") is None, -(e.get("limit_left") or 0)))

    eligible = [r for r in results if r.get("remaining_percent") is not None and r["remaining_percent"] >= args.threshold]
    recommended = max(eligible, key=lambda r: r["remaining_percent"])["provider"] if eligible else None

    if args.raw:
        out = {
            "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "threshold_percent": args.threshold,
            "providers": {r["provider"]: r for r in results},
            "models": all_entries,
            "recommended": recommended,
            "errors": [r["provider"] for r in results if r["status"] not in (200,201)],
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(all_entries, indent=2, ensure_ascii=False))
    if args.pick:
        print("RECOMMENDED=" + (recommended or "NONE"), file=sys.stderr)

if __name__ == "__main__":
    main()
