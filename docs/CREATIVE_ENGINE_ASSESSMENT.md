# Creative Engine — technical assessment (2026-11-03)

Answers section 7 of Hesham's "AI Creative Video Production Engine" brief. Written from the code as it is today (branch `v2`), not from the docs.
**How to read the verdicts:** BUILT = exists and has tests. PARTLY = exists but does less than the brief asks. MISSING = nothing in the code.
**What I have NOT proven:** quality on real footage. Everything marked BUILT is proven to run (362 unit tests, 40 audit checks, one real reel by Hesham), not proven to be *good editing*. The only true quality test is his judgement of drafts.

## 1. Stage by stage

| Brief stage | Verdict | Where it lives today |
|---|---|---|
| 01 Speech analysis | PARTLY | `scripts/lib/speech_intel.py` (fillers, repeats, pauses, speed, unfinished sentences, per-word loudness, 4 separate scores), `transcript.py`, steps `transcribe`, `fix` (Haiku word fix + proofread) |
| 02 Story / narrative | PARTLY | step `selects` (story pick + hooks + main message, `editorial.py` scoring), step `outline` (`scripts/lib/outline.py`: format, sections, titles from his words) |
| 03 Cutting + continuity | PARTLY | step `tighten` (`tighten.py`, AI removes whole lines, reasons saved in `tighten.json`), step `edl` (`edl.py`, rule cuts), `editorial.py` continuity flags |
| 04 Highlight planning | PARTLY | inside step `plan`: `director.py` (moments, punch-ins, emphasis marks `!` from loudness), T133 highlight words, `pack.py` |
| 05 Creative editor | PARTLY | `hfbuild.py`, `templates/blocks/*` (20 blocks incl. `pack_frame`, `motion_card`), `compile.py`, `sfx_mix.py` |
| 06 Director QA | PARTLY | step `critic` (`critic.py`: 8 stills of the draft, Haiku, report only), `scripts/qa_check.py` (free deterministic checks), `render_guard.py` (video check, voice-vs-words drift, silence) |

### Stage 01 — what is missing or weak
- **Blanket pause removal (verified).** `config/rules.json → cut.remove_pauses_over_s = 0.35`: *every* pause over 0.35 s goes, and fillers go by rule (`edl.py`). The brief's critical rule ("do not remove every pause; keep dramatic ones") is **not met**. `speech_intel.py` already measures pause length and loudness, but `edl.py` does not use it to tell a dramatic pause (before a hook, after a number, after a question) from dead air.
- No emotion / topic-change analysis (the file says so itself: "needs a model").
- Key moments are found later (selects), not in this stage, and are not saved as a list with reasons.

