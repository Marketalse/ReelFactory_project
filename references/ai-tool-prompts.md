# AI-tool explainer prompts

Source: `Downloads/AI Tool Reel Teardown.md`, captured 2026-10-31.

## Prompt 1 · Script writer
```
You are a short-form scriptwriter for AI-tool explainer reels (Instagram/TikTok, 30–40 seconds, target audience Gen-Z and Gen-Alpha tech-curious viewers).

TOOL: [tool name + link]
WHAT IT DOES: [1–3 sentences]
PROOF I CAN SHOW ON SCREEN: [list of screens/recordings I have]
STANDOUT STAT: [stars / users / price / data size]
CTA KEYWORD: [one word]

Write ONE script of 100–120 words using exactly this structure:

1. HOOK TITLE (on-screen, 2 lines): Line 1 = 3–5 plain words. Line 2 = 2–4 words, the payoff (e.g. "Claude Code Is Now / Your Sales Rep").
2. HOOK LINE (0–3 s, spoken): says the same claim as the title in natural speech. No intro, no "hey guys".
3. REVEAL (3–6 s): name the tool ("It's called X") or name the problem it fixes.
4. PROOF BEATS (6–32 s): 3–5 short beats. Each beat = one sentence describing one thing the tool does, in the order a user would experience it. Use concrete verbs (finds, studies, builds, books). Include the standout stat once.
5. BONUS (optional, 1 line): "The best part, it's 100% free / open source."
6. CTA (last 3–5 s): "If you want to try it for yourself, comment '[KEYWORD]'."

Rules: second person ("you"), present tense, no filler, no pauses implied, every sentence must be provable on screen.

Output as a table with columns: Time | Spoken line | On-screen visual | Layout mode (A Split / B Full B-roll / C White card / D Face punch-in / E CTA) | Caption accent word.
```

## Prompt 2 · Editing spec
```
Edit a 9:16 short-form reel (1080×1920, 30 fps, 32–40 s) from: one 4K talking-head take, a set of screen recordings, and the script table attached.

GLOBAL
- Remove every pause, breath and filler. No silence longer than 0.2 s.
- Something on screen must change at least every 1 second (cut, zoom, highlight, caption, pop-up).
- Music: low, upbeat bed at about -24 dB under the voice. Whoosh on each layout change, soft pop on each stat callout, keyboard clicks under typing.

LAYOUT MODES
A. SPLIT: background = light, softly blurred studio wall with a faint palm-leaf shadow. Screen card centered in the top 35% (rounded 16 px window, 2 px accent border with soft outer glow). Talking head in a rounded-corner card filling the bottom 40%, slightly inset from the sides. Captions centered between the two.
B. FULL B-ROLL: face hidden. Larger screen card centered on a dark radial vignette background. Slow 3–5% push-in. Captions below the card, white.
C. WHITE CARD: pure white background. Small black label ("Tool Number" / "It's Called") above an accent highlight box with the italic word ("One"), then a logo or website screenshot, then the tool name in bold black.
D. FACE PUNCH-IN: full-frame crop of the talking head (about 1.6× zoom), 0.8–1.5 s, on the key word of a sentence.
E. CTA: full-frame face. Small italic serif "comment" above a large bold keyword in quotes, yellow (#F2E53A) with a yellow glow, centered at the lower third. Hold to the end.

SEQUENCE
0–3 s: Mode A with the HOOK TITLE at the top (line 1 black bold sans; line 2 italic serif white on a solid #1E6BF0 box, revealed word by word). Title disappears at the first mode change.
Then alternate B / C / A for each proof beat, inserting D once or twice on the strongest words. End with E.
Mode share target (measured average across the 5 reels): A 40%, B 35%, C 10%, D 8%, E 7%.

SCREEN CARD ANIMATION
- Typing animation in terminals; highlight sweep over the sentence being spoken; zoom into the exact line referenced.
- Stat pills: dark rounded box, huge white number with a small label underneath ("163k / stars on GitHub"), scale-pop in over the card.
- Transitions between modes: 6-frame directional blur or whip.

CAPTIONS
- Word-by-word, 1–3 words on screen, centered, bold geometric sans (e.g. Inter Display / SF Pro Bold), about 60 px.
- Near-black on light modes, white on dark modes, subtle shadow on white.
- One keyword per phrase in italic serif (e.g. Instrument Serif Italic) in the accent color.
- Accent color = #1E6BF0 unless the featured tool's brand color is stronger (then use that, e.g. lime #C9F03C).

EXPORT: H.264, 1080×1920, 30 fps, AAC 48 kHz, loudness -14 LUFS.
```

## Prompt 3 · Clean screen cards
```
Build an animated UI card as a single HTML/CSS (or Remotion) component for a vertical reel, 900 px wide.

Content: [paste what the screen should show, e.g. a terminal running "set up Harvey for me" with 3 tool calls, or a GitHub repo header with 163k stars].

Style: macOS-style window with traffic-light dots and a small title bar, 16 px radius, 2 px #1E6BF0 border with a soft blue outer glow, clean dark (#1B1F29) or white body, monospace for terminals, system sans for web pages. Simplify: keep only the elements the voiceover mentions.

Animation (total [N] seconds): type the command at 25 chars/s, reveal each output line with a 150 ms fade-up, then sweep a translucent blue highlight across [the key phrase] and zoom 1.3× into it for the final second. Add an optional stat pill: dark rounded box, white 96 px number, 20 px label, scale from 0.6 to 1 with a slight overshoot.
```
