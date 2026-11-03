"""FORMAT PACK (T129): one designed frame for the whole reel instead of loose cards. Free, no AI: it is built from the OUTLINE step's
sections (titles are his own words) and the bundled icons. Layout (1080x1920, all text inside the safe zone):
  header pills (series, presenter)  y 268-332
  face window                       y 380-1100  (the talking head, framed)
  bottom panel                      y 1128-1500: progress bar, STEP n/N, icon, section title; the captions sit inside it (y 1200-1450)
  recap chain                       over the face window in the last seconds (numbered steps connected by a line)
The compiler swaps the director's loose cards for these two blocks when the pack is active."""
import html, json, os

from . import broll, config as cfg, hfbuild

WIN = (108, 380, 920, 1100)            # x0, y0, x1, y1 of the face window
FALLBACK = {"step": "icon-arrow-right.svg", "point": "icon-lightbulb.svg", "proof": "icon-chart-bar.svg", "turn": "icon-repeat.svg"}
RECAP_LEN = 3.4


def conf():
    return cfg.PROJECT.get("format_pack", {})


def active(outline, c=None):
    """Should this reel use the pack? mode off = never; always = whenever there is an outline; auto = explainer/tips with enough sections."""
    c = c or conf()
    mode = c.get("mode", "auto")
    if mode == "off" or not outline or not outline.get("sections"):
        return False
    if len(outline["sections"]) < int(c.get("min_sections", 3)) and mode != "always":
        return False
    return mode == "always" or outline.get("format") in c.get("formats", ["explainer", "tips"])


def pick_icons(outline, words, root=None):
    """One bundled icon per section: the best name/tag match for what he says in it, else a neutral one for its kind. Never twice the same
    while another choice exists. -> [file or None]."""
    idx = [i for i in broll.index(root) if i["file"].startswith("icon-")]
    have = {i["file"] for i in idx}
    used, out = set(), []
    for s in outline["sections"]:
        seg = words[s["from_word"]:s["to_word"] + 1]
        hits = [h for h in broll.suggest(seg, idx) if h["file"] not in used]
        hits.sort(key=lambda h: ("exact contains prefix close".split().index(h["kind"]), h["t"]))
        f = hits[0]["file"] if hits else FALLBACK.get(s.get("kind"), FALLBACK["point"])
        if f not in have: f = None
        if f: used.add(f)
        out.append(f)
    return out


def highlight_idx(outline, words, keyword_ids=()):
    """Which spoken words get the highlight bar: up to 2 per section, inside the section's title (his words): the director's keywords
    first, then the longest words. -> set of edl word indices."""
    kw, out = set(keyword_ids or ()), set()
    for s in outline["sections"]:
        ids = [i for i in range(s["title_from"], s["title_to"] + 1) if len(words[i]["text"].strip(" ،,.!؟?")) >= 3]
        ids.sort(key=lambda i: (i not in kw, -len(words[i]["text"])))
        out.update(ids[:2])
    return out


def pill_style(theme):
    st = theme_style()
    if st:
        k = conf()["colors"]; return f"--kw-bg:{k['accent']};--kw-fg:{k['on']}"
    return "--kw-bg:var(--pk-v-ac);--kw-fg:var(--pk-v-on)" if theme == "violet" else "--kw-bg:var(--pk-d-ac);--kw-fg:var(--pk-d-on)"


def theme_style(c=None):
    """Inline colour variables for the 'custom' theme (colours learned from a reference video, T135); '' for the built-in themes."""
    c = c or conf()
    if c.get("theme") != "custom": return ""
    k = c.get("colors") or {}
    need = ("bg", "accent", "surface", "text", "on")
    if not all(re_hex.match(str(k.get(x, ""))) for x in need): return ""
    return f'--pk-bg:{k["bg"]};--pk-ac:{k["accent"]};--pk-sf:{k["surface"]};--pk-tx:{k["text"]};--pk-on:{k["on"]}'


import re
re_hex = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _e(s): return html.escape(str(s), quote=True)


