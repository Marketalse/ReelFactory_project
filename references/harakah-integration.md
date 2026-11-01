# Reel Factory Harakah integration note

Use Harakah for Arabic text handling when building the reel.

## Repo
- Cloned repo: `~/Desktop/Reel-Factory/integrations/harakah`
- Commit checked out: `7bd4b99`
- Package name: `harakah-fixer`

## What Harakah gives us
- `splitArabic()` for Remotion codemods and helper use
- `<ArabicText>` for direct React / Remotion composition use
- `formatDigits()` for digit shaping
- A safe path for HTML / GSAP / HyperFrames that keeps the same elements so the timeline still works

## Key rule for Reel Factory
- Use Harakah's Arabic shaping helpers instead of manually splitting letters.
- Keep the timeline structure stable.
- Use the same element structure in HTML / GSAP / HyperFrames and let a small script handle the Arabic shaping behavior.

## What the README says that matters here
- `harakah-fixer` supports Remotion, HyperFrames, GSAP and plain HTML/CSS.
- It ships both CLI and Remotion integration.
- It is designed to keep Arabic joined while preserving the animation logic.

## Suggested next step for Reel Factory
- Wire the V0 scene plan to use the Harakah approach for Arabic text.
- Prefer a reusable helper layer so the same reel logic works across the current HyperFrames path and any future Remotion-style reuse.
