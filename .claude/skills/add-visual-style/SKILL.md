---
name: add-visual-style
description: Add a new visual block (card, overlay, animation) to Reel Factory's templates, keep it inside the safe zones, let the AI editor use it, prove it with tests and a sample still. Use when Hesham asks for a new look, style or animation, or when working on T75 (saved visual prompts).
---

# Add a new visual style (template block)

Read first: `AGENTS.md` §5, `style/SAFE_ZONES.md`. Only the HTML templates decide how things look; the AI only fills in values.

## Steps
1. **Copy the closest block** in `templates/blocks/` (e.g. `text_card.html`) to `templates/blocks/<name>.html`.
   - Position everything with the safe-zone CSS variables (`--safe-top`, `--safe-left`, `--text-x`, `--text-w`, `--cap-top`, `--feed-top`…). Never hard-code positions outside x 108–920, y 250–1500.
   - Text comes from `data-var-text="<input>"`; big words that vary in length use `__SIZE_<input>__` + an entry in `FIT` in `scripts/lib/hfbuild.py`.
   - Animate with GSAP on the block's timeline. **Never** set `visibility`, `display` or `autoAlpha` in the script (HyperFrames hides clips itself; doing it made captions vanish in real renders).
   - Brand colours/fonts only via the CSS variables from `hfbuild.brand_vars()`.
2. **Register it** in `templates/blocks/registry.json`: `label`, `file`, `layer`, `purpose`, `inputs` (each string with a `maxLength`), `duration_s`, `rules`, optional `sfx`.
3. **Let the AI editor use it** (only if it's a "moment"): add the name to `DIRECTOR_BLOCKS` in `scripts/lib/director.py`. The menu the AI sees is built from the registry automatically.
4. **Test** (no spend): `python3 -m unittest discover tests`
   - `test_safe_zones.py` fills every block with its LONGEST text and fails if anything crosses the safe box. If `sample_values()` needs a realistic value for the new block, add it there.
   - `TemplateContractTests` catches visibility tweens.
5. **Show Hesham a sample**: render a still with `python3 scripts/safe_zone_preview.py` (overlay of the safe zones) or a HyperFrames snapshot, look at it yourself first, then send it.
6. Log the choice in `docs/DECISIONS.md` (one line), commit on a branch, push, set the board task to **review** with the sample as evidence.

## Don'ts
- Don't let the AI write or edit HTML; it only picks values.
- Don't upgrade HyperFrames/Node packages for a new style.
- Don't put logos in a block unless they come from the reel's own `assets/` folder.