def frame_groups(inst, outline, duration, icons, theme="dark", series="", presenter=""):
    n = len(outline["sections"]); x0, y0, x1, y1 = WIN
    r = 44
    path = (f"M0 0H1080V1920H0Z M{x0 + r} {y0}H{x1 - r}A{r} {r} 0 0 1 {x1} {y0 + r}V{y1 - r}A{r} {r} 0 0 1 {x1 - r} {y1}H{x0 + r}"
            f"A{r} {r} 0 0 1 {x0} {y1 - r}V{y0 + r}A{r} {r} 0 0 1 {x0 + r} {y0}Z")
    steps = []
    for k, s in enumerate(outline["sections"]):
        a = 0.0 if k == 0 else s["t_in"]
        b = duration if k == n - 1 else outline["sections"][k + 1]["t_in"]
        size = hfbuild.fit_size(s["title"], 46, 30, width=470)
        img = f'<img src="assets/icons/{_e(icons[k])}" alt="">' if icons[k] else ""
        steps.append(f'<div id="{inst}-s{k + 1}" class="{inst}-s" data-from="{a:.2f}" data-to="{b:.2f}">{img}<span class="{inst}-lab">STEP {k + 1}/{n}</span>'
                     f'<span class="{inst}-ttl" style="font-size:{size}px">{_e(s["title"])}</span></div>')
    pills = ""
    if series: pills += f'<div class="{inst}-pill" id="{inst}-series">{_e(series)}</div>'
    if presenter: pills += f'<div class="{inst}-pill" id="{inst}-who">{_e(presenter)}</div>'
    return (f'<div id="{inst}-wrap" class="{inst}-{_e(theme if theme in ("dark", "violet") else "dark")}" style="{theme_style()}"><svg id="{inst}-bg" viewBox="0 0 1080 1920"><path fill-rule="evenodd" style="fill:var(--pk-bg)" d="{path}"/></svg>'
            f'<div id="{inst}-glow"></div>{pills}<div id="{inst}-panel"></div>'
            f'<div id="{inst}-prog">{"<i></i>" * n}</div>{"".join(steps)}</div>')


BUTTON_ICONS = ("icon-thumbs-up.svg", "icon-play.svg", "icon-users.svg")        # like, subscribe, follow


def recap_groups(inst, outline, icons, theme="dark", buttons=()):
    """buttons: up to 3 labels (like / subscribe / follow); shown under the chain, only when the chain has at most 4 rows (room)."""
    n = len(outline["sections"]); top, bottom = 486, 1070
    buttons = list(buttons)[:3] if n <= 4 else []
    pitch = min(100 if buttons else 124, (bottom - top) / n)
    rows, links = [], []
    for k, s in enumerate(outline["sections"]):
        y = int(top + k * pitch)
        size = hfbuild.fit_size(s["title"], 44, 28, width=520)
        img = f'<img src="assets/icons/{_e(icons[k])}" alt="">' if icons[k] else ""
        rows.append(f'<div class="{inst}-row" style="top:{y}px;height:58px"><span class="{inst}-num">{k + 1}</span>{img}'
                    f'<span class="{inst}-name" style="font-size:{size}px">{_e(s["title"])}</span></div>')
        if k < n - 1:
            links.append(f'<div class="{inst}-link" style="top:{y + 58}px;height:{int(pitch - 58)}px"></div>')
    btns = "".join(f'<div class="{inst}-btn" style="left:{140 + k * 256}px"><img src="assets/icons/{BUTTON_ICONS[k]}" alt=""><span>{_e(t)}</span></div>' for k, t in enumerate(buttons))
    return (f'<div id="{inst}-wrap" class="{inst}-{_e(theme if theme in ("dark", "violet") else "dark")}" style="{theme_style()}"><div id="{inst}-panel"></div><div id="{inst}-head">RECAP</div>'
            f'{"".join(links)}{"".join(rows)}{btns}</div>')


def plan(job, tl, edl, root=None):
    """-> {"scenes": [...], "icons": [files]} for the compiler, or None when the pack is not active for this reel."""
    try:
        outline = json.load(open(os.path.join(job, "outline.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not active(outline): return None
    c = conf(); theme = c.get("theme", "dark") if c.get("theme") in ("dark", "violet", "custom") else "dark"
    dur = tl["duration"]; words = edl["words"]
    icons = pick_icons(outline, words, root)
    scenes = [{"id": "pk", "block": "pack_frame", "t_in": 0.0, "t_out": dur,
               "values": {"theme": theme, "series": c.get("series", ""), "presenter": c.get("presenter", "")},
               "groups_html": frame_groups("pk", outline, dur, icons, theme, c.get("series", ""), c.get("presenter", ""))}]
    buttons = c.get("closing_labels", ["لايك", "اشتراك", "تابعني"]) if c.get("closing_buttons", False) else []     # OFF by default: the project rule keeps the call to action off
    last = outline["sections"][-1]
    start = round(dur - RECAP_LEN, 2)
    if len(outline["sections"]) >= 3 and start > last["t_in"] + 1.0:          # never cover the last section's first second
        scenes.append({"id": "pkr", "block": "recap_chain", "t_in": start, "t_out": round(dur, 2), "values": {"theme": theme},
                       "groups_html": recap_groups("pkr", outline, icons, theme, buttons)})
    return {"scenes": scenes, "icons": sorted({i for i in icons if i} | (set(BUTTON_ICONS) if buttons else set())), "highlight": highlight_idx(outline, words, tl.get("keyword_ids")), "pill_style": pill_style(theme)}
