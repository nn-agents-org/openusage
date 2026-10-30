#!/usr/bin/env python3
"""Probe AI provider usage limits from inside a Linux container.

Linux port of the network part of OpenUsage's providers.
"""
import argparse, json, os, sys, time, urllib.request, urllib.parse

def http(method, url, headers=None, body=None, timeout=15):
    req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode()

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

# ---------- token loading ----------
def codex_token():
    if os.environ.get("CODEX_ACCESS_TOKEN"):
        return os.environ["CODEX_ACCESS_TOKEN"], os.environ.get("CODEX_REFRESH_TOKEN"), os.environ.get("CODEX_ACCOUNT_ID")
    for p in [os.environ.get("CODEX_AUTH_FILE"), os.path.expanduser("~/.codex/auth.json"), os.path.expanduser("~/.config/codex/auth.json")]:
        if not p: continue
        d = load_json(p)
        if not d: continue
        t = d.get("tokens") or d
        at = t.get("access_token") or t.get("accessToken")
        rt = t.get("refresh_token") or t.get("refreshToken")
        aid = t.get("account_id") or t.get("accountId") or d.get("account_id")
        if at: return at, rt, aid
    return None, None, None

def claude_token():
    if os.environ.get("CLAUDE_ACCESS_TOKEN"):
        return os.environ["CLAUDE_ACCESS_TOKEN"], os.environ.get("CLAUDE_REFRESH_TOKEN")
    for p in [os.environ.get("CLAUDE_AUTH_FILE"), os.path.expanduser("~/.claude/.credentials.json"), os.path.expanduser("~/.claude/credentials.json"), os.path.expanduser("~/.config/claude/credentials.json")]:
        if not p: continue
        d = load_json(p)
        if not d: continue
        o = d.get("claudeAiOauth") or d.get("oauth") or d
        at = o.get("accessToken") or o.get("access_token")
        rt = o.get("refreshToken") or o.get("refresh_token")
        if at: return at, rt
    return None, None

def antigravity_token():
    if os.environ.get("ANTIGRAVITY_ACCESS_TOKEN"):
        return os.environ["ANTIGRAVITY_ACCESS_TOKEN"], os.environ.get("ANTIGRAVITY_REFRESH_TOKEN")
    for p in [os.environ.get("ANTIGRAVITY_AUTH_FILE"), os.path.expanduser("~/.gemini/antigravity-cli/antigravity-oauth-token"), os.path.expanduser("~/.antigravity/auth.json"), os.path.expanduser("~/.config/antigravity/auth.json"), os.path.expanduser("~/.config/antigravity/credentials.json")]:
        if not p: continue
        d = load_json(p)
        if d:
            t = d.get("token") or d.get("tokens") or d.get("oauth") or d
            at = t.get("access_token") or t.get("accessToken")
            rt = t.get("refresh_token") or t.get("refreshToken")
            if at: return at, rt
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
                    return lines[0], lines[1]
                return lines[0], None
    return None, None

def opencode_token():
    if os.environ.get("OPENCODE_API_KEY") or os.environ.get("OPENCODE_ACCESS_TOKEN"):
        return os.environ.get("OPENCODE_API_KEY") or os.environ.get("OPENCODE_ACCESS_TOKEN")
    # opencode cli config
    for p in [os.environ.get("OPENCODE_AUTH_FILE"), os.path.expanduser("~/.local/share/opencode/auth.json"), os.path.expanduser("~/.config/opencode/auth.json"), os.path.expanduser("~/.opencode/auth.json")]:
        if not p: continue
        d = load_json(p)
        if not d: continue
        # try common keys
        for key in ("opencode","openai","apiKey","api_key","token","access_token"):
            v = d.get(key)
            if isinstance(v, str) and v: return v
            if isinstance(v, dict):
                for kk in ("apiKey","api_key","token","access_token","key"):
                    if isinstance(v.get(kk),str) and v.get(kk): return v.get(kk)
    # env file style
    for p in [os.path.expanduser("~/.config/opencode/.env"), os.path.expanduser("~/.opencode/.env")]:
        if os.path.exists(p):
            for line in open(p):
                if "API_KEY" in line or "TOKEN" in line:
                    parts = line.strip().split("=",1)
                    if len(parts)==2 and parts[1]: return parts[1].strip().strip('"').strip("'")
    return None

# ---------- refresh ----------
CLAUDE_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
AG_CLIENT_ID = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
AG_CLIENT_SECRET = "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"

def refresh_claude(rt):
    if not rt: return None
    data = urllib.parse.urlencode({"grant_type":"refresh_token","refresh_token":rt,"client_id":CLAUDE_CLIENT_ID}).encode()
    st, body = http("POST","https://platform.claude.com/v1/oauth/token", {"Content-Type":"application/x-www-form-urlencoded"}, data)
    if st//100 != 2: return None
    try: return json.loads(body)["access_token"]
    except Exception: return None

def refresh_codex(rt):
    if not rt: return None
    data = urllib.parse.urlencode({"grant_type":"refresh_token","client_id":CODEX_CLIENT_ID,"refresh_token":rt}).encode()
    st, body = http("POST","https://auth.openai.com/oauth/token", {"Content-Type":"application/x-www-form-urlencoded"}, data)
    if st//100 != 2: return None
    try: return json.loads(body)["access_token"]
    except Exception: return None

def refresh_ag(rt):
    if not rt: return None
    data = urllib.parse.urlencode({"client_id":AG_CLIENT_ID,"client_secret":AG_CLIENT_SECRET,"refresh_token":rt,"grant_type":"refresh_token"}).encode()
    st, body = http("POST","https://oauth2.googleapis.com/token", {"Content-Type":"application/x-www-form-urlencoded"}, data)
    if st//100 != 2: return None
    try: return json.loads(body)["access_token"]
    except Exception: return None

