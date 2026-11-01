# Reel Factory — Lessons
Read at the start of every job. Max ~150 lines. Format: one line, verb first, with evidence.

## Hesham's taste
- Use `علقلي متجر` as the CTA comment keyword for store-related reels (chosen 2026-10-31)
- Keep the project lean: prefer local files, local preview, and low spend before adding tools or automation.

## Known failures
<!-- error signature → cause → fix -->
- Never install ASR into system Python: faster_whisper import failed on a NumPy binary mismatch → use `hyperframes transcribe`, whisper.cpp, or an isolated `.venv-asr` (run 2026-10-31, IMG_0011)
- Never edit iPhone HEVC/HDR/60 fps originals directly: tone-map + proxy to 1080x1920 30 fps H.264 via scripts/ingest.sh (run 2026-10-31, IMG_0011)
- Never treat a 3 s text-only teaser as proof of a real reel: it only checks layout, not decode, sync, captions, or render time (run 2026-10-31, hf_flash)

## Locked formats
- Build from proxy footage, not the original HEVC/HDR source.
- Ask for the story choice only when transcript-based selects are ready.
- Keep the CTA on the final card only; no persistent handle footer.

## Workflow boundaries
- Keep progress updates in chat and local project files unless Hesham explicitly asks for Multica updates.
- Keep Vision QA in the plan once Hesham approves it; do not drop it unless he says to remove it.
- If Hesham asks to stop Multica use, do not create, update, or reopen Multica issues for Reel Factory; keep tracking in chat and local files only.

## Try next
- Run `scripts/ingest.sh inbox/IMG_0011.MOV online-store` to build the proxy and job folder.
- Use the HyperFrames built-in transcription path first, then whisper.cpp, before falling back to faster-whisper.
- For AI-tool explainer reels, use the formula in `references/ai-tool-reel-teardown.md`: 5 layout modes (A Split, B Full B-roll, C White card, D Face punch-in, E CTA), 32–42 s, visual change ≈ every 1 s, captions 1–3 words word-by-word, CTA comment "WORD".

## Library changelog
- Added `awaiting_footage` as the first job-status checkpoint.

## Retired
- Telegram intake and workflow automation.
