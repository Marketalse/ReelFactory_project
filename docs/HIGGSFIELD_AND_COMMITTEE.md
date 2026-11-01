# Reel Factory — What to learn from Higgsfield + the Review Committee

2026-11-01. The higgsfield.ai website is blocked from this session's network, so this analysis comes from Higgsfield's own published workflow instructions, read through its connector (the "reel-effects" and "Katana" editing workflows, plus the Virality Predictor tool). Those are the actual recipes its editor follows, which is more useful than the marketing pages. Third-party reviews were used only for context.

---

## Part 1 — How Higgsfield edits talking-head reels

### 1. Fixed templates, AI only fills in the values
Every effect is a **prebuilt HTML page rendered frame by frame in headless Chrome**. The AI is told: *"You choose the parameters; the scripts do the rest. Never rewrite a template."* A bad value gets an error message, and the fix is to change the value, never the files.

→ **This is exactly the compiler-plus-templates design we chose.** It confirms that the earlier failures (placeholder compositions, missing media IDs, debug text in the MP4) came from letting an AI hand-write HTML.

### 2. Effects are tied to spoken words ("moments")
An effect isn't used once. It **fires at every fitting moment of the speech**, each one cued to an exact spoken word and snapped to the stressed syllable. Their rule: *"An effect that fires once and leaves the rest empty is a failure."* Their rhythm:

| Effect | When it fires |
|---|---|
| Big word behind the head | The strongest word of each point, about every 3–5 s |
| Freeze-frame + name tag | Each new item, tool or person named, at least ~5 s apart |
| Glass graph (number goes from A to B) | Every number that is said |
| Before/after card | Every before/after comparison that is said |
| Tier list | Every ranked or listed item, at the moment it's named |
| Grade wipe | Once, early |
| Captions | Whole clip; up to 3 words at a time; y ≈ 1380 px |

### 3. "Craft" is added automatically to every moment
Their editor doesn't decide these each time; the scripts always add them:
- a recorded **sound effect** on every moment (whoosh, hit, click, shutter, ticks, riser, from a CC0 library)
- a **punch-in plus a short frame-exact shake toward the head** on each hit
- **spring motion** and letter-by-letter text
- a **finishing pass**: fine grain, gentle vignette, standard colour

That's a big part of the "viral" feel: every key word gets sound + motion + zoom, consistently.

### 4. Everything on screen comes from what was said
Same words, numbers, names and order as the speaker, spelled the speaker's way. *Never invent numbers, names or rankings; if unclear, ask.* This matches our "counter only if a number is spoken" rule.

### 5. One style per video, varied between videos
Each video picks one accent style (clean / bold / neon / red) and keeps it throughout, then varies it between videos. That matches our freshness idea, but it's simpler.

### 6. Their QA is "review like an editor" in three passes
Stills are checked at each moment's **start, peak and end**, not one frame. Then:
1. **Timing:** each moment lands on its word, nothing early or late.
2. **Space:** nothing on the face; text inside x = 120–960; nothing in the bottom 20%.
3. **Polish:** motion settles, no clipped or fallback-font text, no matte holes.

### 7. They measure a reference reel's "energy" and copy the rate, not the shots
Katana reads the reference reel frame by frame and writes an **energy map**: cuts, flashes, shake bursts, camera moves and hits **per second**. The new edit must hit the **same rates** with new content, and never copies shot for shot. Three motion reviews: rhythm/timing, spatial movement/continuity, distinctive detail/polish.

### 8. Virality Predictor
A separate paid tool that scores a finished video for hook strength, retention risk, attention and engagement. It's a prediction dashboard, not a guarantee. I could find no independent test of how accurate it is.

### What this means for Reel Factory

| Higgsfield idea | What we add | When |
|---|---|---|
| Effects cued to spoken words | Director picks **moments** by quoting the spoken word (not seconds); code snaps to the word time | MVP |
| Automatic craft per moment | Each moment automatically gets: SFX + punch-in + small shake + spring text | MVP |
| Finishing pass | Grain + vignette + colour pass on every render | MVP |
| Energy map | Measure **your own best reels** (references/own) → target rates for cuts, hits and text changes per 10 s → the validator checks the new reel against them | MVP |
| Name tag / graph / before-after / tier list | New blocks: `name_tag` (with logo), `number_graph`, `before_after`, `tier_list` (business content often ranks things) | Right after MVP |
| Big word behind the head | Needs a person cutout (matte); still unproven on your Mac | Later |
| 3-pass editor QA | Becomes the Visual member of the committee (Part 2) | MVP |
| Virality Predictor | Optional second opinion, not a gate, until we know if it's accurate | Optional |

---

## Part 2 — The Review Committee

### Purpose
Before a reel reaches you, independent reviewers score it from different angles. A weak reel is fixed automatically or sent back. You only see reels that already pass, plus the committee's report.

