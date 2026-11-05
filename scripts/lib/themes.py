"""THEMES: fixed looks Hesham picks BEFORE a reel starts (templates/themes/<name>.json). Free, no AI.
A theme = a layout (stage / overlay / panel) + a colour palette (dark / violet). The choice is stored in the reel's creative brief (brief.json, "theme").
No theme chosen = the project's own setting (config format_pack.layout / theme), exactly as before.
  themes.names()          -> ["classic", "overlay", ...]
  themes.use_job(job)     -> reads the reel's brief and makes layouts.active_name() / themes.palette() follow it (call once per process)
  themes.palette(default) -> the palette of the chosen theme, else `default`"""
import json, os

from . import config as cfg

DIR = os.path.join(cfg.ROOT, "templates", "themes")
CURRENT = {"name": None}


def names():
    return sorted(f[:-5] for f in os.listdir(DIR) if f.endswith(".json")) if os.path.isdir(DIR) else []


def load(name):
    with open(os.path.join(DIR, os.path.basename(name) + ".json"), encoding="utf-8") as f:
        return json.load(f)


def use_job(job):
    """Pick up the theme from this reel's brief. Unknown or missing = no theme (project setting)."""
    CURRENT["name"] = None
    try:
        with open(os.path.join(job, "brief.json"), encoding="utf-8") as f:
            n = json.load(f).get("theme")
    except (OSError, ValueError):
        n = None
    if n in names():
        CURRENT["name"] = n
    return CURRENT["name"]


def current():
    return load(CURRENT["name"]) if CURRENT["name"] else None


def palette(default="dark"):
    t = current()
    return t["palette"] if t else default
