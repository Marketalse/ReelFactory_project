# Reel Factory — model roster (v2, 2026-11-01, SHAK-289)

Changed by Hesham because reel quality was poor and the SOP was not completing. Machine-readable twin: `models.json`.
Route: existing Hermes **Nous** login (`https://inference-api.nousresearch.com/v1`); no key stored here. DeepSeek stays excluded.

| Role | Model | Where | Status (checked 2026-11-01) |
|---|---|---|---|
| Local planning LLM | `qwen3:8b` | local | unchanged, working |
| Vision / shot log | **`anthropic/claude-sonnet-5.5`** (was qwen3-vl:4b; keep 4b as offline fallback) | cloud | real frame described correctly, $0.0062/frame |
| Vision QA (stills review) | **`anthropic/claude-sonnet-5.5`** (same) | cloud | same call path |
| ASR engine (audio → words + timestamps) | whisper.cpp `ggml-medium` via `hyperframes transcribe` | local | unchanged, working |
| Arabic transcript correction | **`anthropic/claude-haiku-5.5`**, alt `haiku-4.5` | cloud | model IDs live, text call OK |
| Other-language transcript correction | **`anthropic/claude-haiku-5.5`** | cloud | model ID live, text call OK |
| Director (scene plan JSON) | **`anthropic/claude-opus-5`** (was Haiku 5.5) | cloud | ID live, text call OK |
| Renderer | HyperFrames | local | unchanged, working |
| Text-behind matte | MediaPipe (rembg fallback) | local | unchanged, installed, NOT yet proven (P0-B1) |

## Important correction to the request: Claude cannot transcribe audio
A direct audio call to Haiku 5.5 and Haiku 4.5 on this route returned HTTP 404, and Claude returns no word timestamps anyway. So "transcription" is two steps:
1. **Audio → words + timestamps:** the local whisper engine (unchanged).
2. **Words → clean transcript:** Haiku 5.5 (Haiku 4.5 as alternate) fixes Iraqi-dialect spelling, brand names and English terms from the whisper text. It never hears the audio and never changes timestamps. SOP step C already asks for this fix; it is now a model step, not manual.

## Rules that follow from the swap
- Only text transcripts and sampled stills go to the cloud. Raw/proxy video and audio never leave the Mac.
- Opus 5 Director: one call per pass, JSON only, prompt target ~20K tokens (warn 40K, abort 60K). Measured price $5 in / $25 out per MTok — about 50x Haiku 5.5. Estimate (not measured), incl. thinking tokens: ~$0.16-0.30 per Director pass, ~$0.77 per reel with two revisions - see `COST_MODEL.md`. Long-prompt tier price not verified: re-check before any prompt >100K tokens.
- Sonnet 5.5 vision: ~2.7K input tokens per frame (measured). Image tokens scale with width (1080: 2.7K, 540: 0.7K); send resized keyframes only. Full-frame video analysis costs ~$11 per 60 s: see `COST_MODEL.md`.
- Spend cap number is still **unset** (plan §2 item 4). Running these at volume needs the cap.
