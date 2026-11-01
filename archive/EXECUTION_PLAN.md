# Reel Factory — Execution Plan (v3, 2026-10-29)

Source: `Downloads/Reel Factory Blueprint.md` + Hesham's answers + `reference_spec.md` + **reference_spec_v2.md** (base layer unchanged; creative layer added). Tracking (Multica, project **Reel Factory**): SHAK-169 canonical → SHAK-170 umbrella → SHAK-171…189, SHAK-190.
v1 archived at `archive/EXECUTION_PLAN_v1.md`; v2 superseded by this file.
**Status: plan approved in part (see §2). Nothing published, nothing paid.**

## 1. The system in one picture

```
raw clip ─▶ 01 clean+ASR ─▶ 02 shot log ─▶ 03 DIRECTOR (JSON: moves, fx, template refs) ─▶ 04 assemble ─▶ 05 QA stills ─▶ 06 render ─▶ Telegram preview
(script)       (whisper + Haiku 5.5 fix) (Sonnet 5.5)  (Opus 5, 1 call; token budget guards)  (script)      (lint + Sonnet 5.5) (script)       │
                                  ▲                                                 │                           ▼
                                  └────────────── "fix: …" re-runs 03→06 from cache ◀────────────────  ok / fix
```
**Models changed 2026-11-01 (SHAK-289): see `model/MODELS.md`.** The old "only step 03 is an LLM call" rule is superseded: Haiku 5.5 corrects the transcript text, Sonnet 5.5 reads stills (shot log + QA), Opus 5 is the Director. Audio, video, rendering and matte stay local.

## 2. Decisions (Hesham, 2026-10-29) — still open items flagged

| # | Decision | Status | Notes |
|---|---|---|---|
| 1 | Director = **Claude Opus 5** (changed 2026-11-01 from Haiku 5.5; SHAK-289) | ✅ approved by Hesham | DeepSeek stays excluded. Opus 5 measured at $5 in / $25 out per MTok (~50x Haiku 5.5). Prompt rules in §7. |
| 2 | Brand kit: #242834 / #B6FF00 / #7D53FF + Readex Pro | ✅ approved | brand.json v2 (4 colours incl. negative #FF6B4A); lime flash beats 1–2/reel; coral for bad state only (derived, V0 confirm). |
| 3 | Reference reels | ✅ received | 6 MP4s + v2 spec in `references/`; creative layer (4 Pinterest reels) measured. |
| 4 | Spend | ✅ "okey" in principle | **Cap set 2026-11-01 (SHAK-291): $50/month (~24 reels, band $23-$50); per-job stop $2.08.** Old note: hard cap number was needed before P1 (blueprint estimate $10–30 for Sonnet 5.5 template building). I will stop and ask before crossing whatever you name. |
| 5 | Disk | ✅ answered | ~184 GiB free (7% used) after Adobe cache removal. |
| 6 | Adobe apps + /Library services | ⏳ blocked (SHAK-189) | User-level removal done (cache 135 GB + logs + prefs + agents ≈ 141 GB). Remaining: `/Applications/Adobe*` apps (~23 GB) + `/Library` services — **needs one admin login**. |
| 7 | Project files on Desktop | ✅ done | `~/Desktop/Reel-Factory/`. Heavy tooling (node_modules, venvs, models) stays outside Desktop (§6). |
| 8 | Telegram = channel after build | ⏳ planned | New phase P6. Footage goes to `inbox/` (Plan A), NOT Telegram upload. |

Open: **spend cap number; handle + CTA words; Adobe admin step; Telegram channel location** (optional); derived text/surface colours in brand.json (V0 confirm).

## 3. Reference layer — two sets, two jobs

**Set 1 · base layer (measured, unchanged):** six reels 720×1280/30 fps, durations 62.8/56.5/59.1/37.2/72.1/29.8 s; hard cuts 9/8/1/2/3/0. Keep: split layout (card top, face 35–45% bottom), keyword captions, counters/bar charts/price swap, logo pairs, UI mockups, comment-CTA end card, Western digits.

**Set 2 · creative layer (measured, new):** four Pinterest reels; **a hard visual change every ~1–4 s** vs base layer's 20–60 s. That gap is what reads as "creative" to a young audience.

**Set 3 · AI-tool explainer formula (teardown, new):** 32–42 s reels, 8–10 layout cuts, visual change ≈ every 1 s. Five layout modes: A Split, B Full B-roll, C White card, D Face punch-in, E CTA. Hook is a two-line title + claim; proof body is 3–5 beats with screen proof; CTA is comment "WORD". Captions 1–3 words, word-by-word sync; one keyword per phrase in italic serif accent colour. See `references/ai-tool-reel-teardown.md`.

