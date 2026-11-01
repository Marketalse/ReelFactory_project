# Reel Factory — Execution Plan (draft v1)

Source: `~/Downloads/Reel Factory Blueprint.md` (blueprint v1). Tracking: Multica SHAK-169 (canonical) → umbrella issue → phase issues.
Status of this document: **DRAFT for Hesham's approval. Nothing below has been installed, downloaded, spent or published.**

---

## 1. What the blueprint says, in one line

Hesham films → scripts clean + transcribe + log → **one cheap LLM (the Director) writes a small JSON scene plan** → a template library renders it (HyperFrames, HTML→MP4) → QA looks at 8 stills → preview lands in Telegram → "ok" or "fix: …".
The real insight: *design once into templates, then the daily model only fills blanks.* Of the "six agents", only the Director is an LLM; the rest are scripts and two small local models.

```
raw clip ─▶ 01 clean+ASR ─▶ 02 shot log ─▶ 03 DIRECTOR (JSON) ─▶ 04 assemble ─▶ 05 QA stills ─▶ 06 render ─▶ Telegram preview
 (script)    (script/local)  (local VLM)   (only LLM call)       (script)      (lint+VLM)      (script)         │
                                  ▲                                                │                            ▼
                                  └────────────── "fix: …" re-runs 03→06 from cache ◀──────────────  ok / fix
```

## 2. Reality check — where the blueprint and this Mac disagree

| # | Blueprint assumes | What I verified | Consequence for the plan |
|---|---|---|---|
| 1 | "Your PC", VRAM tiers (8 / 12–16 / 24 GB GPU) | **MacBook Pro M2 Pro, 16 GB unified memory, no NVIDIA**, 49 GB disk free (89% full) | Use Apple-Silicon paths (Ollama/Metal, MLX). 16 GB is shared with Chrome + macOS → **models load one at a time, never concurrently with a render**. |
| 2 | Director = DeepSeek V4.1 Flash | **DeepSeek is excluded (privacy)** — standing rule | Director = **Claude Haiku 5.5** (already configured in Hermes) or local Qwen. The blueprint's "$0.01–0.05/reel" figure was DeepSeek-based → **re-measure, don't reuse**. |
| 3 | Install `hermes-video-editor` as a helper | Licence is **PolyForm Noncommercial**; Hesham's reels serve a business brand. A community skill `video-editor` from the same repo is already installed (SHAK-168, ffmpeg runtime never verified) | **Do not depend on it.** FFmpeg + the existing `reel-production` / `cut-video` skills already cover cut, loudness, captions. Flag SHAK-168 for a keep/remove decision. |
| 4 | Build the pipeline from scratch | Already exist locally: `reel-production` (ASS Arabic captions, boundary ground-truthing, QA), `cut-video`, `find-broll`, `tiktok-hooks`; SHAK-68/73 produced a motion-graphics reel with Pillow+ffmpeg; `token-spending` plugin for cost measurement | **Reuse, don't rebuild.** Steps 01 and 06 are mostly assembly of existing parts. |
| 5 | Week-2 builds 10 templates *before* any pipeline exists | Highest-risk assumptions (HyperFrames on this Mac, Arabic ASR quality, Director output quality) are untested | **Reorder: spikes → thin vertical slice (3 templates) → expand.** Failing fast on week 1 beats polishing 10 templates on a renderer that doesn't suit. |
| 6 | "Hands-off, only shoot and approve" | Standing rules: ASR output is never verified; **wrong digits on screen are the costliest error**; Iraqi dialect ASR is unreliable (best published Arabic ASR averages ~23% WER on benchmark sets, not Iraqi-specific) | Add a **number/claim confirmation gate** (counters, prices, %) before render. Autopilot = "approve", not "unreviewed". |
| 7 | `hermes skills install hyperframes` / `hermes plugins install advanced-delegation` | HyperFrames is real (heygen-com/hyperframes, very active, ships its own agent skills via its CLI — the exact Hermes install command is **unverified**). advanced-delegation is real, official, needs Hermes ≥0.22.5 — installed Hermes is **exactly 0.22.5** | Verify install paths in spike P0-B. **advanced-delegation is optional**: a single Director call can be a plain script with a model setting; add the plugin only if multiple routed sub-agents are really needed. |
| 8 | Palette "cream/coral/charcoal" in the references | Reference look belongs to another creator; purple/yellow/black is a *proposal*, not approved branding | Brand kit is a **P0 decision**, not an assumption. |
| 9 | Cost: $10–30 one-time Sonnet 5.5 template build | Plausible but unmeasured | Treat as **estimate with a hard cap that Hesham sets**; track with `token-spending`. |

