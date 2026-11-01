# Reel Factory

Turns Hesham's raw talking-head clips (Iraqi Arabic, marketing and business) into ready-to-post Instagram/TikTok reels (40–90 s).
You upload, comment on the draft, approve, download. Nothing is ever posted for you.

**Start here:** double-click `Reel Factory.command` (or turn on auto-start once), then read `HOW_TO.md`.

## The main folder
| | What it is |
|---|---|
| `Reel Factory.command` | Opens the dashboard (upload, review, results, settings) |
| `Turn on auto-start.command` / `Turn off auto-start.command` | Dashboard starts by itself when the Mac starts |
| `HOW_TO.md` | How to make a reel, in plain words |
| `AGENTS.md` | Rules any AI helper must follow when working on the project |

## Folders
| Folder | What's inside | You touch it? |
|---|---|---|
| `inbox/` | Videos waiting to become reels (the upload page puts them here) | No, use the dashboard |
| `jobs/` | One folder per reel: drafts, final videos, cover, your comments, results | Only to find files |
| `dashboard/` | The web page and its server, plus the task board (`tasks.json`) | No |
| `scripts/` | The pipeline. `reel.py` runs every step | No |
| `templates/blocks/` | The approved visuals (captions, titles, cards) | No |
| `style/` | Fonts, safe zones (`SAFE_ZONES.md`), sound effects (coming) | No |
| `config/` | Settings: AI models and spending caps, brand, rhythm, spellings | Rarely |
| `references/` | Your best reels and other examples to learn from | Add examples |
| `docs/` | `DECISIONS.md` (what we decided and why), `SOP.md` (every step), `ideas/` (for later) | Read |
| `tests/` | Automatic checks (no cost) | No |
| `archive/` | Old plans and files, history only | No |
| `.reel-agent/lessons.md` | What was learned from each reel, including your taste | Read |
| `.claude/skills/` | Step-by-step guides for AI helpers (new visual style, fixing a stopped reel) | No |

## For developers
- Offline checks (no spend): `python3 -m unittest discover tests`
- Run without the dashboard: `python3 scripts/reel.py inbox/<slug> --slug <slug>` (see `docs/SOP.md`)
- Brief template for a reel: `inbox/BRIEF_TEMPLATE.md`
- Branches: `main` is the version in use; work happens on a branch and is merged by Hesham. `backup-v1-working` is a frozen copy of the first working version.

Video, audio and keys never go into git; they stay on the Mac.
