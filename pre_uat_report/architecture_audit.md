# Architecture audit

Tested commit: `b3a2630175643f84f46a63d3fbebd532babb3d61` (plus the fixes made during the audit, see regression_results.md).

## Size and shape
- 62 Python modules, 10821 lines, 62 test files (333+ tests).
- Three layers: `dashboard/` (HTTP server, ~7 modules), `scripts/` (CLI entry points: reel.py, compile.py, render.py, ingest*.py, qa_check.py, cover.py ...), `scripts/lib/` (40 pure-logic modules). Visual templates in `templates/blocks/` (19 HTML blocks + registry.json). Config in `config/*.json`.
- Execution path of one reel: dashboard upload -> `reels_api._run` -> `scripts/reel.py` (pipeline list in `scripts/lib/pipeline.py`: ingest, transcribe, fix, review, selects, tighten, edl, outline, keyframes, shotlog, plan, compile, draft, critic, report) -> `compile.py` -> HyperFrames render (`render.py`) -> `qa_check.py` -> Gate 2 (approve) -> `render.final`.
- Paid AI calls: only through `Ctx.llm` in `scripts/reel.py` (budget guard before each call, ledger after).

## Largest modules
| module | lines | functions |
|---|---|---|
| reel.py | 1059 | 50 |
| dash/reels_api.py | 937 | 52 |
| lib/director.py | 508 | 18 |
| render.py | 428 | 23 |
| stress_dashboard.py | 414 | 27 |
| dash/serve.py | 401 | 16 |
| cover.py | 367 | 15 |
| lib/sequence.py | 317 | 21 |
| lib/speech_intel.py | 298 | 19 |
| lib/render_guard.py | 277 | 15 |
| lib/media_check.py | 265 | 14 |
| lib/hfbuild.py | 241 | 8 |

## Weaknesses found by reading and by testing

1. **Same rule copied in five places (caption gaps).** `compile.py:42`, `qa_check.py:107`, `lib/visual_plan.py:55,59`, `render.py:311`, `lib/render_guard.py:203` each decide which words have captions. When the Format Pack changed the rule in one place the others went wrong (BUG-002, BUG-003, BUG-004). Fix direction: one helper (`captions_gaps(job)`) read by all.
2. **Same problem for 'which scenes exist'.** `render_guard.preflight` reads the director's `timeline.json` while `compile.py` decides the real scenes (BUG-001). The compiled project (`compile_info.json`) should be the single source of truth for later checks.
3. **`scripts/reel.py` is a 1,000-line orchestrator with module-level mutable state** (`M_FIX/M_SEL/M_DIR` rewritten by the bake-off, `ROOT` rewritten by `--project`, `sys.stdout` replaced by `Tee`). It works, but every new mode adds another global. Recommended: pass a settings object into `Ctx` instead of rewriting module globals.
4. **No lock on a reel.** `reels_api._run` keeps 'one reel at a time' only in the dashboard's memory (`_running`). The CLI has no lock, and a dashboard killed with kill -9 leaves its reel process running while the new dashboard offers 'Try again' (see BUG-005 and the crash-test warning).
5. **Very long functions:** `dash/reels_api.py:progress` (148 lines), `dash/serve.py:_post` (144 lines), `lib/director.py:resolve` (129 lines), `reel.py:main` (123 lines), `ready_score.py:score` (109 lines), `ingest_folder.py:main` (103 lines), `reel.py:st_plan` (90 lines). `serve.py:_post` is one if-chain for every route; `reels_api.progress` mixes state detection, timing estimates and message building.
6. **AI call time-out is 600 s with 1 retry after 20 s** (`scripts/reel.py:post_with_retry`): a stalled AI service can hold a reel for about 20 minutes with no progress message.
7. **Heavy temporary data per reel:** the working copy `proxy.mp4` is about 1 MB per second of footage and is linked into the render project; a reel keeps proxy, audio, keyframes, draft and finals. No cleanup policy exists (see endurance results for the measured size).
8. **Bundled icons are attached like logos.** `lib/broll.attach` copies matching `icon-*.svg` files into the reel's `assets/` and the director sees them in 'LOGO FILES AVAILABLE'. Harmless but noisy; they should be listed separately for the Format Pack only.
9. **Dead code:** only 2 unreferenced functions found (`reel.numbers_spoken`, `serve.log_message` which is an override). Config keys: none unused.
10. **Modules without any test naming them:** `dash/add_expense.py`, `block_samples.py`, `cost_estimate.py`, `fetch_icons.py`, `safe_zone_preview.py`, `stress_dashboard.py` (small tools; `stress_dashboard.py` is itself a test tool).

## Strengths verified
- Pipeline is a declarative step list with checked inputs/outputs (`lib/pipeline.py`); a new step is one decorator.
- Money guard counts in-flight calls, enforces per-reel and monthly caps before each call (verified: I2).
- Every AI answer is validated by code before use (titles built from his words, scores clamped, ids checked); malformed answers never crash a step (verified: I1).
- Atomic writes (`os.replace`) and per-batch saves for long jobs (icon tagging, uploads) survive kill -9 (verified).

## Recommended refactoring (in order)
1. One `captions` helper used by compile, QA, visual plan, render checks.
2. Job lock (flock) in `reel.py`; dashboard `progress` reads it.
3. `compile_info.json` as the single record of what the compiled project contains; all post-compile checks read it.
4. Split `serve.py:_post` into a route table; split `reels_api.progress`.
5. Configurable AI time-out with progress messages while waiting.
6. Disk-usage policy: a per-reel cleanup of keyframes/audio after approval.
