# How to make a reel: 3 steps, no Terminal

## Open Reel Factory
**Best (once):** in your **ReelFactory_project** folder, double-click **Turn on auto-start.command**.
From then on Reel Factory starts by itself whenever you log in. Just open http://127.0.0.1:8765 (bookmark it).
Without auto-start: double-click **Reel Factory.command** each time.
First time only: if macOS says it can't verify the file, click **Done**, then go to **System Settings → Privacy & Security**,
click **Open Anyway** and double-click again.

**Updates:** click **Settings → Get the latest version**. No Terminal needed.

## 1. Upload your video
Drag your video onto the box (or click it to choose). MP4, MOV, AVI or WebM.
Several takes are fine: they're joined from top to bottom; use ↑ ↓ to change the order.
Your original files stay where they are; Reel Factory works on a copy.

Optional, under **Extras**:
- **Reel name**: e.g. "Store tips", so you can find it later.
- **Logo**: SVG or PNG of a brand you mention; it can pop up while you talk about it.
- **Notes for the editor**: what matters, in Arabic or English ("main point is…", "ask people to comment ‘store’").
- Subtitles are made automatically from your voice. Music: add a trending song in Instagram or TikTok when you post.

## 2. Click "Make my reel"
A progress bar shows each step, how far along it is, and the time left.
You can close the tab: you get a Mac notification when the draft is ready, and the page shows the reel again when you come back
(also under **Your reels** at the top).

## 3. Watch, then comment or approve
The draft plays on the page.
- **Want changes?** Type them like you'd tell an editor ("hook shorter", "bigger captions", "remove the flash")
  and click **Send changes**. A new draft appears in a few minutes.
  Wrong word in the captions? Write `wrong word => right word` on its own line.
- **Happy?** Click **Approve & make final video**. Two steps run: your **final video** (high quality, one video for both
  Instagram and TikTok), then your **cover image**.
- **Final preview**: watch it, click **Download final video**. Still want a change? Type it in **Want changes?** and click
  **Send changes**: a new draft is made; approve it again for a new final video (the old one stays saved).

## Ready-to-post score
Every draft and final shows a **score out of 100** with up to 3 tips (for example "your first word comes at 1.3 s").
It checks what keeps people watching: a fast start, a title on the first frame, length, something changing every
few seconds, captions, sound, cards and zooms. It is **not** a prediction of views. Follow a tip by typing it into
**Want changes?**. The Results page shows each reel's score next to its real numbers.

## Cover image (thumbnail)
After the final video, a **cover image** is suggested (your title on top, you underneath, in your brand style). Click **Download cover**.
- **Upload my own cover**: pick a finished image; it's used as is (cropped to vertical).
- **Use my photo with our title**: pick a photo of you; the cover is made again with it (about 20 seconds).
- **Back to automatic**: our suggestion again.
You can also add a cover photo before you start, under **Extras → Cover photo**.

## After you post: "How did it do?"
2 days after posting, open **Insights** on Instagram or TikTok, open the reel on the Make a reel page (**Your reels** at the top)
and type the numbers into **How did it do?** (views, average watch time, watched to the end, likes, comments, shares, saves, follows).
Do it again after 7 days if you can. All results are under **All reels & tasks → Results** (also as a spreadsheet).
From 5 reels on, Reel Factory starts learning what works for your audience.

## Backup
**Settings → Backup** copies your results, comments, edit plans, transcripts, settings and lessons (no videos) into
**Google Drive** or **iCloud Drive** on this Mac, in a folder called **Reel Factory backup** (one ZIP per backup, newest 30 kept).
It runs by itself once a day while Reel Factory is open; click **Back up now** any time. Your videos stay only on the Mac:
keep Time Machine on for those.

That's all. If a reel says **Stopped**, click **Try again**. If it stops again, click **Copy message** and send it to Claude.

Cost: about $0.05–0.15 per reel; it never spends more than $1 per reel or $50 per month.
Before the first **Approve**, your handles must be set in `config/brand.json` (Claude can do this for you).
The older view (all reels, task board, spend) is under **All reels & tasks** at the top right.

## Your API key (once)
Click **Settings** (top right of the page), paste your Nous key from portal.nousresearch.com → API keys, and click **Save**.
It's stored only on your Mac (`~/.reelfactory/nous_api_key`), never in the project or git. **Test** checks that it works (free).
Settings also shows whether everything else Reel Factory needs is ready; a ⚠️ says what to do.
Reel Factory no longer uses anything from Hermes. "HTTP 401" on a reel = the key is wrong or the account is out of credit.
