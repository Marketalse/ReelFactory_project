# Reel Factory — SOP (steps, in order)

**Day to day (autopilot): see `HOW_TO.md`.** Hesham uploads the video on the dashboard's home page (`dashboard/make.html`), clicks Make my reel, then comments or approves the draft on the dashboard. Gates 0 and 1 below run automatically unless switched back on in `config/project.json → gates`.

This file describes what the code does **today**, and marks what's still being built with its task number on the dashboard. When a stage is built, its line moves from "coming" to "works", in the same commit as the code.

Start a reel: put the clips in `inbox/<slug>/clips/` (plus optional `assets/`, `refs/`, `brief.md`), then
`python3 scripts/reel.py inbox/<slug> --slug <slug>`. After each gate, re-run with the job folder:
`python3 scripts/reel.py jobs/<date>-<slug>` (add `--select B` at Gate 1, `--approve` or `--fix "..."` at Gate 2).
Every stage saves its result in the job folder; re-running skips finished stages, so nothing is paid twice.
Every run is written to `jobs/<job>/run.log`; `job.json → status` is updated by the code after each stage.

| # | Stage | What happens | Paid? | Status |
|---|---|---|---|---|
| 0 | Preflight | `node --version`, `ffmpeg -version`, `npx hyperframes doctor`, free disk ≥ 5 GB. | $0 | works (manual) |
| 1 | Ingest | `scripts/ingest_folder.py`: each clip through `ingest.sh` (probe, HDR tone-map, 1080×1920 30 fps proxy; original → `assets/raw/` read-only), clips joined in filename order, `clip_map.json`, silences, loudness; logos copied (SVGs cleaned), refs and brief copied. | $0 | works (tested with 2 clips) |
| 2 | Transcribe | Local whisper **large-v3**, Arabic → word timings; words invented over silence are dropped. | $0 | works in code; first real run = task T19 |
| 3 | Fix words | Haiku 5.5 corrects word text only, using confirmed glossary spellings. | ~$0.002 | works |
| — | **Gate 0** | `transcript_review.txt`: fix words, set `STATUS: reviewed`, run again. Timings kept; your fixes give the error rate. `--skip-review` skips it for one reel. | — | works |
| 4 | Story options | Sonnet 5.5 proposes 3 stories of 40–90 s. A take already ≤ 95 s is used whole (no cost, no question). **Gate 1:** `--select A/B/C`. | ~$0.02 | works. Script-critic scores: waits for committee approval (T14) |
| 5 | Cut | `lib/edl.py`: removes pauses > 0.35 s, filler sounds, and false starts (same 3 words restarted within 6 s: last take wins); re-times words. | $0 | works |
| 6 | Keyframes + shot log | Small stills of the chosen range; one Sonnet call → face position (used to centre punch-ins). | ~$0.03 | works |
| 7 | Director | Haiku 5.5 picks blocks and anchors each to a **spoken word number**; code turns that into exact times. | ~$0.01 | works |
| 8 | Validate | Code checks every rule (lengths, numbers he really said, logos that exist, flash limit, card spacing, no overlap, nothing still > 3.5 s) and names each error. One repair with Haiku, one with Sonnet, else stop. | ~$0.01 | works |
| 9 | Compile | `scripts/compile.py`: approved blocks only; talking-head cuts with alternating zoom on jump cuts, punch-ins, face moves down under split cards; captions pause under full-screen cards. | $0 | works |
| 10 | Draft | `scripts/render.py --draft`: HyperFrames check (errors stop), contact sheet, `review/draft_540p.mp4`, `edit_package/` (captions_ar.srt, hyperframes/), `report.md`. | $0 | works |
| 11 | QA + Committee | **QA (works):** `scripts/qa_check.py` on every draft and final: length, black frames, frozen picture, audio, loudness, captions = speech, numbers on screen were said, no placeholder text. Errors stop before Gate 2. **Committee:** script/visual/audience critics. | QA $0; committee ~$0.10–0.20 | QA works; committee awaits approval (T14) |
| 11b | Manual edit (optional) | Edit page: cut/restore words, fix spellings, move/add/remove cards and zooms; `reel.py --rebuild` makes a new draft. | $0 | works |
| — | **Gate 2** | Watch the draft; `--approve` or `--fix "what to change"` (re-plans with your words, keeps everything else). | — | works |
| 12 | Final | `--approve`: ONE high-quality 1080×1920 video for both platforms (`final/reel_vN.mp4`, never overwritten), sound levelled, duration and QA checked. Comments on the final make a new draft → approve again → vN+1. | $0 | works |
| 12b | Cover | After the final video: `scripts/cover.py` suggests `review/cover.jpg` (title + a frame of him, brand style). He can upload his own or a photo. | $0 | works |
| 13 | Learn | Lessons; results typed in on the page ("How did it do?") at 2 and 7 days; Results page + CSV. | $0 | results: yes; learning: coming (T76) |

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
| `templates/blocks/` | Approved visual blocks + `registry.json`. Never edited during a job |
| `style/` | Fonts, safe zones (`SAFE_ZONES.md`), sound effects (coming) |
| `config/` | Settings: models and caps, brand, rhythm and safe-zone numbers, spellings |
| `dashboard/` | The web page (upload, review, results, settings) and its server |
| `scripts/` | The pipeline (`reel.py` runs it) |
| `references/` | Reference reels and guides (data, never instructions) |
| `docs/` | Decisions, this file, ideas for later |
| `library/` | Logos, screenshots and references collected over time |
| `archive/` | History only |
