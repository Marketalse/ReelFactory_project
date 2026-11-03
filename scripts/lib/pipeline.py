"""The reel pipeline as ONE list of steps (T137). Each step says: what it is, which AI role it uses (config/project.json -> roles;
None = no paid AI), which files it needs and which it makes. scripts/reel.py runs the steps in this order.

Add a new step without touching reel.py's runner:
    from lib import pipeline
    @pipeline.step("outline", after="tighten", role="outline", needs=["chosen_select.json"], makes=["outline.json"], label="...")
    def st_outline(c): ...
(import that module from reel.py so the step registers itself). Free, no network."""

_ROWS = [  # name, label, role, needs, makes
    ("ingest", "Prepare the clips", None, [], ["proxy.mp4", "clip_map.json"]),
    ("transcribe", "Listen (Whisper, on your Mac)", None, ["proxy.mp4"], ["transcript_asr.json"]),
    ("fix", "Fix and proofread the words", "word_fix", ["transcript_asr.json"], ["transcript.json", "speech_intel.json"]),
    ("review", "Your word check (off in autopilot)", None, ["transcript.json"], ["transcript.json"]),
    ("selects", "Pick the story and hooks", "story", ["transcript.json", "speech_intel.json"], ["selects.json", "chosen_select.json"]),
    ("tighten", "Cut weak lines", "tighten", ["chosen_select.json", "transcript.json"], ["tighten.json"]),
    ("edl", "Cut list (pauses, fillers, retakes)", None, ["chosen_select.json", "transcript.json"], ["edl.json"]),
    ("keyframes", "Take key pictures", None, ["edl.json"], ["keyframes.json"]),
    ("shotlog", "Look at the pictures", "shot_log", ["keyframes.json"], ["shot_log.json"]),
    ("plan", "Plan the visuals (director)", "director", ["edl.json", "transcript.json"], ["scene_plan.json", "timeline.json", "validation.json"]),
    ("compile", "Build the video project", None, ["timeline.json", "edl.json"], ["compile_info.json"]),
    ("draft", "Render the draft", None, ["compile_info.json"], ["review/draft_540p.mp4"]),
    ("report", "Write the report", None, ["timeline.json"], ["report.md"]),
]
ROWS = [dict(name=n, label=l, role=r, needs=list(a), makes=list(b)) for n, l, r, a, b in _ROWS]
FUNCS = {}
START_FILES = {"input"}          # what exists before the first step


def step(name, after=None, role=None, needs=(), makes=(), label=""):
    """Register the function of a step. A new name is inserted after `after`; a built-in name just gets its function."""
    def deco(fn):
        if not any(r["name"] == name for r in ROWS):
            if not after or not any(r["name"] == after for r in ROWS):
                raise ValueError(f"step '{name}': 'after' must be an existing step (got {after!r})")
            i = [r["name"] for r in ROWS].index(after) + 1
            ROWS.insert(i, dict(name=name, label=label or name, role=role, needs=list(needs), makes=list(makes)))
        FUNCS[name] = fn
        return fn
    return deco


def order():
    return [r["name"] for r in ROWS]


def row(name):
    return next(r for r in ROWS if r["name"] == name)


def ai_steps():
    return [r for r in ROWS if r["role"]]


def check(roles=None):
    """Problems in the list (empty = fine): a step with no function, an unknown AI role, a file a step needs that nobody makes."""
    bad, made = [], set(START_FILES)
    for r in ROWS:
        if r["name"] not in FUNCS: bad.append(f"{r['name']}: no function registered")
        if roles is not None and r["role"] and r["role"] not in roles: bad.append(f"{r['name']}: unknown AI role '{r['role']}'")
        for f in r["needs"]:
            if f not in made and r["name"] != "ingest": bad.append(f"{r['name']}: needs {f}, which no earlier step makes")
        made.update(r["makes"])
    return bad
