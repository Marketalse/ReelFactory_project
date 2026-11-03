"""QA critic (T134): a small vision model LOOKS at stills of the finished draft and scores it. Report only (it never changes the reel);
the scores and the issues with their times are saved to review/critic.json and shown in the report. Cheap: about 8 pictures, Haiku."""
import base64, subprocess

N_STILLS = 8
RUBRIC = ("readable", "layout", "consistency", "variety")

PROMPT = """You are the quality reviewer of a vertical (1080x1920) Arabic short video made by an automatic editor. Below are {n} still frames of the DRAFT, each preceded by its time.
Judge ONLY what you see. Return ONLY JSON:
{{"scores":{{"readable":<1-10: text is large, sharp, not clipped, not over the face>,"layout":<1-10: things sit inside the safe area, clear hierarchy, nothing overlapping badly>,"consistency":<1-10: same fonts, colours and style across frames>,"variety":<1-10: the frames show a real change of visuals, not the same plain talking head>}},
 "issues":[{{"t":<time in seconds of the frame>,"what":"<=18 words: a concrete visible problem"}}],
 "verdict":"<=20 words overall"}}
Be strict and honest. No issues = empty list."""


def pick_times(timeline, dur, n=N_STILLS):
    """Times to look at: the middle of each moment (at most n, spread out), topped up with evenly spaced times."""
    mids = sorted(round((s["t_in"] + s["t_out"]) / 2, 2) for s in (timeline or {}).get("scenes", []) if s.get("t_out", 0) > s.get("t_in", 0))
    if len(mids) > n: mids = [mids[int(i * len(mids) / n)] for i in range(n)]
    i = 0
    while len(mids) < n and dur > 1:
        mids.append(round(dur * (i + 0.5) / n, 2)); i += 1
    return sorted({min(max(t, 0.2), dur - 0.2) for t in mids})[:n]


def still_b64(video, t, width=540):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "4", "-f", "image2pipe", "-vcodec", "mjpeg", "-"], capture_output=True)
    return base64.b64encode(r.stdout).decode() if r.returncode == 0 and r.stdout else None


def content(video, times):
    """-> (vision request, times actually sent)."""
    parts, sent = [{"type": "text", "text": ""}], []
    for t in times:
        b = still_b64(video, t)
        if b:
            parts += [{"type": "text", "text": f"time {t:.1f}s"}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b}}]
            sent.append(t)
    parts[0]["text"] = PROMPT.format(n=len(sent))
    return parts, sent


def clean(ans):
    """Validate: scores 1-10 for each rubric item (average added), issues with a time and a short text."""
    if not isinstance(ans, dict) or not isinstance(ans.get("scores"), dict):
        raise ValueError("the critic answer has no scores")
    sc = {}
    for k in RUBRIC:
        try: v = float(ans["scores"][k])
        except (KeyError, TypeError, ValueError): raise ValueError(f"score '{k}' is missing")
        sc[k] = round(min(10.0, max(1.0, v)), 1)
    issues = []
    for i in (ans.get("issues") or [])[:8]:
        try: issues.append({"t": round(float(i["t"]), 1), "what": str(i["what"]).strip()[:140]})
        except (KeyError, TypeError, ValueError): continue
    return {"scores": sc, "average": round(sum(sc.values()) / len(sc), 1), "issues": issues, "verdict": str(ans.get("verdict") or "")[:160]}


def summary_lines(o):
    s = o["scores"]
    L = [f"Quality check (AI looked at {o.get('stills', '?')} stills): {o['average']}/10 - readable {s['readable']}, layout {s['layout']}, consistency {s['consistency']}, variety {s['variety']}"]
    if o.get("verdict"): L.append("  " + o["verdict"])
    L += [f"  {i['t']}s: {i['what']}" for i in o["issues"]]
    return L
