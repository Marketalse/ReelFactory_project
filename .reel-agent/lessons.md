# Reel Factory — Lessons
Read at the start of every job. Max ~150 lines. Format: one line, verb first, with evidence.

## Hesham's taste
- Keep reels clean: no CTA, no follow ask, no handle on screen; attention first, sales later (Hesham, 2026-11-01, docs/DECISIONS.md)
- Use `علقلي متجر` as the CTA comment keyword for store-related reels, only once the CTA is turned back on (chosen 2026-10-31)

## Known failures
<!-- error signature → cause → fix -->
- Never install ASR into system Python: faster_whisper import failed on a NumPy binary mismatch → use `hyperframes transcribe`, whisper.cpp, or an isolated `.venv-asr` (run 2026-10-31, IMG_0011)
- Never edit iPhone HEVC/HDR/60 fps originals directly: tone-map + proxy to 1080x1920 30 fps H.264 via scripts/ingest.sh (run 2026-10-31, IMG_0011)
- Never treat a 3 s text-only teaser as proof of a real reel: it only checks layout, not decode, sync, captions, or render time (run 2026-10-31, hf_flash)
- Put ffmpeg's folder on PATH for every child tool; HyperFrames render failed "FFmpeg not found" when it lived only in ~/.hermes/tools (2026-11-01, job img-0061-2, PR #19).
- Read review/render_error.log before guessing; npm update notices hid the real render error twice (2026-11-01, job img-0061-2).
- Fold face pieces under 0.3 s into a neighbour; compile refused the plan "seg0: face cut shorter than 0.3 s" (2026-11-01, job smuggling, PR #15).

## Locked formats
- Build from proxy footage, not the original HEVC/HDR source.
- Ask for the story choice only when transcript-based selects are ready.
- When the CTA is on: final card only; never a persistent handle footer.

## Workflow boundaries
- Keep the project lean: prefer local files, local preview, and low spend before adding tools or automation.
- Keep progress in `dashboard/tasks.json` and chat only (no Multica, no Telegram; AGENTS.md §8).

## Try next
- For AI-tool explainer reels, use the formula in `references/ai-tool-reel-teardown.md`: 5 layout modes (A Split, B Full B-roll, C White card, D Face punch-in, E CTA), 32–42 s, visual change ≈ every 1 s, captions 1–3 words word-by-word, CTA comment "WORD".

## Library changelog
- Added `awaiting_footage` as the first job-status checkpoint.

## Retired
- First-run steps for IMG_0011 (ingest.sh by hand, transcription fallbacks): done; the dashboard runs these now (2026-11-01).
- Telegram intake and workflow automation (removed from the project 2026-11-01).
