# Reel Factory — Restructure Plan

How to pull the scattered pieces into one project that runs from one command: raw clip → approved reel.
This builds on `Reel_Factory_Diagnosis.md`. Fill in the answers I need in `Reel_Factory_Inputs_Needed.md`.

---

## 1. The principle: one source of truth per topic

Right now each topic lives in 3–8 files that contradict each other. After the restructure, each topic has exactly one home:

| Topic | Single home | Replaces |
|---|---|---|
| What the project is and how to run it | `README.md` | flowchart brief, MASTER_INDEX, FINAL_INDEX |
| Where we are now | `STATUS.md` | 8 status/queue/board/map files |
| What was decided and why | `DECISIONS.md` | decision tables in EXECUTION_PLAN, COST_MODEL, MODELS, library.json |
| Rules for the agent | `AGENTS.md` (slimmed) | AGENTS.md + rule cards in flowchart + library.json `editorial_rules` |
| The steps, in order | `SOP.md` (rewritten to match the code) | SOP.md + EXECUTION_PLAN §1 + flowchart §1 |
| Models, budget, paths, gate settings | `config/project.json` | models.json, MODELS.md, llm.md, COST_MODEL numbers, hard-coded values in reel.py |
| Brand, handle, CTA words | `config/brand.json` | style/brand.json, BRAND dict in reel.py, brand table in AGENTS.md |
| Rhythm and validator limits | `config/rules.json` | rhythm table in plan, constants inside `validate_plan()` |
| Scene-plan format | `templates/schema/scene_plan.schema.json` | the 2 conflicting schemas (v0 and reel.py) |
| AI prompts | `templates/prompts/*.md` | prompts hard-coded inside reel.py |
| Visual building blocks | `templates/blocks/*.html` | nothing (missing today) |
| Spend | `dashboard/expenses.json` (one ledger) | cost.json totals, COST_MODEL tables, flowchart numbers |

**Rule:** if a fact appears in two places, one of them must be deleted or turned into a link.

---

## 2. Target folder structure

```
Reel-Factory/
├── README.md                  NEW   1 page: what it is, install, "run one reel" command
├── STATUS.md                  NEW   Now / Next / Blocked / Last result (≤ 30 lines)
├── DECISIONS.md               NEW   dated log: date · decision · who · why
├── AGENTS.md                  REWRITE  ≤ 150 lines: role, gates, limits, never-do list
├── SOP.md                     REWRITE  one section per pipeline stage, matching reel.py
│
├── config/
│   ├── project.json           NEW   models, prices, budget caps, ASR model, paths, gate switches
│   ├── brand.json             MOVE  from style/brand.json + handle + CTA defaults + safe zones
│   ├── rules.json             NEW   max hold 3.5 s, hook ≤ 3 s, max 2 flashes, min beat 0.8 s…
│   └── glossary.json          NEW   names/brands/English terms the transcript fix must keep
│
├── scripts/
│   ├── reel.py                MODIFY  orchestrator; reads config; new stages added
│   ├── ingest.sh              KEEP
│   ├── keyframes.py           KEEP
│   ├── edl.py                 NEW   remove pauses/fillers → kept segments + re-timed words
│   ├── compile.py             NEW   scene_plan + EDL → HyperFrames index.html (no AI)
│   ├── qa_check.py            NEW   deterministic checks (lint, freeze, black, loudness, duration…)
│   ├── vision_qa.py           NEW   one batched Sonnet call on ~6 stills, JSON rubric
│   ├── render.py              NEW   versioned render + ffprobe verify + ledger + visual ledger
│   └── lib/
│       ├── llm.py             NEW   one paid-call function: budget guard, logging (moved out of reel.py)
│       └── ledger.py          NEW   monthly cap check; replaces add_expense.py logic
│
├── templates/
│   ├── base/index.html        NEW   root composition: brand CSS variables, fonts, root timeline
│   ├── blocks/                NEW   the 6 MVP blocks (each driven only by data/JSON)
│   │   ├── face_cut.html          proxy segment + optional punch-in
│   │   ├── captions.html          Arabic word-pop, RTL, Harakah shaping, lime keyword
│   │   ├── hook_two_tone.html     visible at 0.0 s
│   │   ├── text_card.html         kinetic headline
│   │   ├── flash.html             lime + one word
│   │   └── cta_card.html          CTA words + promise + handle
│   ├── schema/scene_plan.schema.json   NEW   the ONE plan format
│   └── prompts/               NEW   fix.md · selects.md · director.md · repair.md · vision_qa.md
│
├── vendor/harakah/            MOVE  built browser file only (not the whole repo + .git)
├── style/fonts/               KEEP  ReadexPro + OFL
├── references/                KEEP  ref1–6 mp4 + ONE merged reference_spec.md
├── assets/raw/                KEEP  originals, read-only
├── assets/broll/              LATER only if you decide B-roll is in scope
├── jobs/<date>-<slug>/        KEEP  one folder per reel
├── dashboard/                 KEEP  expenses.json, dashboard.html (fix add_expense.py)
├── .reel-agent/               KEEP  lessons.md, visual-ledger.json
├── tests/
│   ├── fixtures/              NEW   a 15 s sample clip + its transcript
│   └── test_pipeline.py       NEW   validator, EDL, compiler, QA tested without paid calls
└── archive/                   everything retired (nothing is deleted outright)
```

