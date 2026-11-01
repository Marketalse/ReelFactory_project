# How to make a reel — simple steps

Open **Terminal** and type each command, then press Enter. Wait for one to finish before typing the next.

---

## Once: get the latest version

```
cd ~/Desktop/ReelFactory_project
git pull
```

---

## Step 1 — Put your video in

1. Make a folder for the reel, with a short name: lowercase, no spaces (example: `store-tips`).
2. **Copy** your video(s) into it. Don't move the originals: the program moves whatever is inside.

```
mkdir -p inbox/store-tips/clips
cp ~/Desktop/MyVideo.MOV inbox/store-tips/clips/
```

Optional, in the same folder:
- `inbox/store-tips/assets/` → logos (SVG or PNG)
- `inbox/store-tips/brief.md` → a few notes (copy from `templates/inbox_brief.md`)

Several takes? Put them all in `clips/`. They're joined in name order (IMG_0021, IMG_0022…).

---

## Step 2 — Start

```
python3 scripts/reel.py inbox/store-tips --slug store-tips
```

The **first time** it downloads the speech model (about 3 GB). That takes a while, once only.

It stops and says **GATE 0**.

---

## Step 3 — Gate 0: fix the words

Open the transcript it made (the job folder starts with today's date):

```
open -e jobs/*-store-tips/transcript_review.txt
```

- Correct any wrong words. **Only change the words**, not the numbers at the start of each line.
- English words you said in English → write them in English (customer service).
- On the line `STATUS: waiting`, change it to `STATUS: reviewed`.
- Save (Cmd + S) and close.

Then continue:

```
python3 scripts/reel.py jobs/*-store-tips
```

---

## Step 4 — Gate 1: pick the story

It shows 3 story options: **A**, **B**, **C**. Pick one:

```
python3 scripts/reel.py jobs/*-store-tips --select A
```

(If your video is already short, it skips this step by itself.)

Now it cuts, plans and builds. This takes a few minutes.

---

## Step 5 — Gate 2: watch the draft

```
open jobs/*-store-tips/review/draft_540p.mp4
```

Also useful:
- `jobs/…/report.md` → what was done, what it cost, any warnings
- `jobs/…/edit_package/` → files to tweak it yourself in CapCut/DaVinci

**Happy with it?** Make the final, high-quality videos (one for Instagram, one for TikTok):

```
python3 scripts/reel.py jobs/*-store-tips --approve
```

They appear in `jobs/…/final/`.

**Want changes?** Say what to change in plain words:

```
python3 scripts/reel.py jobs/*-store-tips --fix "make the hook shorter and captions bigger"
```

Then watch the new draft again (Step 5).

---

## If something goes wrong

- It says **STOP** with a reason: read the reason. Gates are normal stops, not errors.
- Anything else: send Claude the last lines of `jobs/…/run.log`.
- Before the final videos work, your Instagram and TikTok handles must be set in `config/brand.json`.

**Cost:** about $0.05–0.15 per reel. It refuses to spend more than $1 per reel or $50 per month.
