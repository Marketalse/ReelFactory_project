"""Shared settings for every Reel Factory script. Everything comes from config/*.json — no model names,
prices, caps or paths are hard-coded in the scripts themselves. Standard library only."""
import glob, json, os, shutil
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = os.path.join(ROOT, "config")
LEDGER = os.path.join(ROOT, "dashboard", "expenses.json")


def local_set(path, value):
    """Write one setting into config/local.json, e.g. local_set(("matte", "engine"), "rvm"). Returns the file path."""
    p = os.path.join(CONFIG_DIR, "local.json")
    d = _local()
    cur = d
    for k in path[:-1]: cur = cur.setdefault(k, {})
    cur[path[-1]] = value
    with open(p, "w", encoding="utf-8") as f: json.dump(d, f, ensure_ascii=False, indent=1)
    return p


def _load(name):
    path = os.path.join(CONFIG_DIR, name)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"Missing config file: {path}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"config/{name} is not valid JSON: {e}")


def _merge(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict): _merge(base[k], v)
        else: base[k] = v
    return base


def _local():
    """config/local.json (NOT in git): this Mac's own choices (layout, cut-out engine...). Written by scripts/set_layout.py and set_matte.py, so the
    tracked config/project.json is never edited by hand and the dashboard can always update."""
    try:
        with open(os.path.join(CONFIG_DIR, "local.json"), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


PROJECT = _merge(_load("project.json"), _local())
BRAND = _load("brand.json")
RULES = _load("rules.json")
GLOSSARY = _load("glossary.json")

ROLES = {k: v for k, v in PROJECT.get("roles", {}).items() if not k.startswith("_")}
MODELS = PROJECT["models"]
_LEGACY = {"transcript_fix": "word_fix", "selects": "story", "director": "director", "director_fallback": "repair", "vision": "shot_log"}
for _k, _r in _LEGACY.items():                      # the old names follow the roles
    if _r in ROLES:
        MODELS[_k] = ROLES[_r]["model"]
BUDGET = PROJECT["budget_usd"]


def role(name, default_effort="low"):
    """(model, effort) for one AI job, from config/project.json -> roles."""
    r = ROLES.get(name)
    if not r:
        raise SystemExit(f"No role '{name}' in config/project.json -> roles")
    return r["model"], r.get("effort", default_effort)


def price(model):
    """($ per M input tokens, $ per M output tokens) for a model, from config/project.json."""
    p = PROJECT["prices_per_mtok"].get(model)
    if not p:
        raise SystemExit(f"No price for model '{model}' in config/project.json -> prices_per_mtok")
    return p["in"], p["out"]


HOME_DIR = os.path.expanduser("~/.reelfactory")
TOOLS = os.path.join(HOME_DIR, "tools")            # Reel Factory's own copies of ffmpeg/ffprobe (no Hermes needed)
FFMPEG_DIRS = [TOOLS, "/opt/homebrew/bin", "/usr/local/bin"]
OLD_TOOLS = "~/.hermes/tools/ffmpeg-*"             # only read once, to copy ffmpeg into TOOLS


def adopt_ffmpeg():
    """One-time move away from Hermes: copy ffmpeg + ffprobe from the old Hermes tools folder into TOOLS.
    Returns the TOOLS folder if it now holds ffmpeg, else None. Never changes the Hermes folder."""
    if os.access(os.path.join(TOOLS, "ffmpeg"), os.X_OK):
        return TOOLS
    for d in sorted(glob.glob(os.path.expanduser(OLD_TOOLS)), reverse=True):
        if os.access(os.path.join(d, "ffmpeg"), os.X_OK):
            os.makedirs(TOOLS, exist_ok=True)
            for name in ("ffmpeg", "ffprobe"):
                src = os.path.join(d, name)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(TOOLS, name))
                    os.chmod(os.path.join(TOOLS, name), 0o755)
            return TOOLS
    return None


def find_ffmpeg():
    """ffmpeg on PATH, else Reel Factory's own tools folder or Homebrew (copied from Hermes once if needed).
    Returns (ffmpeg_path, folder)."""
    p = shutil.which("ffmpeg")
    if p:
        return p, os.path.dirname(p)
    for d in FFMPEG_DIRS:
        d = os.path.expanduser(d)
        if os.access(os.path.join(d, "ffmpeg"), os.X_OK):
            return os.path.join(d, "ffmpeg"), d
    try:
        d = adopt_ffmpeg()
    except OSError:
        d = None
    if d:
        return os.path.join(d, "ffmpeg"), d
    raise SystemExit("ffmpeg not found: install it (brew install ffmpeg) or put it in ~/.reelfactory/tools")


def ffmpeg_on_path():
    """Put ffmpeg's folder on PATH for this process and every tool it starts (HyperFrames render needs it)."""
    try:
        _, d = find_ffmpeg()
    except SystemExit:
        return False
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if d not in parts:
        os.environ["PATH"] = os.pathsep.join([d] + [x for x in parts if x])
    return True


ffmpeg_on_path()


def key_file():
    return os.path.expanduser(PROJECT["route"].get("key_file") or os.path.join(HOME_DIR, "nous_api_key"))


def _saved_key():
    try:
        with open(key_file(), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def auth():
    """(base_url, key) for the model route. The key never lives in the repo. Order:
    1. env RF_API_KEY;  2. Reel Factory's own key file (route.key_file, one line). Hermes is not used."""
    r = PROJECT["route"]
    key = os.environ.get("RF_API_KEY", "").strip() or _saved_key()
    if not key:
        raise SystemExit("No API key saved yet: open Reel Factory, click Settings and paste your Nous key")
    return r["base_url"], key


def key_source():
    """Where the API key comes from, in words (for error messages). Never returns the key."""
    if os.environ.get("RF_API_KEY", "").strip():
        return "the RF_API_KEY setting"
    if _saved_key():
        return "Reel Factory's own key (Settings)"
    return "no key saved (Settings)"


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
