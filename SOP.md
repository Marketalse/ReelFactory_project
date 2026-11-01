# Reel Factory — SOP (steps, in order)

This file describes what the code does **today**, and marks what's still being built with its task number on the dashboard. When a stage is built, its line moves from "coming" to "works", in the same commit as the code.

Command: `python3 scripts/reel.py <clip or job folder> --slug <name>`. Every stage saves its result in the job folder; re-running skips finished stages, so nothing is paid for twice. Every run is written to `jobs/<job>/run.log`.

| # | Stage | What happens | Paid? | Status |
|---|---|---|---|---|
| 0 | Preflight | `node --version`, `ffmpeg -version`, `npx hyperframes doctor`, free disk ≥ 5 GB. Stop and report on any failure. | $0 | works (manual) |
| 1 | Ingest | `scripts/ingest.sh <clip> <slug>`: probe (HDR, rotation), 1080×1920 30 fps SDR proxy, 16 kHz audio, silences, loudness, `job.json`. Original is never changed. | $0 | works, **one clip**. Folder of several clips joined in order: coming (T26) |
| 2 | Transcribe | Local whisper (`config/project.json → asr.model`, default large-v3-turbo) → `transcript_asr.json` with word timings. | $0 | works |
| 3 | Fix words | Haiku 5.5 corrects word text only (never timings), using the glossary → `transcript.json`. | ~$0.002 | works. Glossary feed: coming (T27) |
| — | **Gate 0** | Hesham fixes words in `transcript_review.txt`. | — | coming (T27). Until then: check `transcript.json` by eye |
| 4 | Story options | Sonnet 5.5 proposes 3 stories of 40–90 s from his own words → `selects.json`. **Gate 1:** the run stops and prints them; Hesham re-runs with `--select A`, `B` or `C`. | ~$0.02 | works. Script-critic scores: coming (T28) |
| 5 | Keyframes | Up to 40 small stills of the chosen range only (`scripts/keyframes.py`). | $0 | works |
| 6 | Shot log | One batched Sonnet 5.5 call over the stills → face box, eyes, energy, usable moments. | ~$0.03 | works. Local face analysis instead: coming |
| 7 | Cut | Remove pauses, fillers and retakes; re-time words (`scripts/edl.py`). | $0 | coming (T29) |
| 8 | Director | Haiku 5.5 writes `scene_plan.json`: beats/moments using only existing blocks and real media. | ~$0.01 | works with the current schema; cue-by-spoken-word schema: coming (T30) |
| 9 | Validate | Rules from `config/rules.json` checked by code. If it fails: one repair with the Director, then one with the fallback (Sonnet). Still failing → stop. | ~$0.01–0.1 | works |
| 10 | Report | `pipeline_report.md`: tokens, cost and time per stage, warnings. | $0 | works |
| 11 | Compile | Scene plan → HyperFrames project from the approved blocks only (`scripts/compile.py`). | $0 | coming (T31; blocks T20–T25) |
| 12 | QA | Deterministic checks (freeze, black frames, loudness, duration, caption coverage, banned text). | $0 | coming (T35) |
| 13 | Committee | Script, visual and audience critics + measurements → score and report; up to 2 automatic fixes. | ~$0.10–0.20 | coming (T37), pending approval (T14) |
| — | **Gate 2** | Hesham gets the 540p draft, the edit package and the committee report; replies `ok` or `fix: …`. | — | coming (T32) |
| 14 | Final render | 1080×1920 high quality, one file per platform CTA, versioned (`v1`, `v2`…), duration checked. | $0 | coming (T32) |
| 15 | Learn | Visual ledger + up to 3 lessons; after posting, `performance.csv` at 48 h. | $0 | coming (T45, T49) |

## Money guard (works)
- Per reel: warning at `budget_usd.per_reel_warn`; hard stop at `per_reel_stop` (the `--budget` default).
- Per month: hard stop when this month's ledger total plus the next call would pass `monthly_stop`.
- Every paid call is logged to `jobs/<job>/cost.json` and the run total to `dashboard/expenses.json`. Rows are never deleted.

## Shooting checklist (for Hesham)
iPhone: 4K or 1080p at **30 fps**, Format **Most Compatible**, **HDR Video off**. Quiet room, phone at eye level about 1 m away, plain background, a little headroom. Say the hook first, then pause 2 s. Hold still for about 1 s after each key line.

## Folders
| Path | Use |
|---|---|
| `inbox/<slug>/` | What Hesham hands in: `clips/`, `assets/`, `refs/`, `brief.md` |
| `jobs/<date>-<slug>/` | Everything the pipeline makes for one reel |
| `assets/raw/` | Originals, read-only |
| `templates/` | Approved blocks, schema, prompts. Never edited during a job |
| `library/` | Logos, screenshots and references collected over time |
| `archive/` | History only |
