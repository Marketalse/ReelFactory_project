# How to make a reel: 3 steps, no Terminal

## Once per session: open Reel Factory
In Finder, open your **ReelFactory_project** folder (the one you cloned with git, **not** a ZIP copy in Downloads)
and double-click **Reel Factory.command**. Your browser opens the **Make a new reel** page.
First time only: if macOS says it can't verify the file, click **Done**, then go to **System Settings → Privacy & Security**,
click **Open Anyway** and double-click again.

## 1. Upload your video
Drag your video onto the box (or click it to choose). MP4, MOV, AVI or WebM.
Several takes are fine: they're joined from top to bottom; use ↑ ↓ to change the order.
Your original files stay where they are; Reel Factory works on a copy.

Optional, under **Extras**:
- **Reel name**: e.g. "Store tips", so you can find it later.
- **Logo**: SVG or PNG of a brand you mention; it can pop up while you talk about it.
- **Notes for the editor**: what matters, in Arabic or English ("main point is…", "ask people to comment ‘store’").
- Subtitles are made automatically from your voice. Background music: coming soon (add it in CapCut for now).

## 2. Click "Make my reel"
A progress bar shows each step, how far along it is, and the time left.
You can close the tab: you get a Mac notification when the draft is ready, and the page shows the reel again when you come back
(also under **Your reels** at the top).

## 3. Watch, then comment or approve
The draft plays on the page.
- **Want changes?** Type them like you'd tell an editor ("hook shorter", "bigger captions", "remove the flash")
  and click **Send changes**. A new draft appears in a few minutes.
  Wrong word in the captions? Write `wrong word => right word` on its own line.
- **Happy?** Click **Approve & make final videos**. Then click **Download processed video** (one for Instagram, one for TikTok).

## Want to tweak it yourself in CapCut?
After Approve the page also shows the **CapCut files**. Click **Open in Finder**, then in CapCut (new 9:16 project):
1. Drag **1_video.mp4** onto the timeline (you, already cut, with zooms and sound).
2. Drag **2_graphics.mov** onto the track **above** it (captions, titles, cards, on a see-through background).
They start at 0:00 and are the same length, so they line up by themselves. Trim, move or delete anything, then export.
Prefer CapCut's own caption styles? Delete track 2 and import **captions_ar.srt** instead.

That's all. If a reel says **Stopped**, click **Try again**. If it stops again, click **Copy message** and send it to Claude.

Cost: about $0.05–0.15 per reel; it never spends more than $1 per reel or $50 per month.
Before the first **Approve**, your handles must be set in `config/brand.json` (Claude can do this for you).
The older view (all reels, task board, spend) is under **All reels & tasks** at the top right.

## Your API key (once)
Click **Settings** (top right of the page), paste your Nous key from portal.nousresearch.com → API keys, and click **Save**.
It's stored only on your Mac (`~/.reelfactory/nous_api_key`), never in the project or git. **Test** checks that it works (free).
Settings also shows whether everything else Reel Factory needs is ready; a ⚠️ says what to do.
Reel Factory no longer uses anything from Hermes. "HTTP 401" on a reel = the key is wrong or the account is out of credit.
