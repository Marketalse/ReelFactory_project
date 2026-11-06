#!/usr/bin/env python3
"""PHASE 1 PILOT for the Instagram Edits desktop Automation server: ANALYSIS ONLY, on a NEW throwaway project. Free, no AI of ours.
    python3 scripts/edits_pilot.py "/path/to/clip.MOV"        (drag the clip into Terminal to paste its path)
What it does, step by step (each step prints what Edits answered, errors included, and the log is saved to ~/.reelfactory/edits/pilot.json):
  PHASE 1b (default now; add --full to also repeat the words and the face boxes): pauses at three thresholds, SAM 3 masks (waits for the job), Arabic captions with a
  word-highlight style, and saves 4 rendered frames as pictures in ~/.reelfactory/edits/frames/ so you can look at the Arabic captions.
  1 makes a NEW project called "RF pilot ..." (your other projects are never opened)   2 adds your clip   3 asks Edits for the Arabic words with times
  4 finds the pauses   5 finds the face/person boxes   6 asks SAM 3 for the person's masks   7 asks for automatic captions in Arabic   8 saves the project.
SAFETY: only the tool names in ALLOWED can be called (nothing that deletes, closes, opens another project, posts, taps or types); no export; the token is
asked hidden and never printed or saved. When done, you can delete the "RF pilot" project by hand in Edits."""
import getpass, json, os, sys, time, urllib.error, urllib.request

ALLOWED = ("newProject", "setTitle", "setCanvas", "getCanvas", "importMedia", "importToMediaBin", "addLibraryMedia", "mediaBin", "elements", "clips", "probeMedia",
           "transcribeClip", "findPauses", "detectSubjects", "trackObject", "generateCaptions", "captions", "setCaptionStyle", "captureFrame", "saveProject", "jobStatus", "state", "appState")
URL = os.environ.get("EDITS_URL", "http://127.0.0.1:19501/mcp")
OUT = os.path.expanduser("~/.reelfactory/edits")
LOG = []


class Edits:
    def __init__(self, token, allowed=None):
        self.allowed = tuple(allowed or ALLOWED)
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
        if name not in self.allowed: raise SystemExit(f"refused: {name} is not an allowed pilot tool")
        t0 = time.time()
        try: res = self.rpc("tools/call", {"name": name, "arguments": args or {}})
        except (urllib.error.HTTPError, OSError) as e: ok, data = False, f"{type(e).__name__}: {e}"
        else:
            r = res.get("result") or {}; txt = "".join(c.get("text", "") for c in r.get("content", []) if isinstance(c, dict))
            try: data = json.loads(txt)
            except ValueError: data = txt or res.get("error")
            ok = not r.get("isError") and not res.get("error") and not (isinstance(data, dict) and data.get("ok") is False)
            imgs = [c["data"] for c in r.get("content", []) if isinstance(c, dict) and c.get("type") == "image" and isinstance(c.get("data"), str)]
            if imgs: data = {"result": data, "images": imgs}                  # pictures the tool returned as image parts
        logged = _strip(data)                                                  # pictures are saved as files, never printed or kept in the log
        LOG.append({"step": label or name, "tool": name, "args": args, "ok": ok, "seconds": round(time.time() - t0, 1), "answer": logged})
        short = json.dumps(logged, ensure_ascii=False)[:420]
        print(f"  [{'ok' if ok else 'ERROR'}] {name}({json.dumps(args, ensure_ascii=False)[:120] if args else ''}) {round(time.time() - t0, 1)}s -> {short}")
        return ok, data


def _strip(o):
    if isinstance(o, str) and len(o) > 500 and (o.startswith("/9j/") or o.startswith("iVBOR")): return f"<picture, {len(o)} chars>"
    if isinstance(o, dict): return {k: _strip(v) for k, v in o.items()}
    if isinstance(o, list): return [_strip(v) for v in o]
    return o


def _b64s(o, found):
    """Collect base64 pictures (JPEG '/9j/' or PNG 'iVBOR') anywhere inside an answer."""
    if isinstance(o, str):
        if len(o) > 500 and (o.startswith("/9j/") or o.startswith("iVBOR")): found.append(o)
    elif isinstance(o, dict):
        for v in o.values(): _b64s(v, found)
    elif isinstance(o, list):
        for v in o: _b64s(v, found)


def save_images(answer):
    import base64
    found = []; _b64s(answer, found)
    os.makedirs(os.path.join(OUT, "frames"), exist_ok=True)
    for i, b in enumerate(found):
        open(os.path.join(OUT, "frames", f"frame_{i + 1}.{'png' if b.startswith('iVBOR') else 'jpg'}"), "wb").write(base64.b64decode(b))
    return len(found)