Verified facts used: HyperFrames repo active (release v0.8.217 dated today); Jais-ASR (Apache-2.0) has MLX 4-bit (4.5 GB) / 8-bit (7 GB) builds but needs a pinned, patched `mlx-vlm` + PyTorch (fiddly); `qwen3-vl:8b` = 6.2 GB on Ollama, needs Ollama ≥0.12.7; Ollama is installed, **no models pulled yet**; `faster-whisper` and `mlx-whisper` are not currently importable in the system Python (reel-production notes say they were used before, likely in a venv — to re-verify).

## 3. Phases, gates and deliverables

Gate rule: **a phase starts only when the previous gate passes.** Each gate is something I can show you, not a claim.

### P0 · Decide & de-risk  (≈ 3–4 working sessions)
| Item | What | Done when (evidence) |
|---|---|---|
| P0-A Decisions | Hesham answers 6 questions (§4) | Written answers recorded in `style.md` header |
| P0-R Reference inventory | Locate the 6 reference reels; extract per-format feature spec (layout %, caption cadence, cuts, CTA pattern). Existing SHAK-73 manifest covers a *different* set of 9 Pinterest refs — reconcile, don't duplicate | `reference_spec.md` + contact sheets, counts computed in code |
| P0-B HyperFrames spike | Install in an isolated folder; render a 1080×1920 / 30 fps / 60 s composition with Arabic RTL caption, keyword highlight, one counter | Arabic letters join correctly in a decoded frame; **render time and peak RAM measured on this Mac**; go/no-go vs. continuing Pillow+ASS (SHAK-73 route) |
| P0-C ASR bake-off | One of Hesham's real Iraqi clips (SHAK-68 source is on disk): faster-whisper large-v3 vs mlx-whisper large-v3-turbo vs (only if both fail) Jais-ASR-MLX-4bit. Hand-corrected 60 s reference | WER/CER table + word-timestamp drift check; pick one primary model |
| P0-D Local vision spike | `ollama pull qwen3-vl:4b` then `:8b` (~4–6 GB download, needs OK) ; time one 8-still QA pass while nothing else runs | Latency + memory measured; decide whether VLM QA is useful or a deterministic lint is enough |

**Gate P0:** decisions made + HyperFrames go + ASR chosen. If HyperFrames fails, fallback is code-rendered frames (the SHAK-73 route) with the same JSON/template architecture — the architecture survives, only the renderer swaps.

### V0 · Thin vertical slice  (≈ 3–4 sessions)
Smallest end-to-end proof, **hand-written JSON, no Director yet**:
- 3 templates only: **keyword caption card**, **counter**, **CTA** (+ split frame: card top / face bottom).
- Input: an existing clip + transcript already on disk (SHAK-68 material).
- Output: one 30–45 s reel in brand kit; `style.md` v0 (safe zones, caption cadence 2–4 s).

**Gate V0:** Hesham watches it and says "this is the look" (or gives fixes). Nothing else is built until he does.

### P1 · Template library → ~10  (≈ 4–6 sessions; **needs spend approval**)
Order by how often references use them: caption card, counter, bar chart, price swap, logo pair, checklist, timeline, chat mockup, comparison, CTA. Strong model (Sonnet 5.5) builds each against reference frames. Each template = HTML/CSS + JSON schema + sample JSON.
**Gate P1:** every template renders on-brand from its sample JSON; a catalogue page lists them.

### P2 · Director  (≈ 2–3 sessions)
- Scene-plan JSON schema + validator (rejects unknown templates / out-of-range timings).
- Director prompt = `style.md` + template catalogue (stable prefix, cacheable) + transcript → plan.
- Run on Haiku 5.5 and a local Qwen; compare on 3 real transcripts.
- Measure real tokens/cost with `token-spending`.
**Gate P2:** valid plans on 3/3 clips; **measured** cost per reel; Hesham picks Director model.

