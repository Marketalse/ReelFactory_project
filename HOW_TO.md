# How to make a reel — 3 steps, no Terminal

## Once: open the dashboard
In Finder, open the **ReelFactory_project** folder and double-click **Reel Factory.command**.
Your browser opens the dashboard on the **Reels** page. (First time only: if macOS asks, click Open.)
Leave that page open in a tab.

## 1. Drop your clips
In Finder: **ReelFactory_project → inbox**. Make a new folder with a short name, lowercase, no spaces
(example: `store-tips`), and inside it a folder called `clips`. **Copy** your video(s) into `clips`.
Several takes are fine: they're joined in name order.

Optional: logos in `store-tips/assets/`, notes in `store-tips/brief.md`.

## 2. Click "Make reel"
The folder appears on the dashboard under **New footage**. Click **Make reel**.
Everything runs by itself: words, story, cuts, captions, cards, checks.
You get a Mac notification when the draft is ready (the first reel takes longer: the speech model downloads once).

## 3. Watch, then comment or approve
The draft plays on the dashboard.
- **Want changes?** Type them like you'd tell an editor ("hook shorter", "bigger captions", "remove the flash")
  and click **Send changes**. A new draft appears in a few minutes.
  Wrong word in the captions? Write `wrong word => right word` on its own line.
- **Happy?** Click **Approve**. The final high-quality videos (one for Instagram, one for TikTok)
  appear under the reel as download links.

## Want to tweak it yourself in CapCut?
After Approve, the reel also shows **For CapCut** files. Click **Open in Finder**, then in CapCut (new 9:16 project):
1. Drag **1_video.mp4** onto the timeline (you, already cut, with zooms and sound).
2. Drag **2_graphics.mov** onto the track **above** it (captions, titles, cards, on a transparent background).
They start at 0:00 and are the same length, so they line up by themselves. Trim, move or delete anything, then export.
Prefer CapCut's own caption styles? Delete track 2 and import **captions_ar.srt** instead.
For bigger changes, just comment on the dashboard and click Send changes.

That's all. If a reel says **needs attention**, click **Try again**; if it still stops, send Claude the message shown.

Cost: about $0.05–0.15 per reel; it never spends more than $1 per reel or $50 per month.
Before the first **Approve**, your handles must be set in `config/brand.json` (Claude can do this for you).