Tools stay outside the project folder, as now (`~/.hermes/tools/reel-factory/`).

---

## 3. What happens to every existing file

| Existing file | Action | Where its content goes |
|---|---|---|
| REEL_FACTORY_MASTER_INDEX / FINAL_INDEX / LIVE_QUEUE / CONTROL_BOARD / TASK_MAP / CANONICAL_TASK_MAP / EXECUTION_STATUS / STATUS_SNAPSHOT | **Archive all 8** | `STATUS.md` (current state) + `DECISIONS.md` (Telegram removed, Vision QA, cap) |
| EXECUTION_PLAN.md (v3) | Archive | Decisions → `DECISIONS.md`; remaining phases → "Roadmap" section in `STATUS.md` |
| AGENTS.md | Rewrite (slim) | Remove generic HyperFrames skill tables, freshness/cooldown rules (park until reel #10), Multica lines duplicated |
| SOP.md | Rewrite | One section per stage of the real pipeline; gates written as exact message formats |
| model/MODELS.md, models.json, llm.md | Merge → `config/project.json` | Explanation text → a short "Models" section in README |
| model/COST_MODEL.md, cost_model.py | Keep in `docs/` | Update to include selects, repair, agent sessions; read prices from config |
| style/brand.json | Move → `config/brand.json` | Add handle, CTA defaults, safe zones, caption sizes |
| templates/library.json | Archive | Brand → brand.json; slots → blocks/; asset packs → DECISIONS (B-roll yes/no) |
| templates/v0_manifest / v0_build_checklist / v0_input_sheet / v0_scene_plan_example | Archive | Replaced by schema + blocks + `Reel_Factory_Inputs_Needed.md` |
| reels/v0-draft/* | Archive | Its plan breaks the rules (empty counter, 19.6 s hold) |
| scripts/reel.py | Modify | Prompts → templates/prompts/; paid-call code → lib/llm.py; add stages edl, compile, qa, vision_qa, preview, render |
| scripts/ingest.sh, keyframes.py | Keep | — |
| inbox/scripts/intake.py | Archive (or merge into ingest.sh) | Two intake scripts do the same job |
| dashboard/add_expense.py | Fix | No silent 200-row deletion; correct categories; mark partial runs as "stopped" |
| references/reference_spec.md + reference_spec_v2.md | Merge into one | — |
| references/ai-tool-reel-teardown.md, ai-tool-prompts.md | Keep, marked "later format" | Not part of the MVP |
| references/harakah-integration.md | Keep | Short note; the build goes in vendor/ |
| integrations/harakah (full repo + .git + node_modules) | Replace with built file in vendor/ | — |
| spikes/* | Keep as is | Never referenced by jobs |
| .reel-agent/lessons.md | Keep, clean | Move "Workflow boundaries" into AGENTS.md |
| jobs/2026-10-31-img0019, jobs/2026-11-01-img0020-pipeline | Keep | IMG_0020 becomes the first golden test clip |
| Flowchart HTML | Regenerate at the end | From README + STATUS, so it can't drift again |
| `.DS_Store`, `__pycache__` | Delete | Add a `.gitignore` |

---

## 4. How the pieces connect after the fix

```
inbox/store-tips/
├── clips/      IMG_0021.MOV, IMG_0022.MOV …   (joined in order)
├── assets/     logos .svg/.png, screenshots    (copied into library/assets with tags)
├── refs/       optional reference videos       (described once, cached in library/refs)
└── brief.md    optional notes (template: templates/inbox_brief.md)

python3 scripts/reel.py inbox/store-tips/ --slug store-tips

 ingest each clip → same proxy format → join in order (+ map back to originals)
   ─▶ transcribe ─▶ fix ─▶ [GATE 0: you fix words in transcript_review.txt]
   ─▶ selects ─▶ [GATE 1: you reply A / B / C]
   ─▶ edl ─▶ analyse face (local) ─▶ director ─▶ validate (+1 repair)
   ─▶ compile ─▶ qa_check ─▶ vision_qa (max 2 auto-fix loops)
   ─▶ preview ─▶ [GATE 2: you reply "ok" or "fix: …"]
   ─▶ render ─▶ verify ─▶ ledger + lessons
```

- Every stage reads `config/*.json` and writes its result file into the job folder. If that file exists, the stage is skipped on re-run, so a crash or a stop resumes where it left off.
- `job.json → status` is updated by the code after each stage, not by the agent.
- Each gate stops the run and prints one short message. You answer, re-run the same command, and it continues.
- Every paid call goes through `lib/llm.py`, which checks the per-job **and** monthly cap first and logs the measured cost.
- No AI writes HTML. The Director only fills fields in the schema. `compile.py` turns that into HTML from the 6 approved blocks.

---

## 4b. What each reel delivers (decided 2026-11-01)

```
jobs/<date>-<slug>/
├── review/
│   └── draft_540p.mp4            small, fast, low quality — for Gate 2 review only
├── edit_package/                 for your own tweaks + export, no full re-render
│   ├── clean_cut.mp4             talking head with pauses/fillers removed, punch-ins applied, no graphics
│   ├── graphics_alpha.mov        all captions, titles, cards, flashes on a transparent layer
│   ├── captions_ar.srt           plain caption text + timings (editable fallback)
│   ├── timeline.fcpxml           opens in DaVinci Resolve / Final Cut / Premiere with both layers in place
│   └── hyperframes/              the full HyperFrames project (open in HyperFrames Studio, edit, export)
└── final/
    └── reel_v1_1080p.mp4         high quality, only after you approve (v2, v3… never overwritten)
```

- **Small tweak (trim, move a cut, nudge a caption):** open `timeline.fcpxml`, or put `clean_cut.mp4` and `graphics_alpha.mov` on two tracks in CapCut, edit, export.
- **Change caption words or a title:** reply `fix: …`. Only the graphics layer re-renders, locally, for $0 and a few minutes.
- Rendering never costs money. It only takes time on the Mac.

---

## 4c. Adopted from Higgsfield's architecture (2026-11-01)

| # | Their idea | How we build it | New / changed file |
|---|---|---|---|
| 1 | One spec file is the authority for every effect; prompts and code both read it | Block registry: name, inputs, limits, layer, SFX. The Director prompt and the validator are **generated from it**, so they can never drift apart | `templates/blocks/registry.json` |
| 2 | AI fills parameters only; an error names the bad parameter | `compile.py` rejects with "beat b4: `keyword` missing"; the repair call fixes values, never files | `compile.py` |
| 3 | Moments cued to a spoken word, snapped to the stressed syllable | Director writes `cue: "customer service"`, not seconds; code finds the time after cutting | `templates/schema/scene_plan.schema.json` |
| 4 | Craft is automatic on every moment | SFX + punch-in + small shake + spring text added by code; the Director never decides them | `templates/blocks/*`, `compile.py` |
| 5 | Max moments and minimum spacing per effect | e.g. flash ≤ 2, name tag ≥ 5 s apart, text card every 15–20 s | `config/rules.json` |
| 6 | Fixed layer order; finishing pass applied once on top | Face cut → graphics layer → captions → finishing pass; matches the edit package layers | `compile.py`, `render.py` |
| 7 | Positions placed automatically below the face | Use the local face box to place captions and cards | `edl.py` / face analysis |
| 8 | Logos: user's files win → else fetch the official icon → else a text chip | Same order for `logo_card` and `name_tag` | `scripts/logos.py` |
| 9 | Licensed SFX library with a catalog and licence file | Your chosen SFX pack, tagged by type (whoosh, hit, pop, riser) | `style/sfx/catalog.json`, `LICENSES.txt` |
| 10 | Energy map of a reference: hits, cuts and changes per second | Measured from your best reels; checked against every render | `scripts/energy.py` |
| 11 | Review like an editor: timing, space, polish; stills at start/peak/end | Visual member of the committee | `scripts/committee.py` |
| 12 | Paid-call ledger: cap set before the first paid call, every call guarded and recorded | Already planned; add "estimate all paid calls of the job up front" | `scripts/lib/llm.py` |
| 13 | Resume from saved state, never pay twice | Each stage caches its output; `job.json` status is written by code | `reel.py` |
| 14 | Deliver a size-capped file from a verified master; keep the editable project | Draft + edit package + final | `render.py` |
| 15 | One style per video, varied between videos | Replaces the complex 5-reel cooldown rules | `config/brand.json` (`styles`) |
| 16 | Load only the instructions the current stage needs | Slim AGENTS.md + one prompt file per stage | `templates/prompts/*` |

**Not copied on purpose:** no-questions autonomous spending (we keep your 3 gates), AI-generated footage (out of scope; your face is the content), and running in their cloud (we stay on your Mac).

---

## 5. Work order

Each phase ends in something you can see. I can do the building; the parts marked **YOU** need you.

| # | Phase | Who | Done when |
|---|---|---|---|
| 0 | Move the project into a private GitHub repo (code + docs only; video stays on your Mac) | **YOU** create the repo; I set it up | Repo exists with `.gitignore` for media |
| 1 | Clean-up: create README, STATUS, DECISIONS, config/*.json; archive the 8 status files; slim AGENTS + SOP | Me | One source of truth per topic |
| 2 | Fill in decisions + content inputs (`Reel_Factory_Inputs_Needed.md`) | **YOU** | Sheet filled |
| 3 | Build the 6 blocks + base template; render a 5 s sample of each | Me → **YOU approve** | You say "this is the look" or send fixes |
| 4 | Build `edl.py` + `compile.py` + one scene-plan schema; update the Director prompt | Me | First full 30–40 s reel from IMG_0020 renders |
| 5 | Build `qa_check.py` + `vision_qa.py`; wire gates and the "fix:" loop | Me | QA catches 3 deliberately broken reels, passes the good one |
| 6 | Cost fixes: monthly cap, ledger, updated cost model | Me | Ledger total = sum of job costs; cap tested |
| 7 | Run 3 real clips end to end | **YOU** run on your Mac; I fix what breaks | 3 approved reels, measured cost/time/fix rounds |
| 8 | Decide what comes next (Opus vs Sonnet, B-roll, autopilot, more blocks) | **YOU** | Written in DECISIONS.md |

Estimated: phases 1–6 about 8–12 working sessions, then real use.

---

## 6. Practical note: where the work happens

- I can't run anything on your Mac. Drive works for reading files but is a poor place to edit code (no history, no review).
- **Best setup:** a private GitHub repo. I write and test the code here (scripts, templates, schema, tests with a short sample clip), you `git pull` on your Mac and run the command. Large video stays local and is ignored by git.
- Alternative: I prepare the files and you copy them into the Desktop folder by hand. It works but is slower and error-prone.
