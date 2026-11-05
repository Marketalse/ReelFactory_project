"""Little picture of each style for the Styles menu, drawn from the style's own zones with Hesham's Figma colours (purple frame, red animation, green clip,
cyan text, black hero). Free, no files: an inline SVG string per style. themes_menu() -> [{name, label, description, svg}] for the dashboard."""
import html, json, os

from . import config as cfg, layouts, states, themes

COL = {"bg": "#2b2f3d", "frame": "#e7cdf8", "anim": "#fbb8b8", "clip": "#d3cdd0", "text": "#b9f7f4", "hero": "#111"}


def _r(r, fill, op=1.0, dash=None, rx=14):
    return (f'<rect x="{r[0]}" y="{r[1]}" width="{r[2] - r[0]}" height="{r[3] - r[1]}" rx="{rx}" fill="{fill}" fill-opacity="{op}"'
            + (f' stroke="{dash}" stroke-width="6" stroke-dasharray="18 12"' if dash else "") + "/>")


def _person(x, y, s=1.0):
    return f'<circle cx="{x}" cy="{y}" r="{60 * s}" fill="{COL["hero"]}"/><path d="M{x - 130 * s} {y + 250 * s} a{130 * s} {110 * s} 0 0 1 {260 * s} 0z" fill="{COL["hero"]}"/>'


def _panel(st, ox):
    """One 1080x1920 miniature of a state-like dict, placed at x offset ox (viewBox units)."""
    g = [f'<g transform="translate({ox} 0)">', _r([0, 0, 1080, 1920], COL["bg"], rx=0)]
    cl, fr = st.get("clip"), st.get("frame")
    if fr == "none" or (cl and cl.get("full")): g.append(_r([0, 0, 1080, 1920], COL["clip"], rx=0)); g.append(_person(540, 1150, 2.2))
    elif fr is None and not cl: g.append(_r([0, 0, 1080, 1920], COL["frame"], rx=0))
    if cl and cl.get("rect"):
        g.append(_r(cl["rect"], COL["clip"], rx=40)); g.append(_person(540, cl["rect"][1] + 330, 2.0))
    if st.get("anim"): g.append(_r(st["anim"], COL["anim"], 0.92, "#e24"))
    if st.get("text"): g.append(_r(st["text"], COL["text"], 0.85, "#36c"))
    cap = st.get("caption")
    if cap: g.append(_r([108, cap["y"], 920, cap["y"] + cap["h"]], COL["text"], 0.9, "#36c", rx=10))
    if cl and cl.get("hero"): g.append(_person(540, cl["rect"][1] - 40, 2.6))
    g.append("</g>")
    return "".join(g)


def _legacy(name):
    if name == "panel":
        return [{"frame": {"rect": [60, 380, 1020, 1100]}, "clip": {"rect": [60, 380, 1020, 1100]}, "text": [108, 1150, 920, 1500], "caption": None}]
    spec = layouts.load(name); z = spec["zones"]
    if name == "overlay":
        return [{"frame": "none", "clip": {"full": True}, "anim": z["stage"]["rect"], "caption": {"y": z["caption"]["rect"][1], "h": 100}}]
    cx = z.get("container", {}).get("rect")
    return [{"frame": {"rect": cx} if cx else "none", "clip": {"rect": cx, "hero": "hero" in z} if cx else {"full": True}, "anim": z["stage"]["rect"],
             "caption": {"y": z["caption"]["rect"][1], "h": 80}}]


def panels_for(theme):
    if theme.get("sequence"):
        seen = []
        for n in theme["sequence"]:
            if n not in seen: seen.append(n)
        return [states.load(n) for n in seen]
    return _legacy(theme["layout"])


def svg_for(theme):
    ps = panels_for(theme)
    W = 1080 * len(ps) + 120 * (len(ps) - 1)
    body = "".join(_panel(p, i * 1200) for i, p in enumerate(ps))
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} 1920" preserveAspectRatio="xMidYMid meet" role="img" aria-label="{html.escape(theme.get("label", ""))}">{body}</svg>'


def themes_menu():
    out = []
    for n in sorted(themes.names(), key=lambda n: (themes.load(n).get("order", 99), n)):
        t = themes.load(n)
        try: svg = svg_for(t)
        except Exception: svg = ""                                          # a broken picture never breaks the menu
        out.append({"name": n, "label": t.get("label", n), "description": t.get("description", ""), "svg": svg})
    return out
