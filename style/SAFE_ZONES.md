# Safe zones: the layout rule every reel, cover and template follows

Source: Hesham's "Instagram & TikTok Safe Zone & Design Guide" (`style/safe_zones_guide_source.md`, 2026-11-01).
Numbers live in `config/rules.json → safe_zone` (single source); templates use them as CSS variables.

## The box (1080 × 1920, both platforms at once = the stricter number)

| Edge | Reserved | Why |
|---|---|---|
| Top | 250 px | Instagram header (220–250), TikTok tabs (160–200) |
| Bottom | 420 px (nothing important below y = 1500) | Instagram caption/handle (350–420), TikTok caption/sound (320–380) |
| Right | 160 px | TikTok action column (160), Instagram buttons (120) |
| Left | 108 px | Instagram edge padding (108), TikTok bezel (60) |

So every text, card and key graphic **rests** inside x 108–920, y 250–1500.

## Rules
1. **Text width ≤ 780 px**, placed at x 124–904 (inside the box, clear of the right-hand buttons).
2. **Captions** sit in the band y 1200–1450 (centred there); never below y 1500.
3. **Animations** may start off-screen, but their final resting position is completely inside the box.
4. **Frame 0 and the cover**: the title (the hook) sits inside the centred 1080 × 1080 feed square (y 420–1500), so the grid preview shows it.
5. Backgrounds, footage, photos and scrims may fill the whole canvas; only text and key graphics follow the box.
6. Canvas 1080 × 1920 at 30 fps.

## How it is checked
- `tests/test_safe_zones.py` renders every template with its **longest allowed text** plus the cover, and fails if any text or card leaves the box.
- `python3 scripts/safe_zone_preview.py <image>` draws the platform UI zones over a frame or cover (the "UI overlay mask"), for a visual check. The overlay is never part of a real export.
