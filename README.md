# Reel Factory

Turns Hesham's raw talking-head clips into reviewable Instagram/TikTok reels (40–90 s, Iraqi Arabic), with three approval gates. Fixed, approved templates do the visuals; AI only fills in values.

## Where things are
| What | File |
|---|---|
| Tasks, progress, spend (visual) | `python3 dashboard/serve.py` → http://127.0.0.1:8765 |
| Rules for agents | `AGENTS.md` |
| Steps, in order (what works today) | `SOP.md` |
| Decisions and why | `DECISIONS.md` |
| Plan and target structure | `docs/RESTRUCTURE_PLAN.md` |
| Models, budget, gates | `config/project.json` |
| Brand, CTA, captions | `config/brand.json` |
| Rhythm limits | `config/rules.json` |
| Word spellings | `config/glossary.json` |
| How Hermes works | `dashboard/HERMES_TASKS.md` |

## Handing in a reel
```
inbox/<slug>/clips/   footage (joined in filename order)
inbox/<slug>/assets/  logos (SVG/PNG), screenshots
inbox/<slug>/refs/    optional reference videos
inbox/<slug>/brief.md optional notes (template: templates/inbox_brief.md)
```
Run today (one clip): `python3 scripts/reel.py <clip.MOV> --slug <name>` — see `SOP.md` for which stages work yet.
Offline checks (no spend): `python3 -m unittest discover tests`

Video never goes into git; it stays on the Mac.
