#!/usr/bin/env python3
"""PHASE 1 PILOT for the Instagram Edits desktop Automation server: ANALYSIS ONLY, on a NEW throwaway project. Free, no AI of ours.
    python3 scripts/edits_pilot.py "/path/to/clip.MOV"        (drag the clip into Terminal to paste its path)
What it does, step by step (each step prints what Edits answered, errors included, and the log is saved to ~/.reelfactory/edits/pilot.json):
  1 makes a NEW project called "RF pilot ..." (your other projects are never opened)   2 adds your clip   3 asks Edits for the Arabic words with times
  4 finds the pauses   5 finds the face/person boxes   6 asks SAM 3 for the person's masks   7 asks for automatic captions in Arabic   8 saves the project.
SAFETY: only the tool names in ALLOWED can be called (nothing that deletes, closes, opens another project, posts, taps or types); no export; the token is
asked hidden and never printed or saved. When done, you can delete the "RF pilot" project by hand in Edits."""
import getpass, json, os, sys, time, urllib.error, urllib.request

ALLOWED = ("newProject", "setTitle", "setCanvas", "getCanvas", "addMedia", "importToMediaBin", "addLibraryMedia", "mediaBin", "elements", "clips", "probeMedia",
           "transcribeClip", "findPauses", "detectSubjects", "trackObject", "generateCaptions", "captions", "saveProject", "jobStatus", "state", "appState")
URL = os.environ.get("EDITS_URL", "http://127.0.0.1:19501/mcp")
OUT = os.path.expanduser("~/.reelfactory/edits")
LOG = []


class Edits:
    def __init__(self, token):
        self.h = {"Authorization": "Bearer " + token, "Content-Type": "application/json", "Accept": "application/json, text/event-stream"}; self.sid = None; self.n = 0

    def rpc(self, method, params=None, note=False):
        self.n += 1; body = {"jsonrpc": "2.0", "method": method}
        if not note: body["id"] = self.n
        if params is not None: body["params"] = params
        h = dict(self.h)
        if self.sid: h["Mcp-Session-Id"] = self.sid
        r = urllib.request.urlopen(urllib.request.Request(URL, json.dumps(body).encode(), h), timeout=600)
        txt = r.read().decode(); self.sid = r.headers.get("Mcp-Session-Id") or self.sid
        for line in txt.splitlines():
            line = line.strip()
            if line.startswith("data:"): line = line[5:].strip()
            if line.startswith("{"): return json.loads(line)
        return json.loads(txt) if txt.strip().startswith("{") else {}

    def start(self):
        self.rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "rf-pilot", "version": "1"}})
        self.rpc("notifications/initialized", note=True)

    def call(self, name, args=None, label=""):
        """-> (ok, data). data = parsed JSON from the tool's text when possible, else the text. Only ALLOWED tools can be called."""
        if name not in ALLOWED: raise SystemExit(f"refused: {name} is not an allowed pilot tool")
        t0 = time.time()
        try: res = self.rpc("tools/call", {"name": name, "arguments": args or {}})
        except (urllib.error.HTTPError, OSError) as e: ok, data = False, f"{type(e).__name__}: {e}"
        else:
            r = res.get("result") or {}; txt = "".join(c.get("text", "") for c in r.get("content", []) if isinstance(c, dict))
            try: data = json.loads(txt)
            except ValueError: data = txt or res.get("error")
            ok = not r.get("isError") and not res.get("error") and not (isinstance(data, dict) and data.get("ok") is False)
        LOG.append({"step": label or name, "tool": name, "args": args, "ok": ok, "seconds": round(time.time() - t0, 1), "answer": data})
        short = json.dumps(data, ensure_ascii=False)[:420]
        print(f"  [{'ok' if ok else 'ERROR'}] {name}({json.dumps(args, ensure_ascii=False)[:120] if args else ''}) {round(time.time() - t0, 1)}s -> {short}")
        return ok, data


def first(d, *keys):
    for k in keys:
        if isinstance(d, dict) and k in d: return d[k]
    return None


def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    clip = sys.argv[1].strip().strip("'\"").replace("\\ ", " ")
    if not os.path.exists(clip): sys.exit(f"I can't find the clip: {clip}")
    token = os.environ.get("EDITS_TOKEN", "").strip() or getpass.getpass("Paste the Edits access token (nothing shows while you paste), then press Enter: ").strip()
    ed = Edits(token)
    try: ed.start()
    except urllib.error.HTTPError as e: sys.exit(f"Edits answered HTTP {e.code} (401 = wrong token). Is Edits open with the Automation Server on?")
    except OSError as e: sys.exit(f"Could not reach Edits: {e}")
    print("1. new project"); ed.call("newProject", {}, "new project"); ed.call("setTitle", {"title": "RF pilot " + time.strftime("%H:%M")}, "title")
    ed.call("setCanvas", {"aspect": "9:16", "frameRate": 30}, "canvas")
    print("2. add the clip")
    ok, _ = ed.call("addMedia", {"path": clip, "audioKind": "main"}, "add clip")
    if not ok: ok, _ = ed.call("importToMediaBin", {"path": clip}, "import (fallback)"); ok and ed.call("mediaBin", {}, "media bin")
    ok, els = ed.call("elements", {}, "elements")
    items = first(els, "elements", "items") or []
    vid = next((e for e in items if isinstance(e, dict) and "video" in json.dumps(e).lower()), (items[0] if items else {}))
    cid = first(vid, "id", "uuid"); dur = first(vid, "duration") or 18.0
    print("   clip element id:", cid, "duration:", dur)
    if cid:
        print("3. Arabic words with times"); ed.call("transcribeClip", {"id": cid, "language": "ar", "mergeSplitWords": True}, "transcribe ar")
        print("4. pauses"); ed.call("findPauses", {"id": cid, "path": clip, "start": 0, "duration": dur, "minDuration": 0.35, "thresholdDb": -40}, "pauses")
        print("5. faces and people"); ed.call("detectSubjects", {"id": cid, "sampleEvery": 1.0}, "subjects")
        print("6. person masks (SAM 3)"); ed.call("trackObject", {"id": cid, "prompt": "person", "sampleEvery": 0.5, "saveMasks": True}, "masks")
        print("7. automatic captions, Arabic"); ed.call("generateCaptions", {"source": "composition", "language": "ar", "curseWords": False}, "captions ar"); ed.call("captions", {}, "captions list")
    print("8. save"); ed.call("saveProject", {}, "save")
    os.makedirs(OUT, exist_ok=True); json.dump(LOG, open(os.path.join(OUT, "pilot.json"), "w"), ensure_ascii=False, indent=1)
    bad = [s["step"] for s in LOG if not s["ok"]]
    print("\nDone. Saved:", os.path.join(OUT, "pilot.json"), "| steps with an error:", bad or "none")
    print("Send me that file. You can delete the 'RF pilot' project by hand in Edits.")


if __name__ == "__main__":
    main()
