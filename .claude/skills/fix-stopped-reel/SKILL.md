---
name: fix-stopped-reel
description: Diagnose and fix a reel that stopped, crashed or failed to render in Reel Factory (dashboard shows "Stopped", "render failed", or a red error). Use when Hesham reports an error message, a screenshot of one, or a reel stuck in a step.
---

# Fix a stopped reel

Read first: `.reel-agent/lessons.md` → "Known failures" (most errors already happened once).

## 1. Find the real error (don't guess)
- `jobs/<job>/run.log` — every step of `scripts/reel.py`; the last `STOP:` or `CRASH` line is the cause.
- `jobs/<job>/review/render_error.log` (draft) or `final/*/render_error.log` (finals) — the full HyperFrames output. npm "notice" lines are noise; look for `Error`.
- `jobs/<job>/job.json` → `status` shows the last finished step (ingest → transcribe → fix → review → selects → edl → plan → compile → draft).
- Dashboard → Settings → health checks (key, ffmpeg, node, npx, disk).

## 2. Known causes
| Message | Cause | Fix |
|---|---|---|
| `render failed (1): npm notice…` | real error hidden by npm notices | read `render_error.log` |
| `FFmpeg not found` | ffmpeg folder not on PATH | `lib/config.ffmpeg_on_path()`; check Settings health |
| `plan still breaks the rules after repair: …` | AI plan broke a block rule | fix in `scripts/lib/director.py` (e.g. `fix_hook`), add a test in `tests/test_taste.py` |
| `face cut shorter than 0.3 s` | tiny cut piece | fold it into a neighbour (compile) |
| `no key saved (Settings)` | Nous key missing | Hesham saves it in Settings (never ask for it in chat) |
| `budget` / cap stop | money guard | never raise a cap without Hesham's written OK in `DECISIONS.md` |
| captions missing in video but fine in stills | a template sets visibility | `TemplateContractTests` |

## 3. Reproduce offline, fix, prove
- Reproduce with a test in `tests/` using `tests/fixtures` — no paid calls. Paid calls happen only inside `scripts/reel.py`.
- `python3 -m unittest discover tests` must pass.
- Commit on the working branch, push; Hesham updates via Settings → "Get the latest version" and clicks **Try again**.
- Same error 3 times → stop, write it in the task notes, hand back.

## 4. Remember it
Add one line to `.reel-agent/lessons.md` → "Known failures": verb first, cause, fix, job name, date.

## Never
Delete anything in `jobs/`, `inbox/`, `library/`; touch the original footage; paste keys.
