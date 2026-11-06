#!/usr/bin/env python3
"""PHASE 2a PILOT for Instagram Edits: the FINISHING flow on a NEW throwaway project (Reel Factory cuts and plans, Edits finishes). Free.
    python3 scripts/edits_pilot2.py "/path/to/clip.MOV"
Steps: new project + clip -> Arabic captions -> our English-in-Latin-letters fix (call center, lead, follow up, caption...) applied to the captions ->
our highlighted key words -> a royalty-free music track -> 2 rendered frames saved as pictures -> EXPORT to ~/Movies/RF_pilot_export.mp4 (a file on your Mac; nothing is posted).
SAFETY: a fixed allowlist (ALLOWED2: nothing that deletes, closes, opens another project, posts, taps or types); the token is asked hidden, never printed or saved.
The log goes to ~/.reelfactory/edits/pilot2.json; pictures to ~/.reelfactory/edits/frames2/. You can delete the "RF pilot 2" project by hand in Edits afterwards."""
import getpass, json, os, shutil, sys, time, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import edits_pilot as ep

ALLOWED2 = ("newProject", "setTitle", "setCanvas", "importMedia", "elements", "generateCaptions", "captions", "setCaptionStyle", "editCaption", "setCaptionHighlights",
            "setCaptionHighlightColor", "listMusicTracks", "searchMusic", "getMusicTrackDetails", "addSongToComposition", "addMusicTrack", "captureFrame",
            "setExportSettings", "export", "exportStatus", "saveProject", "jobStatus", "state", "appState")
GLOSSARY = {"كول سنتر": "call center", "كابشن": "caption", "فولو اب": "follow up", "ليد": "lead", "الماركتينج": "marketing", "البروسيس": "process", "ماركتينج": "marketing",
            "الريل فاكتوري": "Reel Factory", "بروجكت": "project", "فيديو تيست": "video test"}      # the kind of fix our glossary does (his English words in Latin letters)
KEY_WORDS = ("تسويق", "بزنس", "التسويق", "المبيعات")                                              # stand-in for the key words our editor highlights


def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    clip = sys.argv[1].strip().strip("'\"").replace("\\ ", " ")
    if not os.path.exists(clip): sys.exit(f"I can't find the clip: {clip}")
    movies = os.path.expanduser("~/Movies"); os.makedirs(movies, exist_ok=True)
    if not os.path.abspath(clip).startswith(movies + os.sep):
        copy = os.path.join(movies, "RF_pilot_" + os.path.basename(clip))
        if not os.path.exists(copy): print("copying the clip to", copy, "(your original stays where it is)..."); shutil.copy2(clip, copy)
        clip = copy
    token = os.environ.get("EDITS_TOKEN", "").strip() or getpass.getpass("Paste the Edits access token (nothing shows while you paste), then press Enter: ").strip()
    ed = ep.Edits(token, ALLOWED2)
    try: ed.start()
    except urllib.error.HTTPError as e: sys.exit(f"Edits answered HTTP {e.code} (401 = wrong token). Is Edits open with the Automation Server on?")
    except OSError as e: sys.exit(f"Could not reach Edits: {e}")
    print("1. new project and clip"); ed.call("newProject", {}, "new project"); ed.call("setTitle", {"name": "RF pilot 2 " + time.strftime("%H:%M")}, "title")
    ed.call("setCanvas", {"aspect": "9:16", "frameRate": 30}, "canvas"); ed.call("importMedia", {"path": clip}, "add clip")
    print("2. Arabic captions"); ok, _ = ed.call("generateCaptions", {"source": "video", "language": "ar", "curseWords": False}, "captions ar")
    ed.call("setCaptionStyle", {"style": "Word Highlight"}, "caption style")
    ok, cap = ed.call("captions", {}, "captions list"); caps = ep.first(cap, "captions") or []
    print(f"   {len(caps)} captions")
    print("3. our fixes: his English words in Latin letters, and our highlighted key words")
    fixed = hi = 0
    for c in caps:
        txt = c.get("text") or ""; new = txt
        for ar, en in GLOSSARY.items(): new = new.replace(ar, en)
        if new != txt:
            ok, _ = ed.call("editCaption", {"id": c["id"], "text": new}, "fix words"); fixed += ok
            print(f"      {txt}  =>  {new}")
        words = [w for w in KEY_WORDS if w in new]
        if words:
            ok, _ = ed.call("setCaptionHighlights", {"id": c["id"], "words": " ".join(words)}, "highlight"); hi += ok
    print(f"   fixed {fixed} captions, highlighted words in {hi}")
    print("4. a royalty-free music track")
    ok, mus = ed.call("listMusicTracks", {"query": "calm", "tab": "", "license": "royaltyFree"}, "find music")
    tracks = ep.first(mus, "tracks", "items", "results") or []
    if tracks and isinstance(tracks[0], dict):
        t0 = tracks[0]; print("   first track:", {k: t0.get(k) for k in ("id", "title", "artist", "license") if k in t0})
        ed.call("addSongToComposition", {"track": t0.get("title") or t0.get("id"), "audioAssetId": t0.get("audioAssetId") or t0.get("id") or ""}, "add music")
    print("5. look at the result"); ok, fr = ed.call("captureFrame", {"times": "10,45", "maxWidth": 720}, "frames")
    ep.OUT_FRAMES = os.path.join(ep.OUT, "frames2"); n = save_frames(fr); print("   saved", n, "picture(s) to", ep.OUT_FRAMES)
    print("6. export to a file (nothing is posted)")
    out = os.path.join(movies, "RF_pilot_export.mp4"); ok, _ = ed.call("export", {"path": out}, "export")
    if ok:
        for _ in range(60):
            ok, st = ed.call("exportStatus", {}, "export status")
            s = json.dumps(st).lower()
            if "complete" in s or "done" in s or "finished" in s or '"idle"' in s: break
            time.sleep(10)
        if os.path.exists(out): print("   exported:", out, round(os.path.getsize(out) / 1e6, 1), "MB")
    ed.call("saveProject", {}, "save")
    os.makedirs(ep.OUT, exist_ok=True); json.dump(ep.LOG, open(os.path.join(ep.OUT, "pilot2.json"), "w"), ensure_ascii=False, indent=1)
    print("\nDone. Saved:", os.path.join(ep.OUT, "pilot2.json"), "| steps with an error:", [s["step"] for s in ep.LOG if not s["ok"]] or "none")


def save_frames(answer):
    import base64
    found = []; ep._b64s(answer, found); os.makedirs(ep.OUT_FRAMES, exist_ok=True)
    for i, b in enumerate(found): open(os.path.join(ep.OUT_FRAMES, f"frame_{i + 1}.{'png' if b.startswith('iVBOR') else 'jpg'}"), "wb").write(base64.b64decode(b))
    return len(found)


if __name__ == "__main__":
    main()
