# Idea for later: Reel Factory learns from how reels perform (Hesham, 2026-11-01)

Board: T76. Builds on T45 (performance after 48 h), T36 (measure best reels), T49 (monthly calibration), T63/T72 (learning from comments).

## The idea
After a reel is posted, Reel Factory collects how it did, works out which editing choices go with better results,
and uses that to edit the next reels: a small self-learning loop, specific to Hesham's audience.

## How the numbers come in
1. **Manual (works on day one):** a "How did it do?" box on each finished reel: views, average watch time, % who watched to the end, likes, comments, shares, saves, follows. Can paste a screenshot of the Insights page instead.
2. **Linked accounts (later):** Instagram Graph API (Business/Creator account linked to a Facebook Page) and TikTok API (Display/Research access), read-only, fetched 48 h and 7 days after posting.

## What it compares (per reel, already known from the edit)
Hook text and length, first cut time, reel length, number/kind of moments (cards, flashes, splits), punch-ins per minute,
caption style, topic, CTA type, cover, posting day/time; plus the retention curve where the platform gives one
(where people stop watching -> which moment was on screen).

## How it learns (small and explainable, no black box)
- Start with simple scoring: which choices go with higher watch-through and saves across his own reels.
- After ~10-15 reels: a small model (e.g. regression) per metric; never fewer than 5 reels behind any rule.
- Output = plain-language rules written into `.reel-agent/lessons.md` ("Hooks under 2 s keep 18% more viewers, 12 reels"),
  which the AI editor already reads (director.taste). Hesham can delete any rule.
- Monthly report on the dashboard: what worked, what to try next, one A/B idea.

## Guard rails
- Only his own accounts, read-only; no posting, no scheduling. Keys stay on his Mac (like the Nous key).
- Never invents numbers: every rule shows how many reels it's based on.
- Content rules still win (his words only, safe zones).
