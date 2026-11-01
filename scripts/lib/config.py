"""Shared settings for every Reel Factory script. Everything comes from config/*.json — no model names,
prices, caps or paths are hard-coded in the scripts themselves. Standard library only."""
import json, os, shutil
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = os.path.join(ROOT, "config")
LEDGER = os.path.join(ROOT, "dashboard", "expenses.json")


def _load(name):
    path = os.path.join(CONFIG_DIR, name)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"Missing config file: {path}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"config/{name} is not valid JSON: {e}")


PROJECT = _load("project.json")
BRAND = _load("brand.json")
RULES = _load("rules.json")
GLOSSARY = _load("glossary.json")

MODELS = PROJECT["models"]
BUDGET = PROJECT["budget_usd"]


def price(model):
    """($ per M input tokens, $ per M output tokens) for a model, from config/project.json."""
    p = PROJECT["prices_per_mtok"].get(model)
    if not p:
        raise SystemExit(f"No price for model '{model}' in config/project.json -> prices_per_mtok")
    return p["in"], p["out"]


def find_ffmpeg():
    """ffmpeg on PATH first, then the old Hermes tools folder. Returns (ffmpeg_path, folder)."""
    p = shutil.which("ffmpeg")
    if p:
        return p, os.path.dirname(p)
    old = os.path.expanduser("~/.hermes/tools/ffmpeg-9.0.1-darwin-arm64")
    if os.path.exists(os.path.join(old, "ffmpeg")):
        return os.path.join(old, "ffmpeg"), old
    raise SystemExit("ffmpeg not found: install it or put it on PATH")


def auth():
    """(base_url, key) for the model route. The key is read from the auth file, never stored in the repo."""
    r = PROJECT["route"]
    path = os.path.expanduser(r["auth_file"])
    try:
        with open(path, encoding="utf-8") as f:
            a = json.load(f)["providers"][r["provider"]]
    except (OSError, KeyError, json.JSONDecodeError) as e:
        raise SystemExit(f"Cannot read the '{r['provider']}' key from {path}: {e}")
    return a.get("inference_base_url") or r["base_url"], a["agent_key"]


def month_spent(month=None):
    """Total recorded spend for a month (YYYY-MM) from dashboard/expenses.json."""
    month = month or date.today().isoformat()[:7]
    try:
        with open(LEDGER, encoding="utf-8") as f:
            rows = json.load(f).get("rows", [])
    except (OSError, json.JSONDecodeError):
        return 0.0
    return sum(float(r.get("amount") or 0) for r in rows
               if str(r.get("date", "")).startswith(month) and not r.get("archived"))
