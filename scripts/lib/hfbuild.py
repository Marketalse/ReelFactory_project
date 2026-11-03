"""Builds HyperFrames projects from the approved blocks. Deterministic, no AI, standard library only.

Used by scripts/block_samples.py now and by scripts/compile.py later, so samples and real reels share one builder.
A block is stamped once per use: its host id, scene root id and timeline key are the same instance id
(HyperFrames requirement), and its values are passed as data-variable-values (editable in the desktop app).
"""
import html, json, os, re, shutil

from . import config as cfg

BLOCKS_DIR = os.path.join(cfg.ROOT, "templates", "blocks")
REGISTRY = json.load(open(os.path.join(BLOCKS_DIR, "registry.json"), encoding="utf-8"))
W, H = REGISTRY["canvas"]["width"], REGISTRY["canvas"]["height"]
ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,30}$")


class BuildError(Exception):
    """A plan value the builder refuses. The message names the bad field so the Director can repair it."""


def _num(x):
    return f"{float(x):.3f}".rstrip("0").rstrip(".")


def check_values(block, values, where):
    spec = REGISTRY["blocks"].get(block)
    if not spec:
        raise BuildError(f"{where}: unknown block '{block}'")
    for key, rule in spec["inputs"].items():
        if rule.get("type") == "generated":
            continue
        v = values.get(key, rule.get("default"))
        if rule.get("required") and (v is None or str(v).strip() == ""):
            raise BuildError(f"{where}: '{key}' is required for {block}")
        if v is None:
            continue
        if rule.get("maxLength") and len(str(v)) > rule["maxLength"]:
            raise BuildError(f"{where}: '{key}' is {len(str(v))} characters, max {rule['maxLength']} for {block}")
        if rule.get("type") == "number":
            if not isinstance(v, (int, float)):
                raise BuildError(f"{where}: '{key}' must be a number")
            if "min" in rule and v < rule["min"] or "max" in rule and v > rule["max"]:
                raise BuildError(f"{where}: '{key}'={v} outside {rule.get('min')}-{rule.get('max')}")
        if rule.get("type") == "enum" and v not in rule["options"]:
            raise BuildError(f"{where}: '{key}' must be one of {rule['options']}")
    unknown = set(values) - set(spec["inputs"])
    if unknown:
        raise BuildError(f"{where}: unknown field(s) {sorted(unknown)} for {block}")


FIT = {  # block -> {value: (largest px, smallest px)}: one-line text sized from its length to fit the 780 px text box
    "flash": {"word": (260, 90)},
    "split": {"value": (230, 96)},
    "number_graph": {"value": (230, 96)},
    "text_behind": {"text": (230, 80)},
}
GLYPH_EM = 0.62          # average Readex Pro bold glyph width in em (Arabic and digits), with margin


def fit_size(text, big, small, width=None):
    width = width or cfg.RULES["safe_zone"]["text_max_width"]
    n = max(1, len(str(text or "")))
    return int(max(small, min(big, width / (GLYPH_EM * n))))


MOTION_DIR = os.path.join(cfg.ROOT, "library", "assets", "motion")


def lottie_json(name, motion_dir=None):
    """The animation, as JSON text to put inside the scene file. Only a bare file name from library/assets/motion/ that passes the
    motion check again right now (no expressions, no internet links, a size that fits the safe zone). Anything else stops the build."""
    from . import motion_check
    d = motion_dir or MOTION_DIR
    f = os.path.basename(str(name or ""))
    if not f or f != name or not f.lower().endswith(".json"):
        raise BuildError(f"motion file {name!r}: give only a file name from library/assets/motion/")
    p = os.path.join(d, f)
    if not os.path.isfile(p):
        raise BuildError(f"motion file {f!r} is not in library/assets/motion/ (run scripts/asset_batch.py on your motion pack first)")
    rec = motion_check.check(p)
    if not rec["ok"]:
        raise BuildError(f"motion file {f!r} failed the motion check: {'; '.join(rec['problems'])[:160]}")
    return json.dumps(json.load(open(p, encoding="utf-8")), separators=(",", ":")).replace("</", "<\\/")