# ---------- probes ----------
def probe_codex(at, aid):
    headers = {"Authorization":"Bearer "+at, "Accept":"application/json", "User-Agent":"OpenUsage"}
    if aid: headers["ChatGPT-Account-Id"] = aid
    st, body = http("GET","https://chatgpt.com/backend-api/wham/usage", headers)
    raw = body.decode(errors="replace")
    try: j = json.loads(raw)
    except Exception: j = None
    entries = []
    remaining = None
    if j:
        rl = j.get("rate_limit") or {}
        # session model entry from primary window
        pw = rl.get("primary_window")
        if isinstance(pw, dict) and isinstance(pw.get("used_percent"),(int,float)):
            reset = to_epoch(pw.get("reset_at"))
            if reset is None and pw.get("reset_after_seconds") is not None:
                reset = now_epoch() + float(pw.get("reset_after_seconds"))
            left = 100 - pw["used_percent"]
            entries.append({"provider":"codex","model":"codex","limit_left":left,"limit_reset_in_sec": int(max(0,(reset or now_epoch())-now_epoch())) if reset else None})
            remaining = left
        # spark model
        for ar in j.get("additional_rate_limits",[]) or []:
            if not isinstance(ar,dict): continue
            name = str(ar.get("limit_name") or ar.get("metered_feature") or "").lower()
            if "spark" not in name: continue
            sprl = ar.get("rate_limit") or {}
            spw = sprl.get("primary_window") or sprl.get("secondary_window")
            if isinstance(spw, dict) and isinstance(spw.get("used_percent"),(int,float)):
                reset = to_epoch(spw.get("reset_at"))
                if reset is None and spw.get("reset_after_seconds") is not None:
                    reset = now_epoch() + float(spw.get("reset_after_seconds"))
                left = 100 - spw["used_percent"]
                entries.append({"provider":"codex","model":"codex-spark","limit_left":left,"limit_reset_in_sec": int(max(0,(reset or now_epoch())-now_epoch())) if reset else None})
    return {"provider":"codex","status":st,"remaining_percent":remaining,"entries":entries,"raw":j if j is not None else raw}

def probe_claude(at):
    headers = {"Authorization":"Bearer "+at.strip(), "Accept":"application/json", "Content-Type":"application/json", "anthropic-beta":"oauth-2025-04-20", "User-Agent":"claude-cli/2.1.294 (external, cli)"}
    st, body = http("GET","https://api.anthropic.com/api/oauth/usage", headers)
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

def probe_antigravity(at):
    headers = {"Authorization":"Bearer "+at, "Accept":"application/json", "Content-Type":"application/json", "User-Agent":"antigravity/2.24.0 (aidev_client; os_type=linux; arch=amd64)"}
    st, body = http("POST","https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary", headers, b"{}")
    raw = body.decode(errors="replace")
    try: j = json.loads(raw)
    except Exception: j = None
    entries = []
    remaining = None
    fracs = []
    if j:
        # walk groups
        groups = []
        if isinstance(j.get("response"),dict):
            groups = j["response"].get("groups") or []
        elif isinstance(j.get("groups"),list):
            groups = j["groups"]
        bucket_map = {
            "gemini-5h": ("antigravity","gemini"),
            "3p-5h": ("antigravity","claude"),
        }
        for g in groups:
            if not isinstance(g,dict): continue
            for b in (g.get("buckets") or []):
                if not isinstance(b,dict): continue
                bid = b.get("bucketId")
                frac = b.get("remainingFraction")
                if bid in bucket_map and isinstance(frac,(int,float)):
                    prov,model = bucket_map[bid]
                    left = frac*100
                    reset = to_epoch(b.get("resetTime"))
                    entries.append({"provider":prov,"model":model,"limit_left":left,"limit_reset_in_sec": int(max(0,(reset or now_epoch())-now_epoch())) if reset else None})
                    fracs.append(frac)
        # argon weekly
        for g in groups:
            if not isinstance(g,dict): continue
            if g.get("displayName") != "Gemini 4 Argon": continue
            for b in (g.get("buckets") or []):
                if not isinstance(b,dict): continue
                if b.get("window") != "weekly": continue
                frac = b.get("remainingFraction")
                if isinstance(frac,(int,float)):
                    reset = to_epoch(b.get("resetTime"))
                    entries.append({"provider":"antigravity","model":"gemini-argon","limit_left":frac*100,"limit_reset_in_sec": int(max(0,(reset or now_epoch())-now_epoch())) if reset else None})
                    fracs.append(frac)
        if fracs:
            remaining = min(fracs)*100
    return {"provider":"antigravity","status":st,"remaining_percent":remaining,"entries":entries,"raw":j if j is not None else raw}

def probe_opencode(at):
    headers = {"Authorization":"Bearer "+at, "Accept":"application/json"}
    st, body = http("GET","https://opencode.ai/zen/go/v1/usage", headers)
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
    at, rt, aid = codex_token()
    if at:
        r = probe_codex(at, aid)
        if r["status"] not in (200,201) and rt:
            new = refresh_codex(rt)
            if new: r = probe_codex(new, aid)
        results.append(r)

    # Claude
    at, rt = claude_token()
    if at:
        r = probe_claude(at)
        if r["status"] not in (200,201) and rt:
            new = refresh_claude(rt)
            if new: r = probe_claude(new)
        results.append(r)

    # Antigravity
    at, rt = antigravity_token()
    if at:
        r = probe_antigravity(at)
        if r["status"] not in (200,201) and rt:
            new = refresh_ag(rt)
            if new: r = probe_antigravity(new)
        results.append(r)

    # OpenCode Go
    at = opencode_token()
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
