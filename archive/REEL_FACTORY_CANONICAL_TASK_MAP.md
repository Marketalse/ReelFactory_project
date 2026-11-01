# Reel Factory canonical task map

This is the single working map for the project. Use it as the active reference; the other status files are supporting notes.

## Current working state
- The project stays active.
- Nothing is stopped unless Hesham explicitly changes the plan.
- Vision QA stays in the plan and is approved later-stage work.
- Telegram is removed.
- The local planning model is `qwen3:8b`.
- The reusable JSON library and V0 scaffolding are already in place.
- Harakah integration note added for Arabic text handling.
- `AGENTS.md` now includes `awaiting_footage` as the first job status.
- V0 input sheet now reflects the awaiting_footage flow and CTA type choice.

| Area | Status | Next concrete step | Blocker |
|---|---|---|---|
| **P0 — ASR bake-off** | Active | Keep the chosen local planning path around `qwen3:8b` and use it for planning while the reel work continues. | None |
| **P0 — HyperFrames on this Mac** | Active | Continue building from the local project files and keep the path executable. | None |
| **P0 — Vision QA** | Approved later | Keep it in the plan so it can be added once the first slice is ready. | None |
| **V0 — Thin vertical slice** | Ready to fill | Fill the V0 input sheet with the real hook, counter, CTA, and clip values, then build the first reel. | Waiting on you: look approval + spend cap + actual inputs |
| **P1 — Template / JSON library expansion** | Ready next | Use the reusable JSON library as the source of truth for assets and template slots. | Waiting on you: spend cap |
| **P2 — Director + JSON planning** | Planned | Use the schema and scene-plan pattern once V0 is stable. | None |
| **P3 — Pipeline + reel-factory skill** | Planned | Convert clip to draft MP4 once the template path is stable. | None |
| **P4 — QA critic** | Planned | Add frame/layout checks after the build path is stable. | None |
| **P5 — Autopilot** | Optional later | Only add automation if it proves useful. | None |
| **P6 — Telegram** | Removed | Do not use Telegram intake; footage goes directly into HyperFrames. | Removed by decision |
| **P7 — Review checkpoint** | Later | Measure cost, time, fix rounds, and approval rate after the system is running. | None |

## Canonical files
- `templates/library.json` — reusable library source of truth
- `templates/v0_manifest.json` — V0 template manifest
- `templates/v0_build_checklist.md` — V0 build checklist
- `templates/v0_input_sheet.md` — fill-in sheet for reel inputs
- `templates/v0_scene_plan_example.json` — example scene plan
- `reels/v0-draft/job.json` — first reel job object
- `reels/v0-draft/report.md` — handoff report
- `reels/v0-draft/scene_plan.json` — concrete V0 scene plan
- `references/harakah-integration.md` — Arabic text handling note
- `REEL_FACTORY_FINAL_INDEX.md` — navigation index
- `REEL_FACTORY_STATUS_SNAPSHOT.md` — one-page status table
- `REEL_FACTORY_EXECUTION_STATUS.md` — execution summary
- `REEL_FACTORY_CONTROL_BOARD.md` — condensed board
- `REEL_FACTORY_LIVE_QUEUE.md` — live queue

## Operating rule
The project stays active. Nothing is stopped unless Hesham explicitly changes the plan.