def first(d, *keys):
    for k in keys:
        if isinstance(d, dict) and k in d: return d[k]
    return None


def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    clip = sys.argv[1].strip().strip("'\"").replace("\\ ", " ")
    if not os.path.exists(clip): sys.exit(f"I can't find the clip: {clip}")
    movies = os.path.expanduser("~/Movies")
    if not os.path.abspath(clip).startswith(movies + os.sep):          # Edits is not allowed to read Downloads/Desktop/Documents: work on a COPY in ~/Movies (the original is never touched)
        import shutil
        os.makedirs(movies, exist_ok=True); copy = os.path.join(movies, "RF_pilot_" + os.path.basename(clip))
        if not os.path.exists(copy):
            print("copying the clip to", copy, "so Edits is allowed to read it (your original stays where it is)..."); shutil.copy2(clip, copy)
        clip = copy
    token = os.environ.get("EDITS_TOKEN", "").strip() or getpass.getpass("Paste the Edits access token (nothing shows while you paste), then press Enter: ").strip()
    ed = Edits(token)
    try: ed.start()
    except urllib.error.HTTPError as e: sys.exit(f"Edits answered HTTP {e.code} (401 = wrong token). Is Edits open with the Automation Server on?")
    except OSError as e: sys.exit(f"Could not reach Edits: {e}")
    print("1. new project"); ed.call("newProject", {}, "new project"); ed.call("setTitle", {"name": "RF pilot " + time.strftime("%H:%M")}, "title")
    ed.call("setCanvas", {"aspect": "9:16", "frameRate": 30}, "canvas")
    print("2. add the clip")
    ok, _ = ed.call("importMedia", {"path": clip}, "add clip")
    ok, els = ed.call("elements", {}, "elements")
    if not (first(els, "elements", "items") or []):                       # not on the timeline yet: take it from the media bin
        ok, mb = ed.call("mediaBin", {}, "media bin")
        ids = [first(a, "aliasId", "id") for a in (first(mb, "assets", "items", "media") or []) if isinstance(a, dict)]
        ids = [i for i in ids if i]
        if ids: ed.call("addLibraryMedia", {"ids": ids[:1]}, "put it on the timeline")
        ok, els = ed.call("elements", {}, "elements")
    items = first(els, "elements", "items") or []
    vid = next((e for e in items if isinstance(e, dict) and "video" in json.dumps(e).lower()), (items[0] if items else {}))
    cid = first(vid, "id", "uuid"); dur = first(vid, "duration") or 18.0
    print("   clip element id:", cid, "duration:", dur)
    if cid:
        full = "--full" in sys.argv
        if full:
            print("3. Arabic words with times"); ed.call("transcribeClip", {"id": cid, "language": "ar", "mergeSplitWords": True}, "transcribe ar")
            print("5. faces and people"); ed.call("detectSubjects", {"id": cid, "sampleEvery": 1.0}, "subjects")
        print("4. pauses at three thresholds (a noisy car needs a higher one)")
        for db in (-40, -30, -25): ed.call("findPauses", {"id": cid, "path": clip, "start": 0, "duration": dur, "minDuration": 0.35, "thresholdDb": db}, f"pauses {db} dB")
        print("6. person masks (SAM 3): the job runs in the background, waiting for it (up to about 4 minutes)")
        ok, job = ed.call("trackObject", {"id": cid, "prompt": "person", "sampleEvery": 0.5, "saveMasks": True}, "masks")
        jid = first(job, "jobId")
        for _ in range(12):
            if not jid or not (isinstance(job, dict) and job.get("status") == "running"): break
            ok, job = ed.call("jobStatus", {"id": jid}, "mask job")
        print("7. automatic captions, Arabic")
        ok, _ = ed.call("generateCaptions", {"source": "video", "language": "ar", "curseWords": False}, "captions ar")
        ed.call("captions", {}, "captions list")
        ed.call("setCaptionStyle", {"style": "Word Highlight"}, "caption style")
        print("   looking at 4 frames of the result")
        ok, fr = ed.call("captureFrame", {"times": "2,6,10,15", "maxWidth": 720}, "frames")
        n = save_images(fr)
        print("   saved", n, "picture(s) to", os.path.join(OUT, "frames"))
    print("8. save"); ed.call("saveProject", {}, "save")
    os.makedirs(OUT, exist_ok=True); json.dump(LOG, open(os.path.join(OUT, "pilot.json"), "w"), ensure_ascii=False, indent=1)
    bad = [s["step"] for s in LOG if not s["ok"]]
    print("\nDone. Saved:", os.path.join(OUT, "pilot.json"), "| steps with an error:", bad or "none")
    print("Send me that file. You can delete the 'RF pilot' project by hand in Edits.")


if __name__ == "__main__":
    main()