**The 15 moves** (recorded in `references/reference_spec_v2.md` §2.2; cost = director's choice only, render runs locally, 0 LLM tokens):
- **T templates the Director calls:** 1 word-pop captions (white words, keyword turns lime), 2 mixed weights per word (Readex Pro wght 200↔700, variable axis approved), 3 text-behind subject (MediaPipe matte — spike P0-B1), 4 concept B-roll cutaway, 5 solid flash + 1 word, 10 kinetic type card (lime glow on slate), 11 icon row on beat (violet discs), 12 editorial interlude, 14 before/after compare slider (violet divider, lime "After" label), 15 two-tone bold caption (white + lime).
- **FX transitions:** 6 whip-blur zoom into screen record, 8 ghost/echo, 9 light-leak tint (violet→coral), 13 object motion-blur swipe.
- **A/S assets & shooting:** 4 concept B-roll cutaway asset library, 7 sticker on face (Fluent Emoji 3D), S1 leave headroom, S2 hold still 1 s after each key line, S3 one big reaction per reel, S4 plain background.

**Creative rhythm (tune on the golden set):**
- something on screen changes every 1–2 s (word-pop)
- visual change (cutaway/card/zoom) every 3–5 s
- signature move 1 per ~10 s, never two back to back
- hook (0–3 s): two-tone caption + punch-in + one signature move
- lime flash: max 2 per reel, payoff numbers only
- end: comment-CTA card (base layer)

Example 60 s beat map: `0s hook → 3s word-pop → 6s B-roll cutaway → 10s text-behind → 15s word-pop → 18s icon row → 22s whip into screen → 30s kinetic chapter → 34s compare slider → 40s flash payoff → 45s word-pop → 52s light-leak → 55s CTA`.

## 4. What changes in the execution plan

- **V0 templates:** word-pop caption (replaces static caption card), counter + lime flash, CTA, + **one FX** (light leak or whip-blur) to prove transitions.
- **P0-B** adds the 3-second text-behind Subject test (MediaPipe matte) — the riskiest creative move on 16 GB and the most valuable.
- **P1 template order:** add moves 3, 4, 10, 11, 14; drop checklist and timeline to later.
- **New one-time asset libraries** (licence-checked): light leaks, 3D icons/emoji, 3D objects, tagged B-roll — `style/assets/` with a licence file per pack.
- **Director schema:** `"fx"` and `"move"` fields added; validator enforces the rhythm table (no back-to-back signature moves, at most 2 flashes/reel).
- Set 1's palette/dot grid/handle are not ours (see brand.json); the creative layer's creators' handles/watermarks/footage/layouts are not ours either — copy techniques only.
- AI-tool explainer formula and prompts are recorded in `references/ai-tool-reel-teardown.md` and `references/ai-tool-prompts.md`.

## 5. Phases and gates (v3)

Gate rule: a phase starts only after the previous gate passes; each gate is something shown to you.

| Phase | What | Gate (evidence) |
|---|---|---|
| **P0** Decide & de-risk (≈3–4 sessions) | P0-B1 text-behind Subject test (3 s, MediaPipe matte); P0-B2 HyperFrames + RTL/counter/Readex Pro; ASR bake-off; VLM 4B/8B timing; Vision QA approval | HyperFrames go; ASR chosen; VLM latency measured; text-behind matte ≥1 clean frame; Vision QA explicitly approved |
| **V0** Thin vertical slice (≈3–4) | word-pop caption, counter + lime flash, CTA, one FX; hand-written JSON → one 30–45 s reel from existing clip + transcript | Hesham says "this is the look" or sends fixes |
| **P1** Template library → ~10 (≈4–6) | moves 3/4/10/11/14 added; checklist/timeline dropped to later; licensed asset packs | each template renders on-brand from sample JSON; licence files present |
| **P2** Director (≈2–3) | schema with fx/move fields + rhythm validator; prompt-size guard (§5); 3-transcript test Opus 5 vs local Qwen (Haiku 5.5 as cheap baseline) | valid plans 3/3; measured cost/reel; Hesham confirms model |
| **P3** Pipeline + skill (≈3–4) | one command clip → draft MP4; number-confirmation gate; captions_editable.md | 3 real clips → 3 drafts + check report |
| **P4** QA critic (≈2) | lint first, VLM on 8 stills second; max 2 fix loops | catches 5 broken plans, passes 3 good |
| **P5** Autopilot (≈3–4) | inbox watcher, fix-loop engine, fix-log cap | 3 manual runs, then 1 live inbox→draft cycle |
| **P6** Telegram go-live (≈2–3) | previews ≤50 MB, ok/fix, notifications | one full cycle on your phone |
| **P7** Review checkpoint (1) | measured cost/time/fix rounds/approval rate | decide: stay Opus 5 / step down to Sonnet 5.5 or Haiku 5.5 / go local / more templates / stop |

Total estimate: ~22–30 sessions ≈ 4–6 calendar weeks.

## 6. Project layout

```
~/Desktop/Reel-Factory/
  EXECUTION_PLAN.md      archive/ (v1)
  style/                 brand.json · fonts/ReadexPro…ttf + OFL · assets/ (licensed packs, licence file per pack)
  references/            ref1…ref6 .mp4 (copies; originals remain in Downloads), reference_spec.md, reference_spec_v2.md
  templates/             moves/ (T), effects/ (FX), assets/ (A)
  inbox/                 footage intake + scripts/intake.py + README
  reels/<slug>/          source/ · cache/ · captions_editable.md · v1/ v2/ …
  dashboard/             expenses.json · dashboard.html · add_expense.py · README.md
Outside Desktop:          ~/.hermes/tools/reel-factory/  node_modules, Python venv, Chrome, models (Ollama keeps its own ~/.ollama)
```
Reason: heavy dependency trees on Desktop slow Finder/Spotlight and bloat backups. iCloud Desktop sync is off on this Mac (checked), so Desktop is local-only.

## 7. Director rules — now Opus 5 (see `model/MODELS.md`); the table below is the former Haiku 5.5 price sheet, kept for the cheap baseline — enforced in code

**Opus 5 (2026-11-01, measured from provider usage on the Nous route):** $5 in / $25 out per MTok. Long-prompt tier and cache prices NOT verified — re-check before relying on them. Estimate (unmeasured): ~$0.15–0.20 per Director pass, ~$0.35–0.55 per reel incl. 2 revisions. The ≈$0.005 figure below applied to Haiku 5.5 only.

| | ≤ 100K-token prompt | > 100K-token prompt |
|---|---|---|
| Input | $0.10 / MTok | $0.50 / MTok |
| Output | $0.50 / MTok | $2.50 / MTok |
| Cache write 5m / 1h | $0.125 / $0.20 | $0.625 / $1.00 |
| Cache read | $0.01 | $0.05 |

- Tokenizer ≈ **30% more tokens** than Haiku 4.5. Any figure from the blueprint or Haiku 4.5 must be multiplied by ~1.3.
- Prompt length counts cache reads/writes; each request priced on its own — one request over 100K pays higher rates on everything.
- Rules: target ~20K tokens (warn 40K, abort 60K, never approach 100K); stable cacheable prefix (style.md + move catalogue + rhythm rules), transcript and shot notes last; style.md fix log capped ~2K tokens and regularly consolidated; measure tokens with the provider's own count (token-spending plugin); adaptive thinking bills as output → low effort; no manual budget_tokens/sampling parameters; handle stop_reason refusal.
- Cost estimate: ≈ $0.005 first pass / $0.003 warm; reel (1 + 2 revisions) ≈ $0.010–0.013. Real figures from P2 measurement; routing through any provider may price differently — P2 verifies.

## 8. Disk space (read-only record — nothing deleted without your OK)

Current: **184 GiB free / 460 GiB (7% used)** — verified after the Adobe cache removal. Sizes: Qwen3-VL 4B = 3.3 GB, 8B = 6.2 GB; Jais-ASR-MLX 4-bit = 4.5 GB (8-bit ~7 GB); Whisper large-v3-turbo already cached (1.5 GB).
Minimum path ≈ 8 GB (Whisper cached, Qwen3-VL 4B, HyperFrames + Chrome ≈ 1 GB); full path ≈ 24 GB (8B + Jais fallback + PyTorch + working space). Raw phone clips are the hidden cost (IMG_9966.MOV alone is 1.6 GB). Final reels ≈ 65 MB each.

## 9. Scope and boundaries (unchanged)
No publishing/scheduling; spend only up to a cap you state; no new accounts or credentials without approval; sources never overwritten; Telegram only to your private chat unless you choose otherwise; background services only after approval.

## 10. Next actions (when approved)
1. **You:** the spend cap number; the handle + CTA words.
2. **Me (no spend, no big downloads):** P0-B1 text-behind Subject test + P0-B2 HyperFrames spike + ASR bake-off with the faster-whisper turbo model already cached.