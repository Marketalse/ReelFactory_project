# Reference spec v2 — base layer + creative layer (P0-R)

Two reference sets, two jobs:
- **Set 1 (6 reels, 2026-10-29): the base layer.** Structure, layout and card templates. Clear, but slow and safe.
- **Set 2 (4 Pinterest reels, 2026-10-29): the creative layer.** Motion, transitions, kinetic type and B-roll. This is the energy Gen-Z and Gen-Alpha expect.

Values marked **measured** came from ffprobe/ffmpeg; values marked **eyeballed** came from contact sheets. Two of the six Pinterest links have not been received yet, so add them when they arrive.

Visual companion: `creative_move_board.png` (16 frames, labelled).

---

## 1. Base layer (from set 1, unchanged)

| # | Format | Duration | Res / FPS | Hard cuts (measured) |
|---|---|---|---|---|
| 1 | A · motion graphics + voiceover | 62.8 s | 720×1280 / 30 | 9 |
| 2 | A · motion graphics + voiceover | 56.5 s | 720×1280 / 30 | 8 |
| 3 | B · card top / face bottom | 59.1 s | 720×1280 / 30 | 1 |
| 4 | C · screen recording + overlays | 37.2 s | 720×1280 / 30 | 2 |
| 5 | B · card top / face bottom | 72.1 s | 720×1280 / 30 | 3 |
| 6 | B · card top / face bottom | 29.8 s | 720×1280 / 30 | 0 |

Keep from set 1: the split layout (card top, face in the bottom ~35–45%), keyword-highlighted captions, data cards (counter, bar chart, price swap), logo pairs, UI mockups, the "comment a word" CTA end card, and Western digits.

## 2. Creative layer (from set 2)

### 2.1 Specs (measured)

| Ref | Source | Duration | Res / FPS | Visual changes* | Seconds per change |
|---|---|---|---|---|---|
| P1 | @motion_pet (before/after showcase) | 19.1 s | 720×1280 / 30 | 5 | ~3.8 |
| P2 | creator reel, full frame | 37.6 s | 720×1280 / 24 | 22 | ~1.7 |
| P3 | "Pov: I Edit Your Reel" (before/after) | 35.4 s | 720×1280 / 30 | 38 | ~0.9 |
| P4 | @bydualmodestudio (before/after) | 21.8 s | 720×1280 / 30 | 5 | ~4.4 |

\* ffmpeg scene score > 0.3. For P1, P3 and P4 this was measured on the cropped "After" panel only. Word-level caption animation doesn't register as a scene change, so P1 and P4 *feel* faster than their numbers.

**The headline gap:** set 1 Format B makes a hard visual change every **20–60 s**. Set 2 makes one every **~1–4 s**. That gap is what reads as "creative" to a young audience.

### 2.2 Move catalogue

Build type: **T** = template the Director can call · **FX** = transition/effect preset · **A** = asset library · **S** = something you do while shooting. Cost: everything below is local and code-rendered (0 LLM tokens at render time). Only the Director's choice of *which* move costs tokens.

