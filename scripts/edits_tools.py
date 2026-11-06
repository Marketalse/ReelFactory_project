#!/usr/bin/env python3
"""List the tools of the Instagram Edits desktop app's Automation server (read-only: it only asks "what tools do you have?"). Free, changes nothing.
    python3 scripts/edits_tools.py                 asks for the access token (hidden): in Edits > Automation click Copy, then paste here and press Enter
    python3 scripts/edits_tools.py --schemas       also saves every tool WITH its parameters to ~/.reelfactory/edits/tools.json (no token inside)
    python3 scripts/edits_tools.py --probe         also calls a few READ-ONLY tools (rules, caption styles, transitions, catalog kinds, app state) and saves
                                                   the answers to ~/.reelfactory/edits/probe.json. Only the names in PROBE_ALLOWED can ever be called here.
Needs Edits open with "Enable Automation Server" on. The token is never printed or stored. Set EDITS_URL / EDITS_TOKEN to skip the prompt."""
import getpass, json, os, sys, urllib.error, urllib.request

PROBE_ALLOWED = ("getCapabilities", "listCaptionStyles", "listTransitionsCatalog", "listCatalogKinds", "appState")     # read-only; nothing else can be called by this script
OUT = os.path.expanduser("~/.reelfactory/edits")
URL = os.environ.get("EDITS_URL", "http://127.0.0.1:19501/mcp")
TOKEN = os.environ.get("EDITS_TOKEN", "").strip() or getpass.getpass("Paste the Edits access token (nothing shows while you paste), then press Enter: ").strip()
if not TOKEN: sys.exit("No token given.")
H = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


def post(body, sid=None):
    h = dict(H)
    if sid: h["Mcp-Session-Id"] = sid
    r = urllib.request.urlopen(urllib.request.Request(URL, json.dumps(body).encode(), h), timeout=20)
    txt = r.read().decode(); sid2 = r.headers.get("Mcp-Session-Id") or sid
    for line in txt.splitlines():                                   # the answer is plain JSON or a server-sent event
        line = line.strip()
        if line.startswith("data:"): line = line[5:].strip()
        if line.startswith("{"): return json.loads(line), sid2
    return (json.loads(txt) if txt.strip().startswith("{") else {}), sid2


try:
    init, sid = post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "tool-list", "version": "1"}}})
    post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    res, _ = post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, sid)
except urllib.error.HTTPError as e:
    sys.exit(f"Edits answered HTTP {e.code} (401 = wrong token: click Regenerate in Edits and try again; is Edits open and the Automation Server on?)")
except OSError as e:
    sys.exit(f"Could not reach Edits at {URL}: {e}. Open Edits and turn on Enable Automation Server.")
print("Connected to:", (init.get("result") or {}).get("serverInfo"))
tools = (res.get("result") or {}).get("tools", [])
print(len(tools), "tools:")
for t in tools: print("-", t.get("name"), "|", (t.get("description") or "").strip().replace("\n", " ")[:200])
if "--schemas" in sys.argv:
    os.makedirs(OUT, exist_ok=True)
    json.dump([{"name": x.get("name"), "description": x.get("description"), "inputSchema": x.get("inputSchema")} for x in tools], open(os.path.join(OUT, "tools.json"), "w"), ensure_ascii=False, indent=1)
    print("saved the tools with their parameters to", os.path.join(OUT, "tools.json"))
if "--probe" in sys.argv:
    os.makedirs(OUT, exist_ok=True); got = {}
    names = {x.get("name") for x in tools}
    for n, name in enumerate(PROBE_ALLOWED, start=10):
        if name not in names: got[name] = "not offered"; continue
        try: r, _ = post({"jsonrpc": "2.0", "id": n, "method": "tools/call", "params": {"name": name, "arguments": {}}}, sid)
        except (urllib.error.HTTPError, OSError) as e: got[name] = f"failed: {e}"; continue
        got[name] = r.get("result") or r.get("error")
    json.dump(got, open(os.path.join(OUT, "probe.json"), "w"), ensure_ascii=False, indent=1)
    print("saved the read-only answers to", os.path.join(OUT, "probe.json"))
    for name, v in got.items(): print("*", name, "->", (json.dumps(v, ensure_ascii=False)[:160]))
