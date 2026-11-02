# Reel Factory — Decisions

One line per decision. Newest at the bottom. If a later decision changes an earlier one, the earlier line gets "(replaced)".

| Date | Decision | By | Why |
|---|---|---|---|
| 2026-11-01 | MVP is talking-head only: tighter cuts, Arabic word-pop captions, punch-ins, hook title, text card, flash, CTA card. | Hesham | The footage is a single talking-head shot and the asset library is empty. |
| 2026-11-01 | B-roll is out of scope until 3 reels are approved. | Hesham | Prove the core first. |
| 2026-11-01 | Hesham runs the pipeline day to day, one command per reel on the Mac. No autonomous agent runs. | Hesham | Predictable and cheap until it's stable. |
| 2026-11-01 | Director = Claude Haiku 5.5 to start. It automatically moves up to Sonnet 5.5 if the plan still fails validation after one repair. Selects (story choice) = Sonnet 5.5. Opus 5 is no longer used in the pipeline. | Hesham + Claude | Haiku is enough for a constrained JSON plan checked by a validator. Choosing the story is the step that needs judgement. A/B Haiku vs Sonnet on the first 3 clips. |
| 2026-11-01 | Spend is counted per finished reel (job). Shared work on one source take (transcript, fix, selects) is charged once to that take. | Hesham + Claude | A 5-minute take costs only cents more than a 1-minute take, because cutting is done locally. |
| 2026-11-01 | Per-reel cap: warn $0.30, hard stop $1.00. Monthly hard stop $50. Both are checked in code before every paid call. | Hesham + Claude | With Haiku as Director the expected cost is ~$0.10 per reel, so the old $1 / $2.50 levels had no meaning. |
| 2026-11-01 | Review deliverable: small, fast, low-quality draft MP4 + an editable package (clean cut, graphics layer with transparency, captions file, timeline file, HyperFrames project). Final after approval: high-quality 1080×1920 MP4. | Hesham | Hesham can make small tweaks himself and export without a full re-render. |
| 2026-11-01 | Telegram is removed from the whole project: plan, docs and code. | Hesham | Not needed; Hesham works locally. |
| 2026-11-01 | Project moves to a private GitHub repo (code and documents only; video stays on the Mac and is git-ignored). | Hesham | History, review, and Claude can build and test code. |
| 2026-11-01 | Default transcription: whisper large-v3-turbo (was medium). | Hesham | Better Iraqi-Arabic accuracy; local, $0. |
| 2026-11-01 | CTA: one master reel, but the final CTA card is rendered twice — one Instagram version, one TikTok version (local render, $0). Default CTA type = "follow" with a reason; "comment a keyword" only for a reel that has something to send (e.g. علقلي متجر was one video only). | Hesham + Claude | Different audiences per platform; Instagram rewards saves/shares, TikTok rewards follows/part 2. |
| 2026-11-01 | Reel length: 40–90 s (was 30–45 s). Story choice looks for 40–90 s ranges; a chapter text card every ~15–20 s to hold attention on longer reels. | Hesham | Business/marketing content needs more talk time. |
| 2026-11-01 | Captions: up to 3 words on screen, centred in the lower-middle (below the face, above the app buttons). Keyword in lime + heavier weight + small pop. | Hesham | — |
| 2026-11-01 | Music bed under the voice (auto-lowered while speaking) and sound effects (whoosh on layout change, pop on keyword, ding on numbers), both from a licensed library, kept as separate tracks in the edit package. | Hesham | — |
| 2026-11-01 | Digits on screen are always Western (0–9), also inside Arabic text. | Hesham | Matches the references. |
| 2026-11-01 | Reference reels: ref5_B_counters (main) + ref3_B_split (layout). Add a "split" block (text card top, face bottom) to the MVP — it needs no outside assets. | Claude (Hesham delegated) | Both are talking-head "Format B", 59–72 s, closest to the new 40–90 s length. |
| 2026-11-01 | Script rule for captions: English words Hesham says (customer service, page, ads, store…) are written in Latin letters; Arabic words in Arabic. Exact spellings live in config/glossary.json. | Hesham | Keeps business terms readable and searchable. |
| 2026-11-01 | One reel can come from several clips. Ingest takes a folder of clips, normalises each to the same proxy format, joins them in order into one timeline, and keeps a map back to the original files. Transcript, story choice and cutting then work on the joined timeline. Repeated lines (retakes): last take wins unless Hesham picks another. | Hesham | Hesham usually records a topic in several takes. |
| 2026-11-01 | Gate 0 = transcript review. The pipeline writes transcript_review.txt (one phrase per line with its time). Hesham fixes words there; timings are kept. Captions can also be fixed later in the edit package. Comparing the raw and the fixed text gives the transcription error rate automatically (this is the D2 measurement). | Hesham + Claude | Hesham wants to fix words himself without a re-render. |
| 2026-11-01 | Every run writes run.log in the job folder, so a stop is never unexplained again. | Claude | The IMG_0020 run stopped with no record of why. |
| 2026-11-01 | Each reel arrives as one inbox folder: clips/ (footage), assets/ (logos SVG/PNG, screenshots), refs/ (optional reference videos for this reel), brief.md (optional short notes). | Hesham | Every piece of content has its own logos and references. |
| 2026-11-01 | Assets and references are copied into a growing library (library/assets, library/refs) with tags, so they can be reused later and eventually support B-roll. | Hesham + Claude | Build the library over time instead of buying packs up front. |
| 2026-11-01 | New MVP block: logo_card (one logo, or a pair "X vs Y" / "X + Y"). The Director may only use logos that exist in the job's assets/ folder; the validator checks this. | Claude | References 3, 5, 6 use logo pairs; it needs no outside assets. |
| 2026-11-01 | SVGs are cleaned on ingest (scripts and external links removed) and a PNG copy is made; PNGs must have a transparent background or they get a rounded card behind them. | Claude | SVGs run in the browser renderer; safety and consistent look. |
| 2026-11-01 | Hesham's previous videos go into references/own/ as the main taste reference (global, used for every reel). Per-reel refs/ are extra hints for that reel only. Each reference is described once (cached), not re-analysed every run. | Hesham + Claude | Your own best videos are better references than other creators'. |
| 2026-11-01 | PROPOSED: Adopt Higgsfield-style "moments": effects cued to spoken words; every moment automatically gets SFX + punch-in + small shake + spring text; finishing pass (grain, vignette, colour) on every render; energy targets measured from Hesham's own best reels. | Claude (awaiting Hesham) | Higgsfield's own editing workflows work this way. |
| 2026-11-01 | PROPOSED: Review committee before Gate 2 — Script critic, Visual critic, Audience critic (AI, independent) + measurements (code). Weighted score; ≥7.5 goes to Hesham, 6–7.4 one auto-fix, <6 back to plan, max 2 auto rounds. Script critic also scores the 3 story options at Gate 1. | Hesham (idea) + Claude (design), awaiting approval | Hesham wants every reel scored before he sees it. |
| 2026-11-01 | PROPOSED: Calibrate the committee with real results: performance.csv (views, avg watch %, 3 s hold, saves, shares, follows) 48 h after posting; weights adjusted monthly. | Claude (awaiting Hesham) | Without real results, scores are only opinions. |
| 2026-11-01 | PROPOSED: Per-reel warning raised to $0.45 (stop stays $1.00, monthly $50) because the committee adds up to ~$0.20 per reel. | Claude (awaiting Hesham) | The $0.30 warning would trigger on almost every reel. |
| 2026-11-01 | Transcription model is whisper **large-v3** (replaces large-v3-turbo, which HyperFrames' transcriber does not offer). Engine forced to whisper, language ar. | Claude (correction of the earlier decision) | Checked against `hyperframes transcribe --help` v0.8.226. |
| 2026-11-01 | **Autopilot:** Hesham only comments on / approves the finished draft, on the dashboard Reels page (Make reel, Send changes, Approve). Gate 0 (transcript) and Gate 1 (story) run automatically: highest-scored story, words fixed by comments `old => new`. Mac notification when a draft or the finals are ready. | Hesham | Stepping through every gate was too much work. |
| 2026-11-01 | Editor = **CapCut** (HyperFrames desktop app for bigger edits). On Approve the pipeline also makes `edit_package/1_video.mp4` (cut + zooms + sound) and `2_graphics.mov` (all graphics, transparent ProRes 4444, ~17 MB/s) that line up in CapCut, plus `captions_ar.srt`. No CapCut project file: CapCut has no supported import format. | Hesham | Small tweaks without a full re-render. |
| 2026-11-01 | **Upload page** (`dashboard/make.html`, the dashboard's home page): drop the video(s), optional logo and notes, click *Make my reel*; files are copied into `inbox/<name>/` by the browser (originals stay where they are), then a live progress bar (5 steps, %, time left, learned from earlier reels' timing) runs until the draft is ready; comment / approve / download on the same page. Accepts MP4, MOV, AVI, WebM (also M4V, MKV). Subtitles are automatic (no SRT slot); background music shows "coming soon" until T23. Opened without the server it runs as a demo. | Hesham (request) + Claude (build) | No Finder folders, no wrong copies of the project; one page for the whole job. |
| 2026-11-01 | `Reel Factory.command` says what it is doing, warns when the copy is a ZIP download (no updates), and if a dashboard from another copy of the project is running it stops that one and starts this one. | Claude | Hesham opened a ZIP copy in Downloads while the real copy's dashboard was running. |
| 2026-11-01 | Reel Factory has **its own Nous API key** in `~/.reelfactory/nous_api_key` (outside the repo, file mode 600). Order: env `RF_API_KEY` → own key file → Hermes' login (`~/.hermes/auth.json`). | Hesham | Spend is separated from Hermes, and an expired Hermes login no longer stops reels (HTTP 401 on test run). |
| 2026-11-01 | Plan **P8 Independent + smarter** (tasks T53–T65 on the board): Reel Factory runs on its own Nous key with no Hermes dependency; spend capped in the code and watched in the Nous portal; cheaper models only after a bake-off on real footage shows equal quality; comments become lessons. Hermes stays an optional helper for development tasks. The board gets a **Plan table** view. | Hesham (goal) + Claude (plan) | Fewer moving parts, lower cost without losing quality. |

## 2026-11-01 · v2: independent of Hermes
- The API key comes only from `RF_API_KEY` or `~/.reelfactory/nous_api_key` (saved from the page's **Settings**). The Hermes login is no longer read.
- ffmpeg/ffprobe: PATH, then `~/.reelfactory/tools`, then Homebrew. If only the old Hermes copy exists it is copied once into `~/.reelfactory/tools` (the Hermes folder is never changed).
- The dashboard refuses POSTs whose Origin isn't the dashboard itself, so other websites can't start, approve or change settings.

## 2026-11-01 · v2: auto-start and one-click update
- "Turn on auto-start.command" installs a LaunchAgent (com.reelfactory.dashboard) that runs scripts/autostart.sh at login (git pull --ff-only, then the dashboard). It records the Terminal PATH so node/npx/ffmpeg are found. "Turn off auto-start.command" removes it.
- Settings → "Get the latest version" runs git pull --ff-only (refused while a reel is being made) and restarts the dashboard in place.

## 2026-11-01 · Cover image with every reel
- Look from Hesham's reference: dark brand background with dot grid, lime topic pill, two-line title (white + lime) = the hook, his photo in the lower half, optional violet sticker and lime formula card.
- Text comes from his words: the hook, and the AI's cover fields (tag, sticker, formula card) are dropped if too long or if they show a number he didn't say.
- Photo: his upload (Extras → Cover photo, or "Use my photo" after the draft), else the sharpest of 10 frames from the take. "Use my own cover" uses his image as is.
- Rendered by `scripts/cover.py` with HyperFrames snapshot (no extra tools). A cover problem never stops the reel.

## 2026-11-01 · Reel results, step 1: typed in by hand
- Each finished reel has a "How did it do?" box: platform, 2/7/30 days after posting, views, average watch time, watched-to-end %, likes, comments, shares, saves, follows. Stored in jobs/<job>/performance.json; the Results page and CSV join them with what the edit was (length, hook, cards, zooms, own cover).
- Step 2 (later, T76): read the same numbers from linked Instagram/TikTok accounts (read-only). Learning rules start at 5 reels with results.

## 2026-11-01 · No CTA for now: clean reels
- Hesham: "keep my video clean since I'm not creating greedy commercial video, I'm focusing on attracting people attention then I would change my strategy."
- `config/brand.json → cta.enabled = false`: no end card, no follow ask, no handle, no comment keyword. The reel ends on his face with captions to the last word. The AI editor is told so and may place moments up to the end.
- To bring it back: set `cta.enabled` to true (wording in the same block). Covered by tests/test_p3.py (CleanEndingTests + DirectorTests with it on).

## 2026-11-01 · Music is added when posting; the factory adds sound effects
- Hesham mostly uses trending Instagram music, added in the app when posting (sometimes CapCut music). Trending tracks can't be baked into the file (rights + they change weekly).
- So: finals carry his voice + sound effects only (`audio.music.enabled` false). He picks the trending track in Instagram/TikTok. The CapCut package keeps voice, graphics and sound on separate tracks for reels where he wants CapCut music.
- Next: learn SFX style and pace from his 11 best reels (references/own/best_reels.md), then build a small licence-safe SFX set (T23). An optional licensed music bed may come later, per reel.

## 2026-11-01 · Approve = one final video, then the cover
- Hesham: drop the Instagram / TikTok / CapCut steps after Approve. Now: (1) one high-quality final video `final/reel_vN.mp4`
  (no handle or end card, so both platforms get the same file), (2) the cover suggestion `review/cover.jpg`, made after the video.
- The final page shows the final preview, a download button, a "Want changes?" box (makes a new draft; approve again → reel_v(N+1)),
  and the cover with "Upload my own cover". The draft page no longer shows the cover.
- CapCut layers are no longer made (code kept in render.capcut_layers if ever wanted again). Old reels' per-platform files still show.

## 2026-11-01 · Repository tidied
- Main folder keeps only what Hesham opens: README (map), HOW_TO, AGENTS, the 3 .command files. `DECISIONS.md` and `SOP.md` moved to `docs/`; ideas to `docs/ideas/`.
- Old planning files (diagnosis, restructure plan, Higgsfield notes, cost model + calculator, inputs list, one-time import script, empty visual ledger) moved to `archive/planning-2026-11-01/`.
- Empty `templates/prompts` and `templates/schema` removed (prompts live in the scripts). Brief template is now `inbox/BRIEF_TEMPLATE.md`; the safe-zone guide source sits in `references/`.
- No code path the Mac relies on moved (scripts/, dashboard/, templates/blocks/, style/, config/, the .command files and auto-start).

## 2026-11-01 · Backup to Google Drive / iCloud Drive (no database yet)
- Settings → Backup: one ZIP of the small text files (jobs/*: job, plan, transcript, results, cost, report, logs; config; lessons; task board; expenses; briefs) into the Google Drive for desktop or iCloud Drive folder on the Mac → "Reel Factory backup". Never videos, images, audio or keys. Newest 30 kept.
- Automatic once a day while the dashboard runs (can be switched off). Nothing is uploaded by us: the Drive/iCloud app syncs the folder.
- A real database (e.g. Supabase) waits until results come in automatically or more than one device/person needs the data.

## 2026-11-02 · Ready-to-post score instead of an outside "virality predictor"
- Reviewed github.com/juanls1/TikTok-Virality-Predictor: trained only on 1,000 already-trending English TikToks from Dec 2020 (no flops), 99% of its targets sit near 0 so its low error is meaningless, Windows-only, text model missing, no licence. Not used.
- Built `scripts/ready_score.py`: 0-100 from 10 checks on the reel's own files (first word ≤0.5 s, title from frame 0, 40-60 s, longest still ≤2.6 s, highlighted keywords, captions = speech, loudness, no black/frozen, cards + zooms, cover on finals). Up to 3 concrete tips. Shown on the draft and final pages; saved in jobs/<job>/ready_score.json and next to the real numbers on Results/CSV so the checks can be re-weighted from Hesham's own results later (T76). Free, local, not a view prediction.

## 2026-11-02 · Task board in plain words
- "Review" shows as "Built, needs your OK"; a task whose dependency is built is no longer shown as waiting. Summary: Built so far %, Needs your OK (Show them / Mark all done), Your turn, Claude next, Parked for later, plus "How to read this board".
- Committee and block-sample tasks parked in P7 (autopilot works without them); real-reel tasks (T42, T43) moved to review with evidence.

## 2026-11-02 · Edit page: manual editing in the dashboard (Premiere-style)
- Hesham wants to edit himself, like Premiere's text-based editing. New page `dashboard/edit.html` (opened from a draft/final: "✂ Edit it yourself"): transcript (cut / restore / highlight / fix spelling), live preview over the proxy video, properties, and a timeline (Cards, Title, Zooms, You, Voice, Words) with drag to move/resize, add and delete, undo/redo.
- Edits are stored in SOURCE word numbers (`jobs/<job>/manual_edit.json`: drop / keep / texts) so a cut never moves a card onto the wrong word; `lib/manual_edit.py` rebuilds the cut (edl.build gained drop/keep/texts) and re-checks the plan with the same rules as the AI (director.resolve). Saving is refused while a rule is broken; every save backs up the previous files in `edits/<time>/`.
- "Save & make new draft" runs `reel.py --rebuild`: compile + draft + report only, $0. Later `--fix` comments keep the manual cuts (st_edl reads manual_edit.json).
- The live preview is approximate (HTML overlays on the source video); the exact look is the rendered draft.