def stamp(block, inst_id, dur, groups_html="", values=None):
    """Return the scene file text for one use of a block."""
    if not ID_RE.match(inst_id):
        raise BuildError(f"bad instance id '{inst_id}' (lowercase letters, digits, _)")
    spec = REGISTRY["blocks"][block]
    src = open(os.path.join(BLOCKS_DIR, spec["file"]), encoding="utf-8").read()
    for key, (big, small) in FIT.get(block, {}).items():
        v = (values or {}).get(key) or spec["inputs"][key].get("default") or ""
        src = src.replace(f"__SIZE_{key}__", str(fit_size(v, big, small)))
    full = {k: v.get("default", "") for k, v in spec["inputs"].items()}
    full.update(values or {})
    for key, v in full.items():                                  # asset paths and numbers that must be in the file text itself (video src, positions)
        src = src.replace(f"__VAR_{key}__", html.escape(str(v if v is not None else ""), quote=True))
    if "__LOTTIE_JSON__" in src:
        src = src.replace("__LOTTIE_JSON__", lottie_json(full.get("motion")))
    return src.replace("__ID__", inst_id).replace("__DUR__", _num(dur)).replace("<!--GROUPS-->", groups_html)


def caption_events(words, t_offset=0.0, max_words=None, gap=0.15, hold=0.35, stops=()):
    """The ONE rule that decides how words become caption groups and when each group is on screen.
    Returns [{"idx": [word indices], "start", "end"}] in reel time. Used by the renderer and by the visual plan."""
    max_words = max_words or cfg.RULES["captions"]["max_words"]
    groups, cur = [], []
    for i, w in enumerate(words):
        if cur and (len(cur) >= max_words or w["start"] - words[cur[-1]]["end"] >= gap):
            groups.append(cur); cur = []
        cur.append(i)
    if cur:
        groups.append(cur)
    out = []
    for n, g in enumerate(groups):
        s = max(0.1, words[g[0]]["start"] - t_offset - 0.04)
        nxt = (words[groups[n + 1][0]]["start"] - t_offset - 0.04) if n + 1 < len(groups) else None
        e = words[g[-1]]["end"] - t_offset + hold
        if nxt is not None:
            e = min(e, nxt)
        e = max(e, s + 0.3)
        stop = min([t for t in stops if t > s + 1e-3], default=None)
        if stop is not None:
            e = min(e, stop)
        out.append({"idx": g, "start": s, "end": e})
    return out


def caption_groups(words, keyword_idx, inst_id, t_offset=0.0, max_words=None, gap=0.15, hold=0.35, stops=(), pill_idx=(), pill_style=""):
    """Group transcript words (reel time) into caption groups of up to max_words; returns HTML.
    words: [{"text","start","end"}] already on the reel timeline. keyword_idx: indices into words.
    stops: times where a full-screen card or the CTA begins; a caption never stays on screen past one."""
    kw = set(keyword_idx or []); pills = set(pill_idx or [])      # pills (T133): a highlight bar wipes in behind the word as it is said
    out = []
    for n, ev in enumerate(caption_events(words, t_offset, max_words, gap, hold, stops)):
        s, e, g = ev["start"], ev["end"], ev["idx"]
        spans = "".join(
            f'<span class="{inst_id}-w{" " + inst_id + "-kw" if i in kw else ""}{" " + inst_id + "-kwp" if i in pills else ""}"{f" style=\'{pill_style}\'" if i in pills and pill_style else ""} data-t="{_num(max(s, words[i]["start"] - t_offset))}">'
            f'{html.escape(words[i]["text"])}</span>' for i in g)
        out.append(f'  <div id="{inst_id}-g{n}" class="clip {inst_id}-g" data-start="{_num(s)}" data-duration="{_num(e - s)}">'
                   f'<div class="{inst_id}-pill">{spans}</div></div>')
    return "\n".join(out)