### P3 · Pipeline & skill  (≈ 3–4 sessions)
- One command: raw clip → draft MP4. Steps 01 (clean/cut/ASR, reusing `cut-video` ground-truthing), 02 (face box + shot notes), 04 (assemble), 06 (render + −14 LUFS + caption text).
- Cache layout next to the clip: transcript, shot notes, plan, version folders (`v1/ v2/`), source never overwritten.
- **Number-confirmation gate**: any digit/price/percentage on screen is listed for Hesham to confirm before the final render.
- New skill `reel-factory` (links to `reel-production`, doesn't duplicate it).
**Gate P3:** 3 real clips → 3 draft MP4s, one command each, with a check report (frame count, loudness, safe-zone check).

### P4 · QA critic  (≈ 2 sessions)
Deterministic lint first (safe zones, text overflow, contrast, font present, caption overlap), VLM on 8 stills second. Max 2 auto-fix loops back to the Director.
**Gate P4:** critic catches 5 deliberately broken plans and passes 3 good ones.

### P5 · Autopilot  (≈ 3–4 sessions; **needs approval for background service**)
Inbox folder watcher (launchd, same pattern as the gateway), Telegram preview to Hesham's private chat (Bot API video limit is 50 MB → compressed preview; verify), `ok` / `fix:` handling, log every fix into `style.md`.
**Gate P5:** 3 reels run through the *manual* pipeline first; then one full inbox → Telegram → ok cycle observed live. No auto-publishing, ever.

### P6 · Review checkpoint  (1 session)
Per-reel measured cost, wall-clock time, # of fix rounds, approval rate. Decide: stay on Haiku, go local, add templates, or stop.

**Total (estimate):** ~20–28 focused sessions ≈ 4–6 calendar weeks, not 4 — mostly because the blueprint omits the spikes and the number-confirmation gate. Label: planning estimate, not measured.

## 4. Decisions needed from Hesham (P0-A)

1. **Director model** — Haiku 5.5 (recommended; already configured, no new account) vs fully local Qwen (free, weaker) vs test both in P2. DeepSeek stays out.
2. **Brand kit** — 3 colours (purple/yellow/black proposal? or something else), Arabic font (IBM Plex Sans Arabic / Readex Pro / Tajawal — Tajawal already used in SHAK-73), handle (`@hesham_alshakarchi` per reel-production), CTA word(s).
3. **Where are the 6 reference reels** (files or links)? The blueprint was built from them; the board only holds a different 9-reel Pinterest set.
4. **Spend cap** for template building (blueprint estimates $10–30 with Sonnet 5.5) — I will not exceed what you approve.
5. **Local model downloads**: OK to pull Qwen3-VL (4–6 GB; disk is 89% full) and possibly Jais-ASR (4.5–7 GB)?
6. **SHAK-168 `video-editor` skill** (non-commercial licence): remove, or keep disabled for personal experiments only?

## 5. Risks (ranked)

1. **Iraqi-dialect ASR quality** → wrong caption words. Mitigation: bake-off, human check, never auto-burn digits.
2. **16 GB memory pressure** (Chrome render + models). Mitigation: strictly sequential steps; measured in spikes.
3. **Template quality ≠ reference quality** — taste is the bottleneck, not tokens. Mitigation: V0 gate with Hesham before scaling.
4. **Over-building** (six "agents", delegation plugin, watcher) before one reel works. Mitigation: gates above; plugin optional.
5. **Third-party sources** in the blueprint are blogs; some figures (prices, "Haiku 5.5 on full reel edit") are unverified. Mitigation: verify each tool at install time; re-measure costs.
6. **Licensing/brand**: copy structure, not the other creator's look, handle or claims.

## 6. Approval boundaries (unchanged)

No publishing/scheduling; no spending beyond approved cap; no new accounts; source files never overwritten; Telegram only to Hesham's private chat for review/blockers; background services only after approval.

## 7. Immediate next step (when approved)

Run **P0-R + P0-B + P0-C** — no spend, no downloads beyond a local npm/Python install in an isolated folder under `~/Movies/Reels/reel-factory/spikes/`. P0-D waits on your OK for the model download.
