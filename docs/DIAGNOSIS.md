# Reel Factory — Full Diagnosis

Reviewed 2026-11-01. Sources: the flowchart, plus the Drive folder (AGENTS.md, SOP.md, EXECUTION_PLAN.md v3, model/*, dashboard/*, scripts/reel.py, the 8 status/index files, templates/*, reels/v0-draft/*, both job folders in jobs/, spikes/, references/, .reel-agent/*). I also ran model/cost_model.py.

---

## 0. The verdict in one paragraph

The project has a lot of planning and no reel yet. Four days in, it has 8 status files, 3 rulebooks and a 7-phase plan, but **no code turns a plan into a video**. `scripts/reel.py` stops at a validated `scene_plan.json` and says so: *"NOT done by this pipeline: assemble/render and the visual QA gate."* No HyperFrames composition template exists. The only HTML that renders is a 3-second flash spike. Vision QA has no code. The cost model leaves out the step most likely to cost the most. The creative spec asks for a visual change every 1–3.5 s, but the input is one static talking-head shot and the asset library is empty.

The fix: stop adding documents, build the one missing piece (a **deterministic compiler: scene_plan.json → HyperFrames HTML**), and cut the MVP down to what a talking-head clip can support.

---

## 1. Idea and MVP

| # | Issue | Evidence | Impact |
|---|---|---|---|
| 1.1 | **The creative target doesn't match the input.** The spec wants a hard visual change every 1–4 s (B-roll, screen recordings, icon rows, compare sliders, 3D emoji). The real footage is one continuous talking head. | `shot_log.json` for IMG_0020: same framing in all 13 frames, notes like "near-identical to 16s". COST_MODEL: "this talking-head clip has **zero scene changes**". | The Director is asked for something it has no material to make. It has to fill gaps with `needs_asset` placeholders or frozen stills. |
| 1.2 | **The asset library is empty.** | `templates/library.json`: all 4 packs `"items": []`, `"license": "to be checked"`. reel.py's MOVES list says no B-roll library exists and screen recording is unavailable. | Moves 4, 6, 7-sticker, 9, 11 and 14 can't be used. That leaves about 4 real moves. |
| 1.3 | **The "AI-tool explainer" formula is for a different kind of reel.** It needs separately captured screen proof, a grey wall, a mic in frame, and a script written ahead of time. Your footage is unscripted Iraqi-dialect talk about online stores and customer service. | references/ai-tool-reel-teardown.md, production steps 2–4 | Treating it as an "optional mode" adds rules and doesn't help. |
| 1.4 | **The MVP is too big.** V0 is supposed to be a thin slice, but the plan spans 15 moves, ~10 templates, freshness/cooldown rules, monthly registry refresh, autopilot and a fix-loop engine. | EXECUTION_PLAN §3–5, AGENTS.md §6 | Effort goes into rules for reels that don't exist. The visual ledger is empty (`[]`). |
| 1.5 | **The V0 scene plan breaks the project's own rules.** It has an 8.5 s counter beat with no number (`"number": ""`), a 19.6 s unbroken talking-head section, and uses a "glitch/mesh overlay" (probably a camera artefact) as the hook. | reels/v0-draft/scene_plan.json | V0 can't pass the validator in reel.py, which caps a hold at 3.5 s and forbids a counter without a spoken number. |

**What the MVP should be:** raw talking head → tighter cut (pauses and false starts removed) → word-pop Arabic captions with one lime keyword → 2–4 punch-ins on strong words → two-tone hook title at 0 s → one kinetic text card → CTA card. All of that comes from the clip itself. It covers most of the value and needs no outside assets.

---

## 2. Process and steps

| # | Issue | Evidence |
|---|---|---|
| 2.1 | **The core step is missing: nothing assembles or renders.** The flowchart's steps 6–9 (Build → Verify → Preview → Render) have no code. reel.py's last stage is `report`. | reel.py `STAGES = [... "plan","validate","report"]`. The report writes "NOT done by this pipeline: assemble/render and the visual QA gate." |
| 2.2 | **The pipeline can't cut.** The SOP says "cut pauses over 0.4 s, false starts and filler", but the Director prompt requires `src_in = s0 + t_in` with "audio is the source audio, uncut". The reel can only be one continuous range of the take. | reel.py PLAN_PROMPT, last paragraph |
| 2.3 | **"Cutaways" over continuing speech will look broken.** `keyframe_still` holds a still of your face while your voice keeps playing, so the mouth freezes while the audio talks. | reel.py MEDIA SOURCES: "keyframe_still … audio keeps playing" |
| 2.4 | **Two scene-plan schemas, and nothing consumes either.** V0 uses `scenes[].slot` (word_pop_caption, counter…). reel.py uses `beats[].media.type/move/caption`. The flowchart talks about `data-hold`, `id="seg-hook"` and a timing block. | templates/v0_scene_plan_example.json vs reel.py PLAN_PROMPT |
| 2.5 | **Gate 1 is a CLI flag, and a stale pick won.** The new Opus selects gave A = 0–22 s with a hook line. reel.py silently used the old `job.json` pick instead: A = 0–24 s, `hook_line: ""`. | jobs/2026-11-01-img0020-pipeline/selects.json vs chosen_select.json |
| 2.6 | **The transcript-verification gate isn't enforced.** The SOP says to set `transcript.verified: true` before selects. The job shows `"verified": false` and the pipeline ran anyway. | job.json `transcript.verified: false` |
| 2.7 | **The number gate is weak.** `numbers_spoken()` only matches digits, ألف and مليون. Spoken numbers like اثنين، ثلاثة، ضعف and "2x–4x" said in words slip through. Select C was about "2x to 4x sales". | reel.py `numbers_spoken` |
| 2.8 | **There's no feedback loop.** The plan promises "fix: …" re-runs 03→06, but nothing reads Hesham's feedback into a re-plan. `job.json.feedback` is never used. | reel.py, job.json |
| 2.9 | **Folder layout differs in every document.** Jobs live in `jobs/<id>/` (AGENTS, SOP, reel.py), `reels/<slug>/` (plan, flowchart) or `~/Movies/Reels/` (flowchart). Brand lives in `style/brand.json` or `config/brand.json` (SOP). | Cross-doc comparison |
| 2.10 | **AGENTS.md assumes the root is a HyperFrames project.** It isn't: there's no `index.html`, `package.json` or `meta.json` at the root. `npm run check` can't run there. `scripts/compare_renders.py` (named in the flowchart) doesn't exist. | Drive file listing |

---

## 3. Agents and assigned models

**Current roster:** Haiku 5.5 corrects the transcript, Opus 5 picks selects and directs (with one repair call), Sonnet 5.5 writes the shot log and does Vision QA, qwen3:8b is the "local planning LLM", and whisper does ASR. Hermes, the orchestrating agent, runs the SOP.

| # | Issue |
|---|---|
| 3.1 | **The "only one LLM call" rule is dead but still shown as non-negotiable.** The flowchart (brief + rule cards) still says it. EXECUTION_PLAN says it was superseded on 2026-11-01. A real job now makes 4–6 paid calls (fix, selects, shot log, plan, repair, QA). |
| 3.2 | **qwen3:8b has no job.** Every status file says "continue with qwen3:8b", but no code calls it. reel.py uses only Claude. Either remove it or give it a real job (for example, offline fallback for selects). |
| 3.3 | **The ASR choice contradicts itself 4 ways.** The flowchart says faster-whisper large-v3-turbo. The SOP prefers `hyperframes transcribe`. MODELS.md says whisper.cpp ggml-medium. reel.py defaults to `--asr-model medium`. The SOP says "always use a large model; small models garble Iraqi dialect". The P0 bake-off tested large-v3 on a reference reel, not on your Iraqi footage. |
| 3.4 | **The shot log pays Sonnet to describe 13 near-identical frames.** Face box, eyes and energy can come from MediaPipe face mesh locally for $0. Use the VLM only when the footage has real variety. |
| 3.5 | **Opus for selects is over-spec'd.** It used 755 tokens in and 20 reasoning tokens. Sonnet (or Haiku plus your Gate 1 pick) does this fine. Keep Opus for the Director only, if at all. |
| 3.6 | **The real "agent" is unconstrained.** AGENTS.md tells Hermes, an LLM, to hand-write each composition. The flowchart's own mistakes list shows what that produces: placeholder compositions, CSS overlays on one continuous video, missing media IDs, debug text in the MP4. An LLM hand-writing HTML is the root cause, not something better rules will fix. |
| 3.7 | **The routing depends on a third-party key.** Calls go through Nous (`~/.hermes/auth.json → agent_key`), and prices are "measured" from Nous `usage.cost`. That's fine, but the long-prompt and cache tiers are marked unverified, and the ffmpeg path is hard-coded to darwin-arm64. |

**Recommended roster:** whisper large-v3-turbo (local) → Haiku transcript fix → **you** confirm names and numbers → Sonnet selects → Gate 1 → local MediaPipe face/energy analysis → Opus *or* Sonnet Director (A/B on 3 clips, as P2 already planned) → **deterministic compiler (no LLM)** → deterministic QA → Sonnet Vision QA on 6 stills → Gate 2.

---

## 4. Vision QA concept

| # | Issue |
|---|---|
| 4.1 | **It doesn't exist.** There's no script, prompt, rubric or pass/fail schema. reel.py doesn't call it. |
| 4.2 | **Its status contradicts itself.** The flowchart says "Vision QA gate enforced". The SOP says "required before preview". Every status file and library.json say "approved later… not a blocker". |
| 4.3 | **It's pointed at the wrong failures.** Most of what it's meant to catch can't be seen in 8 stills or can be measured exactly without AI: dead stretch >3 s, frozen video, lip-sync, loudness, blank first frame, "every beat has a different source", URLs returning 200, and debug text. |
| 4.4 | **The cost model assumes 3 QA passes and AGENTS.md allows 10 fix cycles.** Nothing caps QA spend per job. |

**Redesign as two layers:**

1. **Deterministic QA (free, always runs, blocks preview):**
   - `hyperframes lint/check --json`
   - Each beat has a unique media element ID (from the compiled HTML)
   - `ffmpeg freezedetect` (n=0.003, d=3), `blackdetect` (first frame + overall), `scdet` for change frequency
   - `ebur128` loudness target (−14 LUFS ±1)
   - `ffprobe` duration within ±0.2 s
   - Caption coverage: every transcript word in range appears in the DOM
   - grep for `pending|TODO|placeholder|debug|lorem`
   - Numbers burned on screen must be in your confirmed list
2. **Vision QA (Sonnet, about 6 stills at 720 px, one batched call, JSON rubric):** only for things a human eye judges.
   - Caption legibility against the background
   - Captions covering the face or mouth
   - Arabic shaping (broken joins, reversed text)
   - Safe-zone overlap
   - Brand look
   - Each check gets a 1–5 score with the frame timestamp. Fail if any score is below 3. At most 2 fix loops.

---

## 5. Rules and guidelines

| # | Issue |
|---|---|
| 5.1 | **There are 3 rulebooks plus 8 status files, and several claim to be the source of truth.** `REEL_FACTORY_CANONICAL_TASK_MAP.md` says it is "the single working map". MASTER_INDEX, FINAL_INDEX, LIVE_QUEUE, CONTROL_BOARD, TASK_MAP, EXECUTION_STATUS and STATUS_SNAPSHOT all repeat the same 5 lines. |
| 5.2 | **"There is no reason to stop… keep moving" is written into every status file.** For an autonomous agent, this rule produces exactly what you see: more status files and no output. Replace it with "stop and report when blocked; one deliverable per session". |
| 5.3 | **Telegram is both in and out.** EXECUTION_PLAN §1 and P6 still end in a "Telegram preview". The status files say removed. |
| 5.4 | **The spend cap is both set and pending.** COST_MODEL and models.json say $50/month and $2.08/job, approved. The status files and library.json say "spend cap pending". |
| 5.5 | **Several rules have no enforcing code:** the freshness/cooldown rules (5-reel cooldown, 3 registry candidates per slot), the monthly refresh, and lessons promoted to `[RULE]`. Park them until reel #10. |
| 5.6 | **Generic HyperFrames boilerplate fills about half of AGENTS.md.** Skill tables, Tailwind and Remotion porting, Figma, slideshow. That's context cost on every agent session. |
| 5.7 | **The flowchart is out of date.** Its "Current Status: P0 complete, first reel in preview, Vision QA gate enforced" is false. In reality, P0-B1 (text-behind matte) isn't proven, no reel has been built, and Vision QA doesn't exist. |
| 5.8 | **The housekeeping rules aren't followed.** Drive contains `.DS_Store`, `__pycache__`, a full `harakah/.git` and node_modules, all against your own "heavy tooling outside Desktop" rule. Harakah is cloned but not wired into anything. |

---

## 6. Cost tracker and operating cost

I ran `model/cost_model.py`: lean $0.225, expected $0.978, heavy $2.090 per reel.

| # | Issue | Evidence |
|---|---|---|
| 6.1 | **The per-job cap has no headroom.** The cap is $2.08, the model's heavy case is $2.09, so a heavy reel trips the guard mid-job. | $50/24 = 2.083 < 2.090 |
| 6.2 | **The model leaves out paid calls the code actually makes:** the Opus **selects** call, the Opus **repair** call (up to 9,000 output tokens, roughly $0.23 worst case), and **re-running the shot log** when the range changes. | reel.py `st_selects`, `st_validate`; job cost.json shows shot log paid twice ($0.0315 + $0.0337) |
| 6.3 | **The biggest real cost isn't tracked: the Hermes agent's own tokens.** COST_MODEL admits this ("next-largest cost"). Under AGENTS.md, Hermes reads skills, writes HTML, runs check loops and reads snapshots for every reel. With Opus-class pricing, that can be several dollars per reel, more than the whole pipeline. | COST_MODEL "Not included" |
| 6.4 | **Nothing enforces the monthly cap.** The budget guard is per job only. Nothing sums `expenses.json` against $50. | reel.py `Ctx.llm`; add_expense.py |
| 6.5 | **The ledger corrupts itself over time.** `add_expense.py` silently drops rows past 200 (`rows[-200:]`), so totals will under-report. The JSON note says to archive, but the code deletes. Category text still says "Claude Haiku 5.5 (Director)". | add_expense.py |
| 6.6 | **Partial runs are logged as "ok".** The img0020 run never reached `plan`, but both ledger rows say "reel.py run (ok)". | expenses.json rows 3–4; timing.json ends at `shotlog` |
| 6.7 | **The budget guard underestimates Arabic.** It estimates input tokens as `chars / 2.6`, but Arabic tokenizes much denser than English, so input is under-counted. Use the provider's token-count endpoint, or `chars / 1.5` for Arabic. | reel.py `Ctx.llm` |
| 6.8 | **`max_tokens` also covers reasoning.** Plan and repair calls cap at 9,000. At medium or high effort, thinking can eat that and truncate the JSON. It stops safely, but the money is already spent. | reel.py |
| 6.9 | **Cost is tracked in 4 places that don't agree:** per-job `cost.json`, `expenses.json`, COST_MODEL.md tables, and the flowchart's "$23–50/month". | — |

**Actual spend to date:** $0.157 total. The ledger matches the job cost.json, apart from the duplicate shot-log charge.

**Realistic target with the recommended architecture**, where no LLM writes HTML:
- Haiku fix: ~$0.001
- Sonnet selects: ~$0.01
- Director: Sonnet ~$0.05, or Opus ~$0.25 at low effort
- Repair: ≤ $0.10
- Vision QA, 2 passes: ~$0.04

That's **about $0.15–0.45 per reel**, or **$4–11/month at 24 reels**, plus whatever human-in-the-loop agent sessions you choose to run.

**Cap settings I'd use:**
- Per-job: soft $1.00 (warn), hard $2.50 (stop)
- Monthly: hard $50, enforced from the ledger
- Log every agent session's token cost as its own row in the ledger

---

## 7. What's actually proven vs. claimed

| Item | Status |
|---|---|
| ffmpeg ingest → 1080×1920 SDR proxy | ✅ Works (proxy.mp4, probe.json, silences, loudness exist) |
| Whisper transcript with word timestamps | ✅ Works (medium model, 146 words / 60 s, `verified: false`) |
| Haiku transcript fix | ✅ Works (5 of 146 words changed, $0.001) |
| Opus selects | ✅ Works ($0.014) |
| keyframes.py + batched Sonnet shot log | ✅ Works ($0.03 per run) |
| Director scene plan on real footage | ❌ Never run (no scene_plan.json in either job) |
| Validator | ⚠️ Code exists, never exercised on a real plan |
| scene_plan → HyperFrames composition | ❌ **Does not exist** |
| Render of a real reel | ❌ Never done (only a 3 s text-only flash spike) |
| Vision QA | ❌ Does not exist |
| Text-behind matte (P0-B1) | ⚠️ Spike PNGs only; "installed, NOT yet proven" |
| Arabic shaping (Harakah) | ⚠️ Cloned, not integrated |
| Preview / Gate 2 / feedback loop | ❌ Not built |
| Learn (ledger, lessons) | ⚠️ Ledger empty; lessons hand-written |

---

## 8. What you need for a working final product

### Target architecture

```
ingest (✅) → ASR large-v3-turbo (fix default) → Haiku fix (✅) → [YOU: confirm names/numbers]
→ selects (Sonnet) → [GATE 1] → EDL: cut pauses/fillers, re-time words (NEW, deterministic)
→ local face/energy analysis (MediaPipe, replaces paid shot log for single-shot footage)
→ Director → scene_plan.json (ONE schema, only moves that have a template)
→ validator (✅, extend) → COMPILER scene_plan → HyperFrames index.html (NEW, deterministic, no LLM)
→ deterministic QA (NEW) → Vision QA rubric (NEW) → preview → [GATE 2: approve / "fix: …"]
→ render + verify (NEW) → ledger + lessons
```

### Build order (each step ends in something you can watch)

**Step 1: clean up (1 session)**
- Delete the 8 status/index files. Keep one `STATUS.md` with Now / Next / Blocked / Decisions and nothing else.
- Fix the flowchart so it shows the current model roster, the current status, and the real cap.
- Pick one folder convention (`jobs/<date>-<slug>/`) and one brand path (`style/brand.json`).
- Remove the "never stop" rule.
- Move generic HyperFrames boilerplate out of AGENTS.md. Keep the role, brand, render contract and limits.

**Step 2: fixed templates, made once by hand and approved by you (2–3 sessions)**

Six HyperFrames sub-compositions, each driven only by data attributes or JSON:
1. `face_cut` — proxy segment with optional punch-in crop
2. `word_pop_captions` — RTL, Harakah-shaped, keyword in lime, safe zones built in
3. `hook_two_tone` — visible at 0.0 s
4. `text_card` — kinetic headline
5. `flash` — lime, one word
6. `cta_card` — علقلي متجر + promise + handle

Gate: you approve one still and a 5 s clip of each.

**Step 3: EDL + compiler, the missing core (2–3 sessions)**
- `edl.py`: the chosen range plus silences.txt and filler/false-start words gives a list of kept segments. It re-times the word timestamps onto the reel timeline. Pauses over 0.35 s are cut, and the cuts are hidden with punch-in alternation (100% → 115% → 100%).
- `compile.py`: scene_plan + EDL + transcript produce `index.html`, filled only from Step 2 templates. Every media element gets a unique ID, and there's no free-text HTML.
- Change the Director's schema to beats over EDL segments, and remove `keyframe_still`-over-speech.

Gate: one real 30–40 s reel from IMG_0020, rendered.

**Step 4: QA (1–2 sessions)**
- `qa_check.py` runs the deterministic checks (§4 layer 1).
- `vision_qa.py` makes one batched Sonnet call with a JSON rubric (§4 layer 2).
- Both write `qa_report.json` and block preview on failure. At most 2 automatic fix loops, then hand back to you.

**Step 5: gates and feedback (1 session)**
- Gate 1, the numbers/names confirmation and Gate 2 become one short message each, with a reply format of `A|B|C`, `ok` or `fix: …`.
- A `fix:` reply is fed into the Director as a revision with the previous plan.
- The render step adds a versioned filename, ffprobe duration check, and ledger append.

**Step 6: costs (in parallel)**
- Update cost_model.py with the selects, repair and agent-session lines.
- Enforce the monthly cap from `expenses.json`, remove the 200-row truncation, and fix the "ok" status on partial runs.
- Don't re-run the shot log if the range only grew by ±2 s.

**Step 7: run 3 real clips, then decide (P7)**
- Measure time per reel, cost per reel, fix rounds and approval rate.
- Only then add B-roll and asset packs, text-behind, compare slider, freshness rules, and autopilot.

### Decisions only you can make
1. **Opus or Sonnet as Director?** Run the P2 A/B on 3 clips once the compiler exists. Until then, the Director's quality can't be seen.
2. **Is B-roll in scope?** If yes, someone has to source and license a starter pack of about 50 tagged clips. Without it, the "change every 1–3 s" goal has to come from punch-ins, captions and cards.
3. **Who runs the pipeline day to day:** an autonomous Hermes agent, or you running one command per stage? The second is cheaper and more predictable until the compiler is stable.
4. **Confirm the cap structure:** $1 soft / $2.50 hard per job, $50 per month.
