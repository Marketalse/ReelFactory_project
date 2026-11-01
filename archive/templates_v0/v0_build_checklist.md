# Reel Factory — V0 build checklist

Goal: turn the current manifest into one reviewable reel with the smallest useful surface area.

## Inputs
- Existing clip on disk
- Word-level transcript
- Brand kit from `style/brand.json`
- Slot manifest from `templates/v0_manifest.json`
- Local planner: `qwen3:8b`

## Build order
1. Draft the `word_pop_caption` scene.
2. Draft the `counter` scene.
3. Add one FX only: `fx_whip_blur`.
4. Finish with `cta_card`.
5. Check that the reel still reads cleanly in vertical format.

## Rules
- Use Readex Pro.
- Keep Arabic RTL legible.
- Keep the hook short.
- Keep the counter large and high-contrast.
- Do not add extra FX.
- Do not add Telegram or any other intake workflow.
- Do not add a persistent handle footer; only the CTA card may carry the handle.
- Keep spend minimal while preserving quality.

## Acceptance criteria
- One 30–45 second reel can be assembled from the manifest.
- The reel uses the approved brand kit.
- The reel includes the four V0 slots exactly once each.
- The reel uses one FX only.
- The reel is ready for Hesham to approve or request fixes.

## Next decision needed from Hesham
- Approve the look when ready.
- Confirm the spend cap before expanding beyond V0.