ROOT_TEMPLATE = """<!doctype html>
<html lang="ar">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width={W}, height={H}">
<script src="vendor/gsap.min.js"></script>
<script src="vendor/lottie_light.min.js"></script>
<style>
@font-face {{ font-family: "Readex Pro"; src: url("assets/fonts/ReadexPro.ttf"); font-weight: 160 700; }}
:root {{ {vars} }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ width: {W}px; height: {H}px; overflow: hidden; background: {page_bg}; }}
#root {{ position: relative; width: 100%; height: 100%; overflow: hidden; font-family: var(--font); }}
#face {{ position: absolute; inset: 0; transform-origin: 50% 38%; }}
#face video {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{dur}" data-width="{W}" data-height="{H}">
  <div id="face">
{videos}
  </div>
{hosts}
{audio}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{root_tweens}
window.__timelines["main"] = tl;
</script>
</body>
</html>
"""


def brand_vars():
    c = cfg.BRAND["colors"]
    pairs = {"bg": c["bg"], "lime": c["accent"], "violet": c["secondary"], "coral": c["negative"],
             "text": c["text"], "surface": c["surface"], "muted": c["muted"], "font": '"Readex Pro", sans-serif'}
    v = c["secondary"]                                           # Format Pack themes (T129), all derived from the brand colours
    pairs.update({"pk-d-bg": c["bg"], "pk-d-ac": c["accent"], "pk-d-on": c["bg"], "pk-d-sf": c["surface"], "pk-d-tx": c["text"],
                  "pk-v-bg": f"color-mix(in srgb, {v} 16%, black)", "pk-v-ac": f"color-mix(in srgb, {v} 55%, white)",
                  "pk-v-on": f"color-mix(in srgb, {v} 14%, black)", "pk-v-sf": f"color-mix(in srgb, {v} 28%, black)", "pk-v-tx": c["text"]})
    z = cfg.RULES["safe_zone"]
    W_, H_ = z["canvas"]
    pairs.update({"safe-top": f'{z["top"]}px', "safe-bottom": f'{H_ - z["bottom"]}px', "safe-left": f'{z["left"]}px',
                  "safe-right": f'{W_ - z["right"]}px', "text-x": f'{z["text_x"]}px', "text-w": f'{z["text_max_width"]}px',
                  "cap-top": f'{z["captions_y"][0]}px', "cap-h": f'{z["captions_y"][1] - z["captions_y"][0]}px',
                  "feed-top": f'{z["feed_square_y"][0]}px'})
    return " ".join(f"--{k}: {v};" for k, v in pairs.items())