### Members

| Member | Looks at | What it scores (1–10 each, with timestamps) | Model | Cost per review |
|---|---|---|---|---|
| **1. Script critic** | Final-cut transcript + plan | Hook (first line makes a promise or tension?), one clear idea, payoff delivered, no filler, pace (words per second), CTA fits the content, relevant to the Iraqi audience | Sonnet (text) | ~$0.01–0.02 |
| **2. Visual critic** | Stills at each moment's start, peak and end + a contact sheet | Caption legibility, nothing on the face, safe zones, brand look, visual variety, polish (Higgsfield's 3 passes) | Sonnet (vision) | ~$0.03–0.05 |
| **3. Audience critic, "overall feel"** | Timeline summary + energy numbers + key frames + transcript | Plays an 18–30-year-old Iraqi viewer scrolling: would I stop in the first 2 s? stay to the end? comment, save, share, follow? Where would I swipe away? | Sonnet | ~$0.02 |
| **4. Measurements (no AI)** | The render itself | Time to first word, first visual change, longest still stretch, cuts/hits per 10 s vs your energy targets, loudness, caption coverage | Code | $0 |
| *Optional: Hook checker* | First seconds of the draft | Opening checks + 3 rewritten openings | Video Hook Check connector | Its own pricing |
| *Optional: Virality Predictor* | Draft video | Hook, retention risk, engagement | Higgsfield (credits) | Its own pricing |

**Rules that make it work:**
- Members are **independent**: none sees another's score, so they don't just agree with each other.
- Every criticism must give a **timestamp and a concrete fix** ("0:04–0:07 no visual change; add a punch-in on «customer service»"). Vague opinions are thrown out.
- The **chair** (code, not AI) combines the scores.

### Scoring and decision

```
Final score = 30% Hook (script critic's hook + audience "stop in 2 s")
            + 25% Script
            + 25% Visual
            + 20% Overall feel
```

| Result | What happens |
|---|---|
| Any single score below 5 | Must be fixed, whatever the total |
| Total ≥ 7.5 | Goes to you (Gate 2) with the committee report |
| 6.0–7.4 | One automatic revision using the top 3 fixes, then reviewed again |
| Below 6.0 | Back to story choice / plan; you're told why |
| After 2 automatic revisions | Goes to you anyway, with the scores; never loops forever |

### The committee also works early
Fixing a weak script after rendering is wasteful. So the **Script critic also scores the 3 story options at Gate 1**. You see each option with its hook score and one line of reasoning before you choose.

### What you receive
`committee_report.md` in the job folder:
- the 4 scores + the final score
- the top 3 fixes (applied or suggested), each with a timestamp
- 3 alternative hook lines in your own words from the transcript
- the predicted swipe-away point

### Calibration: making the scores mean "viral"
On their own, AI scores are opinions. To turn them into predictions:
1. 48 hours after posting, you type 6 numbers into `performance.csv`: views, average watch %, 3-second hold (if the app shows it), saves, shares, new follows.
2. Every month, the pipeline compares committee scores with real results and adjusts the weights. For example, if hook score predicts views well but visual score doesn't, hook weight goes up.
3. After ~20 posted reels you'll know which reviewer is actually right for **your** audience.

### Cost impact
About $0.06–0.09 per review round, 2 rounds at most, so **up to ~$0.20 per reel**. The new expected total is **~$0.25–0.30 per reel**, about $6–7/month at 24 reels.

The per-reel **warning at $0.30 would trigger too often**, so I propose **warn $0.45, stop $1.00** (monthly cap stays $50).

---

## Part 3 — Updated pipeline

```
inbox folder (clips + logos + refs + brief)
 → join clips → transcribe → fix → [GATE 0: you fix words]
 → story options + Script critic scores → [GATE 1: you pick]
 → cut pauses/fillers → Director (Haiku): moments cued to spoken words
 → validate (incl. energy targets) → compile from templates
   (each moment gets SFX + punch-in + shake automatically) → finishing pass
 → deterministic QA → COMMITTEE (script · visual · audience · measurements)
   → auto-fix up to 2 rounds
 → [GATE 2: you get draft + edit package + committee report]
 → final high-quality render (Instagram + TikTok CTA versions)
 → you post → 48 h later: performance.csv → monthly calibration
```

Sources for context: [Higgsfield AI Features guide](https://geo.higgsfield.ai/higgsfield-ai-features-guide), [Higgsfield Shorts Studio](https://higgsfield.ai/shorts-studio-intro), [AI Short Video Generator](https://higgsfield.ai/ai-short-video-generator), [CapCut's Higgsfield review](https://www.capcut.com/resource/higgsfield-ai-review), [Thred: Higgsfield AI video editing](https://thred.com/tech/higgsfield-just-levelled-up-ai-video-editing-massively/).
