# Reference spec — 6 reels (P0-R)

Source: 6 MP4s Hesham attached in the Claude chat on 2026-10-29. Values marked **measured** came from ffprobe/ffmpeg; values marked **eyeballed** came from 16-frame contact sheets per reel and still need a code measurement.

## File specs (measured)

| # | Format | Duration | Resolution | FPS | Scene cuts (ffmpeg scene > 0.25) |
|---|---|---|---|---|---|
| 1 | A · motion graphics + voiceover | 62.8 s | 720×1280 | 30 | 9 |
| 2 | A · motion graphics + voiceover (stats/charts) | 56.5 s | 720×1280 | 30 | 8 |
| 3 | B · card top / face bottom | 59.1 s | 720×1280 | 30 | 1 |
| 4 | C · screen recording + overlays | 37.2 s | 720×1280 | 30 | 2 |
| 5 | B · card top / face bottom | 72.1 s | 720×1280 | 30 | 3 |
| 6 | B · card top / face bottom | 29.8 s | 720×1280 | 30 | 0 |

Takeaways:
- All are 9:16, 30–72 s, median ~58 s.
- Format B (talking head) has almost no hard cuts (0–3). Its pace comes from card swaps above a continuous face shot.
- Format A cuts more often (8–9), mostly scene-to-scene wipes.

## Layout (eyeballed)

- Format B: the graphic card fills the upper part; the face sits in a rounded frame in roughly the bottom 35–45%. The caption card sits between them. (An automated measurement was noisy because caption cards break the background, so measure on the template instead.)
- A handle watermark at the top in formats A and B.
- The end card in every reel is a "comment a word" call to action with an input-box mockup.

## Caption behaviour (eyeballed)

- One short phrase per card (≈3–7 words), Arabic, with 1–2 key words highlighted in the accent colour.
- A new caption card roughly every 2–4 s. **Measure this in V0 from word timestamps.**
- Western digits (59,309 · 70.6% · $275), not Arabic-Indic.

## Recurring graphic types (count of reels that use each, eyeballed)

| Type | Reels |
|---|---|
| Keyword caption card | 3, 4, 5, 6 |
| Counter / big number | 1, 2, 5 |
| Bar chart | 1, 2, 5 |
| Price before→after | 2, 5 |
| Logo / app icon pair | 3, 5, 6 |
| UI mockup (chat, dashboard, PDF) | 1, 2, 3, 5 |
| Timeline / steps | 1, 2, 4 |
| Comment CTA end card | 1, 2, 5, 6 |

Suggested V0 templates (highest coverage for Format B): **caption card, counter, CTA**, plus the split frame. This matches the plan.

## Not ours to copy

The cream/coral/charcoal palette, the dot grid and the `@majed_alzaabi_` handle belong to the reference creator. Copy the structure only.
