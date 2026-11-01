# Reel Factory — operating cost per reel (2026-11-01, SHAK-290)

Calculator: `python3 cost_model.py` (edit the scenario dict to change assumptions). Prices from the provider catalogue on the Nous route ($/MTok in/out): Opus 5 5/25, Sonnet 5.5 2/10, Haiku 5.5 0.1/0.5. Only Claude calls cost money; whisper, HyperFrames, MediaPipe, qwen3:8b, Telegram are $0 marginal.

## Why Vision showed $11.16 for 60 s
Measured: one full 1080x1920 frame to Sonnet 5.5 = ~2,730 input tokens ≈ **$0.0063**. A 60 s clip at 30 fps is 1,800 frames: 1,800 x $0.0063 = **$11.40** (your $11.16 ≈ 1,761 frames). So the number matches "every frame sent at full size". That is inferred from arithmetic; I could not find the screen where you saw it. Vision must never see every frame.

Image tokens scale with size (measured): 1080 wide 2,728 tok, 720 -> 1,233, 540 -> 737, 384 -> 387.

| Vision method (60 s take) | Frames | Cost |
|---|---|---|
| Every frame, 1080 wide (what produced ~$11) | 1,800 | ~$11.40 |
| 1 fps, 1080 wide | 60 | ~$0.38 |
| 1 fps, 540 wide, short output | 60 | ~$0.18 |
| Keyframe every 2 s, 540 wide (recommended) | 30 | ~$0.09 |
| Scene-change keyframes only | ~12 | ~$0.03 |

## Per-reel total (60 s take -> 24-45 s reel)
| Step | Lean | Expected | Heavy |
|---|---|---|---|
| ASR (whisper, local) | $0 | $0 | $0 |
| Transcript fix (Haiku 5.5) | $0.001 | $0.001 | $0.001 |
| Shot log (Sonnet 5.5) | $0.03 | $0.09 | $0.34 |
| Director (Opus 5, incl. thinking tokens) | $0.16 (1 pass) | $0.77 (1+2 revisions) | $1.55 (1+2) |
| QA stills (Sonnet 5.5, 8 per pass) | $0.03 | $0.11 | $0.21 |
| Render / Telegram | $0 | $0 | $0 |
| **Per reel** | **$0.23** | **$0.98** | **$2.09** |
| 12 reels / month | $2.70 | $11.73 | $25.08 |
| 24 reels / month | $5.39 | $23.46 | $50.15 |

## What is measured vs assumed
- Measured: per-frame image tokens and Sonnet cost; unit prices; Haiku/Opus call works.
- Assumed (not yet measured): Director prompt 12K/20K/40K tokens, output + thinking tokens, number of revision passes, 70% of the prompt served from cache on revisions, QA 8 stills/pass, 3 passes max (SOP fix-loop cap). Replace with real figures after the first Opus 5 pass; log real spend in `dashboard/add_expense.py` (ledger is still empty: no spend recorded yet).
- Biggest lever: **Opus 5 thinking tokens** (billed as output at $25/MTok). Set low/medium reasoning effort for the Director; high effort is the default and is what pushes "Heavy" to ~$1.5.
- Sonnet 5.5 reasoning is mandatory (cannot be turned off): cap `max_tokens` and ask for terse output, or frames cost more than the table says.

## Not included
- Hermes' own agent tokens while it runs the SOP (this chat's model). Not measurable from the pipeline; it is the next-largest cost if the agent narrates a lot.
- Failed/re-run attempts beyond 2 revisions, stock assets, subscriptions, electricity.

## Controls to enforce in code
1. Vision input = keyframes only, resized to 540 (shot log) or 720 (QA); hard cap 40 frames per job, abort above.
2. Per-job budget guard: stop and ask if projected job spend > $2.00 (proposal, needs your cap).
3. Director prompt cap 20K tokens (warn 40K, abort 60K), reasoning effort low/medium.
4. Log every call's `usage.cost` to the dashboard ledger.

## Update 2026-11-01 (SHAK-291): approved budget + measured keyframe result
- **Hesham approved (chat):** Heavy-level spend is fine, band **$23-$50 per month for ~24 reels**, provided results match the Opus 5 Director expectation. Working monthly cap = **$50**. Derived per-job stop = $50/24 = **$2.08**: a job projected above that stops and asks.
- **Measured, real clip (IMG_0020 proxy, 60 s):** `scripts/keyframes.py` picked 31 frames @540 wide; ONE batched Sonnet 5.5 call returned a valid 31-row shot log. Real cost **$0.0558** (22,114 in / 1,154 out tokens, reasoning 0 with effort low) vs **$11.20** for every frame: ~200x cheaper. The $0.0587 estimate was within 5%.
- Finding: this talking-head clip has **zero scene changes**, so frames add little information. Interval can widen to 3-4 s (20-15 frames, ~$0.03-0.04) for single-shot footage.
- Why batching beats per-frame: one call, one set of output/reasoning overhead.
- Shot-log cost is no longer the issue; Director (Opus 5) is ~80% of per-reel cost, so expected band stays ~$1/reel (lean $0.23, heavy $2.09). Revised expected using measured shot log: ~$0.94/reel.