| # | Move | Seen in | Build | What it does for the viewer | Brand mapping (lime / violet / slate / coral) | Local tool |
|---|---|---|---|---|---|---|
| 1 | **Word-pop captions**: 1–3 words at a time, each pops in on its spoken word | P1, P2 | T | Forces reading along; highest retention move | White words, keyword turns lime | HyperFrames + word timestamps |
| 2 | **Mixed weights per word**: thin and heavy weights in one line | P1 | T | Adds rhythm and stress without extra colours | Readex Pro wght 200 ↔ 700 (variable axis already approved) | Readex Pro variable font |
| 3 | **Text behind subject**: big word or number sits behind you | P1 ("4") | T | Strongest "how did they do that" signature move | Lime numeral behind your head | MediaPipe selfie segmentation → cached alpha matte |
| 4 | **Concept B-roll cutaway**: a full-screen image or clip that matches the spoken word | P1, P3, P4 | A + T | Visual metaphor per idea; breaks the talking-head monotony | Grade B-roll toward slate; lime word on top | `find-broll` skill + local tagged library |
| 5 | **Solid flash + 1 word** | P2 | T | Thumb-stop reset every ~10 s | Lime flash beat (max 2 per reel), dark text | HyperFrames |
| 6 | **Whip-blur zoom into screen recording** | P2 | FX | Makes UI demos feel fast | Violet edge glow on the screen card | CSS transform + blur |
| 7 | **Punch-in zoom + sticker on face** | P2 | FX + A | Comedy and emphasis on reactions | Sticker pops in lime/violet outline | Face box (already cached) + Fluent Emoji 3D |
| 8 | **Ghost / echo transition** | P2 | FX | Smooth handoff between shots | No colour; opacity only | ffmpeg `tmix` or layered frames |
| 9 | **Light-leak transition** | P3 | FX + A | Warmth and a cinematic feel | Tint leaks violet → coral | Free light-leak clip pack, screen blend |
| 10 | **Kinetic type card**: condensed, glowing headline on black | P3 | T | Chapters the reel ("MOST IMPORTANTLY") | Lime glow on slate | CSS text-shadow; Readex Pro HEXP axis for width |
| 11 | **Icon row on beat**: 3 icons pop one per word | P4 | T | Turns lists into visuals | Violet discs, white icons | Fluent Emoji 3D / icon set |
| 12 | **Editorial interlude**: a calm full-frame card with floating 3D objects | P4 | T + A | Contrast moment; feels premium | Violet full-bleed instead of cream | HyperFrames + 3D object PNGs |
| 13 | **Object motion-blur swipe** | P4 | FX | Kinetic link between interludes | Any brand object | CSS blur + translate |
| 14 | **Before/after compare slider** | P2 | T | Perfect for AI-tool reviews | Violet divider, lime "After" label | HyperFrames |
| 15 | **Two-tone bold caption**: white line + lime line | P4 | T | Stronger hook captions in the first 3 s | White + lime | HyperFrames |

### 2.3 Shooting moves (S): your part

- **Leave headroom** above your head for move 3: the text needs space behind you.
- **Hold still for 1 s** after each key line, so the segmentation matte and the punch-in stay clean.
- **Make one big reaction** per reel (a face or gesture) to anchor move 7.
- **Use a plain or uncluttered background**: segmentation and B-roll grading both get easier.

## 3. Creative rhythm (proposal, to test in V0)

Derived from 2.1. These are not measured rules; tune them on your golden set.

| Layer | Rule |
|---|---|
| Captions | Something on screen changes every **1–2 s** (word-pop) |
| Visual change | A cutaway, card or zoom every **3–5 s** |
| Signature move | 1 per **~10 s** (text-behind, flash, compare slider), never two back to back |
| Hook (0–3 s) | Two-tone caption + punch-in + one signature move |
| Lime flash | Max 2 per reel, only on payoff numbers |
| End | Comment-CTA card (base layer) |

60 s beat map, example:
`0s hook (two-tone + punch-in) → 3s word-pop → 6s B-roll cutaway → 10s text-behind number → 15s word-pop → 18s icon row → 22s whip into screen → 30s kinetic chapter card → 34s compare slider → 40s lime flash payoff → 45s word-pop → 52s light-leak → 55s CTA`

## 4. What changes in the execution plan

- **V0 templates become:** word-pop caption (replaces the static caption card), counter with lime flash, CTA, plus **one FX** (light leak or whip-blur) to prove transitions work.
- **P0-B spike adds:** a 3 s text-behind-subject test using a MediaPipe matte. It's the riskiest creative move on 16 GB and the most valuable.
- **P1 template order:** add moves 3, 4, 10, 11 and 14 to the list, and drop the checklist and timeline to later.
- **New asset libraries (one-time, licence-checked):** light leaks, 3D icons/emoji, 3D objects and tagged B-roll. Store them under `style/assets/` with a licence file per pack.
- **Director schema:** add `"fx"` and `"move"` fields. The validator enforces the rhythm table: no back-to-back signature moves, at most 2 flashes.

## 5. Not ours to copy

Set 1: the cream/coral/charcoal palette, dot grid and `@majed_alzaabi_` handle. Set 2: the creators' handles, watermarks, footage and exact layouts. Copy the **techniques**; your brand kit (lime/violet/slate + Readex Pro) carries the look.