### Stage 02 — what is missing or weak
- `selects` picks **one continuous range** of the take (candidates A/B/C). **Re-ordering recorded segments is not possible**: `tighten.py` forbids it by design, `edl.py` only cuts inside the range. The brief's items 4–6 (rebuild structure, rearrange without changing meaning) are MISSING.
- **No "suggested pickup / voice-over / on-screen clarification" output** (brief's critical rule for missing content). MISSING.
- Weak hook, missing context, confusing transitions are not reported as warnings. MISSING.

### Stage 03 — what is missing or weak
- Continuity is **rule-based on text only** (`editorial.py`: cut inside a sentence, very tight cut, filler start). **Nothing looks at the picture or sound at the cut point** (face, gesture, audio jump). The shot log samples key frames about every 2 s, not at cuts. MISSING.
- Only AI removals have a reason (`tighten.json`). Rule cuts (pauses, fillers, retakes) are saved without a per-cut explanation ("why, what removed, meaning preserved, needs repair?"). PARTLY.
- **Clean-cut checkpoint:** the building block exists (`compile.py layer="video"` = him, cuts + zooms + sound, no graphics) but it is only used at Approve for the CapCut layers. There is **no plain-cut draft and no approval gate before the creative stage**. PARTLY (parts exist, gate missing).

### Stage 04 — what is missing or weak
- Moments have no `why` and no category (critical info / number / opinion / question / emotion / comparison / CTA). The director picks blocks, and the choice cannot be traced back to a reason. MISSING.
- Sound effects are wired (T127) but chosen by block, not by the highlight's category.

### Stage 05 — what is missing or weak
- "Speaker is the hero": face is protected by safe zones and by the Format Pack face window; `text_behind` checks the face is centred. But **six blocks are full-screen and hide the face by design** (`director.FULL_SCREEN`), and face position is one static value per reel (`face_cy`), **no tracking**. PARTLY.
- No check that a card does not cover the face/mouth at the moments it is shown (the safe-zone test checks templates, not each reel). MISSING.
- Creative intensity: `creative_brief.py` has a style (educational | fast | storytelling) that goes into the prompts as one line. No rule-level effect (zoom frequency, flash count, transition style). PARTLY.

### Stage 06 — what is missing or weak
- The critic sees **only stills of the draft**. It never compares with the original recording or the clean cut. It **only reports**; nothing acts on its issues. PARTLY.
- **Information integrity:** numbers must be spoken (`director.resolve`), pack titles are built from his words, captions must equal the spoken words (`qa_check.py`). Not covered: a deterministic proof that **the final speech is a source-ordered subset of the original words** (nothing reworded, nothing reordered, no word clipped). Cheap and local: the word map from `edl.py`/`media_index.py` already has the data. MISSING.
- **Targeted correction:** quick re-render of changed 6 s pieces exists (`segcache.py`), but the only "fix" entry point is a whole re-plan (`--fix`). The Director cannot send back "scene m4 only". MISSING.

### Cross-cutting
| Brief requirement | Verdict | Note |
|---|---|---|
| Shared creative memory | PARTLY | Data is spread over `transcript_asr.json`, `speech_intel.json`, `editorial.json`, `tighten.json`, `outline.json`, `shot_log.json`, `timeline.json`, `scene_plan.json`, `validation.json`. `content_intel.py` (T102) already merges some into one file. **Extend that file, do not add another one** (AGENTS.md: no new index/status files). |
| Word timing + confidence, silence detection | BUILT | `transcript.py`, `speech_intel.py` |
| Source ↔ final timestamp mapping | BUILT | `media_index.py`, `edl.py` re-timed words |
| Edit decision list | BUILT | `edl.py`, `timeline.json`, `editorial.json` |
| Scene-level re-render | PARTLY | `segcache.py` caches pieces; no scene-targeted correction loop |
| Decision logs | PARTLY | `tighten.json`, `validation.json`; none for cuts by rule, none for visuals |
| Audio-video sync check | BUILT | `render_guard.sync_and_silence` |
| Feedback / learning | PARTLY | `learning.py` (posted results → ≤3 lessons), `.reel-agent/lessons.md`, `brand_memory.py`. Does not record decision-level outcomes (which cut he restored, which card he removed). |
| Preview visual reasoning | PARTLY | `critic.py` (stills, report only) |
| No self-modifying code | BUILT | by design (AGENTS.md §6, §11) |

## 2. How information should flow (no new service needed)
```
source clips ──ingest──> media_index.json (never edited)
   │
   ├─ 01 speech_intel.json  ──┐
   ├─ 02 selects/outline    ──┤  all merged into ONE shared file: content_intel.json (extend T102)
   ├─ 03 edl + tighten      ──┤  + cut_log (one entry per cut: why / removed / meaning kept / repair needed)
   │        └── CLEAN CUT draft (compile layer="video") ── GATE A: checks + Hesham may approve
   ├─ 04 treatment plan     ──┤  moments with category + why
   ├─ 05 timeline → compile → render (existing)
   └─ 06 qa_check + render_guard + integrity proof + critic ── GATE B: failures name the scene → targeted fix
```
Each box reads the shared file and writes its own part; code validates every AI decision against real timestamps and the word list before it is used (the pattern already used in `tighten.py`, `outline.py`, `director.resolve`).

## 3. How a decision becomes an edit
Already true today: AI points at word numbers → code turns that into times (`director.at()`), blocks (`hfbuild.stamp`), zooms (`director.face_cuts`), sounds (`sfx_mix`). The brief's example ("umm", shorten pause, subtle zoom, animate UNDERSTAND YOUR AUDIENCE, emphasize WASTING YOUR BUDGET) maps to: `edl` removes the filler → `director` punch-in on the emphasis word → `pack` highlight bar or `text_card` with words taken from his transcript → `sfx_mix`. What is missing is the **written reason** at each step.

## 4. Changes, file by file (each with an acceptance test)

### A. Can be done now (no new architecture)
| # | Change | Files / functions | Acceptance test |
|---|---|---|---|
| A1 | **Keep dramatic pauses.** Classify each pause (before hook, after a number/question, before an emphasised word) from `speech_intel` and keep up to a limit; remove the rest | `edl.py` (pause removal), `speech_intel.py`, `config/rules.json → cut` | Unit test: a 0.9 s pause after a number is kept at ≤0.5 s, a 0.9 s pause mid-sentence is cut; real reels: Hesham compares old vs new cut |
| A2 | **cut_log**: one entry per cut (rule or AI) with why / what removed / meaning kept | `edl.py`, `tighten.py`, Edit page | Test: every removed word range appears in exactly one entry; Edit page shows it |
| A3 | **Integrity proof** (free): final words are a source-ordered subset of the original words; no cut inside a word | new `scripts/lib/integrity.py`, called from `qa_check.py` | Test with a doctored timeline (reordered, clipped word) must fail |
| A4 | **Clean-cut checkpoint**: render `layer="video"` as a low-res draft before `plan`, run A3 + sync checks, show it on the dashboard | `compile.py`, `reel.py` new step `cleancut`, dashboard Reels page | Test: step produces `review/clean_540p.mp4`; a job with a clipped word stops here, not after rendering graphics |
| A5 | **`why` + `category`** on every director moment, saved in the decision log | `director.py` (PROMPT, `resolve`), registry | Test: a moment without a reason is rejected; log lists all |
| A6 | **Face-overlap check per reel**: deterministic, using shot-log face boxes and each card's rectangle | `qa_check.py`, `shot_log` | Test: a card placed over the face box is flagged with its time |
| A7 | **Critic → targeted fix**: issues carry a time; map to the scene; re-plan only that scene; use `segcache` to re-render only its pieces | `critic.py`, `reel.py st_critic`, `director.py`, `segcache.py` | Test with mock critic returning one issue: only that scene's file changes |
| A8 | **Intensity controller**: map style → numbers (punch-in gap, flash max, SFX density) | `creative_brief.py`, `config/rules.json`, `director.py` | Test: "fast" gives more moments per minute than "educational" |
| A9 | Record decision outcomes (cut restored, card removed on the Edit page) | `learning.py`, `manual_edit.py` | Test: removing a card writes one outcome line |

### B. Needs a larger change
| # | Change | Why it is big |
|---|---|---|
| B1 | **Re-order recorded segments** (narrative reconstruction) | Redesign `selects` + `tighten` + `edl` (they assume one ordered range); needs a continuity check at every new join and a rule that meaning is not changed; high risk of misleading edits, so it needs Hesham's approval flow |
| B2 | **Picture/sound analysis at each cut point** | Extra frames at every cut for the shot log (AI cost) or local face/gesture detection (new dependency); thresholds need a test set |
| B3 | **Face tracking** (moving face position for zooms and overlays) | New component (face detector over the whole clip), changes `face_cuts` and every block that uses `face_cy` |
| B4 | **Pickup / voice-over suggestions** | New output in the story step plus a place in the dashboard to approve; no content is ever generated into his mouth |
| B5 | **Director comparing original vs clean cut vs final with vision** | Needs sampled frame pairs across three videos; costs more per reel; do after A3/A4 prove the cheap checks |

## 5. Testing approach
1. **Unit tests** for every rule (as now).
2. **Nasty-AI harness** (`pre_uat_report/tools/e2e.py NASTY`, `suite.py nasty`): extend with the failures a real AI shows (card past the end, unknown block, answer in words; found on 2026-11-03).
3. **Golden set:** 5–10 of Hesham's real reels with his marked judgements ("this cut is good / clipped / too tight"). Thresholds for the quality gates (brief §5) are set **from this set, not guessed**. I cannot make this set without him.
4. **Draft review stays the final judge:** the dashboard comments and "posted results" feed `learning.py` (small sample, never overrides his comment).

## 6. Recommended order (agrees with the brief's own advice)
1. A3 integrity proof, A2 cut_log, A4 clean-cut checkpoint (editorial foundation first).
2. A1 dramatic pauses (this is the biggest quality gap against the brief; test on his reels before it becomes default).
3. A5 why/category, A6 face overlap, A7 targeted fix.
4. A8, A9.
5. Only then B1–B5, one at a time.
Cost: A1–A9 add no paid AI except small extra tokens for A5 (a sentence per moment). B2/B5 add real per-reel AI cost and need his approval of the budget first (AGENTS.md §6).

## 7. Ideas borrowed from how Higgsfield's agent works (added 2026-11-03)
Checked against Higgsfield's own connector instructions (workflow "katana", read-only, no credits spent), not only against the article. Confirmed there: a per-job **task contract** (explicit locks + creative freedoms), an **energy map** of a reference (cuts, flashes, shake bursts, camera moves, hits, with rates per second) that is carried into the plan and **checked on the output**, **three motion reviews** (rhythm/timing; spatial movement/continuity; detail/polish) before and after render, a **finite spend cap with a price quote before any paid job**, **only recorded CC0 sound effects** (Kenney, OpenGameArt; "do not synthesize SFX in code"), and **"never generate a graphic scene as video: models blur text"** (graphics are drawn in code from time alone). I did not test Higgsfield's output quality.
| Idea | Reel Factory today | Upgrade | Cost |
|---|---|---|---|
| Locks file per reel | brief + AGENTS rules + glossary, checked in different places | `locks` + `freedoms` in the per-reel plan data (`content_intel.json`), checked by `qa_check.py` (e.g. "no text", "keep my colours", "no CTA") | free |
| Energy map | `ref_learn.py` measures picture changes/min but only the colours are used | extend it to cuts, zooms, flashes, shakes, sound hits per second; director gets them as targets; QA compares output vs target | free (ffmpeg) |
| Three review passes | one critic on 8 stills, report only | rhythm = rates vs target (free); spatial = face/safe-zone overlap (free); polish = vision look at start/peak/end of each moment; repair only the failed scene | small Haiku cost |
| Recorded sounds | `make_sfx.py`: tones and noise made by ffmpeg, no recordings | real CC0 recordings (Kenney etc.) via the asset pack, mapped to roles (hit, whoosh, pop, ding, riser); plus a code-driven shake on strong hits | free |
| Graphics drawn from time alone | already the HyperFrames/GSAP design (and the Lottie player) | nothing to change; confirms the approach | — |
| Generated stills (not video) for one hero scene | library pictures matched by vision (T123) | optional: generate one still when no library picture fits; needs a price quote and Hesham's per-reel yes, and a DECISIONS entry (AGENTS §5, §6) | credits |
Order: plain-cut checkpoint + dramatic pauses + integrity proof (section 6) → locks + energy map → recorded sounds + shake → three reviews → generated stills.