def build_project(out_dir, *, duration, face_cuts, scenes, video_src, audio=None, transparent=False):
    """Write a complete HyperFrames project.
    face_cuts: [{"id","t_in","t_out","src_in","scale","cx","cy","y"}]  (y = vertical shift in px, e.g. 480 for split)
    scenes:    [{"id","block","t_in","t_out","values", "groups_html"?}]
    video_src: path to proxy.mp4 (copied/linked into assets/)."""
    os.makedirs(os.path.join(out_dir, "compositions"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "assets", "fonts"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "vendor"), exist_ok=True)
    fonts = [f for f in os.listdir(os.path.join(cfg.ROOT, "style", "fonts")) if f.lower().endswith(".ttf")]
    if not fonts:
        raise BuildError("no .ttf font in style/fonts")
    shutil.copy(os.path.join(cfg.ROOT, "style", "fonts", fonts[0]), os.path.join(out_dir, "assets", "fonts", "ReadexPro.ttf"))
    shutil.copy(os.path.join(cfg.ROOT, "templates", "vendor", "gsap.min.js"), os.path.join(out_dir, "vendor", "gsap.min.js"))
    shutil.copy(os.path.join(cfg.ROOT, "templates", "vendor", "lottie_light.min.js"), os.path.join(out_dir, "vendor", "lottie_light.min.js"))
    vid = os.path.join(out_dir, "assets", "proxy.mp4")
    if face_cuts and not os.path.exists(vid):
        try:
            os.link(video_src, vid)
        except OSError:
            shutil.copy(video_src, vid)

    videos, tweens, hosts = [], [], []
    for n, f in enumerate(face_cuts):
        d = f["t_out"] - f["t_in"]
        if d < 0.3 - 1e-3:
            raise BuildError(f"{f['id']}: face cut shorter than 0.3 s")
        videos.append(f'    <video id="{f["id"]}" class="clip" src="assets/proxy.mp4" data-start="{_num(f["t_in"])}" '
                      f'data-duration="{_num(d)}" data-media-start="{_num(f["src_in"])}" '
                      f'data-has-audio="true" data-track-index="0" playsinline></video>')
        sc, cx, cy, y = f.get("scale", 1.0), f.get("cx", 0.5), f.get("cy", 0.38), f.get("y", 0)
        state = f'scale: {sc}, x: {_num((0.5 - cx) * W * (sc - 1))}, y: {_num(y + (0.38 - cy) * H * (sc - 1))}'
        prev = face_cuts[n - 1] if n else None
        same_take = bool(prev) and abs(prev["src_in"] + (prev["t_out"] - prev["t_in"]) - f["src_in"]) < 0.05 and (sc, y) != (prev.get("scale", 1.0), prev.get("y", 0))
        if same_take and sc != 1.0 or same_take and prev.get("scale", 1.0) != 1.0:
            # a zoom inside one continuous take SNAPS (a fast ease, like an editor's keyframe) instead of jumping; a real cut stays instant
            d = 0.14 if sc > prev.get("scale", 1.0) else 0.2
            tweens.append(f'tl.to("#face", {{ {state}, duration: {d}, ease: "power2.out" }}, {_num(f["t_in"])});')
        else:                                                   # a cut is instant: set the frame for this segment exactly at its start
            tweens.append(f'tl.set("#face", {{ {state} }}, {_num(f["t_in"])});')

    for s in scenes:
        check_values(s["block"], s.get("values", {}), s["id"])
        spec = REGISTRY["blocks"][s["block"]]
        d = s["t_out"] - s["t_in"]
        text = stamp(s["block"], s["id"], d, s.get("groups_html", ""), s.get("values"))
        open(os.path.join(out_dir, "compositions", s["id"] + ".html"), "w", encoding="utf-8").write(text)
        full = {k: v.get("default", "") for k, v in spec["inputs"].items() if v.get("type") != "generated"}
        full.update(s.get("values", {}))
        vals = html.escape(json.dumps(full, ensure_ascii=False), quote=True)
        kind = spec.get("track_kind", "graphics")
        hosts.append(f'  <div id="{s["id"]}" class="clip" data-composition-id="{s["id"]}" '
                     f'data-composition-src="compositions/{s["id"]}.html" data-start="{_num(s["t_in"])}" '
                     f'data-duration="{_num(d)}" data-width="{W}" data-height="{H}" data-track-kind="{kind}" '
                     f'style="z-index:{spec["layer"]}" data-variable-values="{vals}"></div>')

    audio_html = ""
    if audio:
        audio_html = "\n".join(f'  <audio id="{a["id"]}" class="clip" src="{a["src"]}" data-start="{_num(a["t_in"])}" '
                               f'data-duration="{_num(a["dur"])}" data-volume="{a.get("volume", 1)}"></audio>' for a in audio)
    page = ROOT_TEMPLATE.format(W=W, H=H, vars=brand_vars(), page_bg="transparent" if transparent else "var(--bg)", dur=_num(duration), videos="\n".join(videos),
                                hosts="\n".join(hosts), audio=audio_html, root_tweens="\n".join(tweens))
    open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8").write(page)
    json.dump({"id": os.path.basename(out_dir.rstrip("/")), "name": os.path.basename(out_dir.rstrip("/"))},
              open(os.path.join(out_dir, "meta.json"), "w"))
    json.dump({"paths": {"blocks": "compositions", "assets": "assets"}, "media": {"autoProxy": False}},
              open(os.path.join(out_dir, "hyperframes.json"), "w"), indent=1)
    return os.path.join(out_dir, "index.html")
