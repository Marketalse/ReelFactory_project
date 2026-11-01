# Reel Factory SOP — raw clip to approved reel

How Hermes turns one raw clip into a 30–45 s reel. AGENTS.md holds the rules (brand, render
contract, limits). This file holds the **order** of work.

**Hesham touches the pipeline twice:** he picks the story (Gate 1) and approves the preview (Gate 2).
Everything else runs without him.

```
A Preflight ─▶ B Ingest (script) ─▶ C Transcribe ─▶ D Selects ─▶ [GATE 1: Hesham picks]
   ─▶ E Plan ─▶ F Build on proxy ─▶ G Verify ─▶ H Preview ─▶ [GATE 2: Hesham approves]
   ─▶ I Render ─▶ J Learn
```

**Cheap-model rule:** steps A, B and the mechanical parts of C, G and I are scripts and commands,
with no LLM reasoning. Spend tokens only on D (choosing the story), E (copy and plan) and on reading
snapshot frames.

---

## Shooting settings (for Hesham, set once on the iPhone)
Settings → Camera:
- Record Video: **4K at 30 fps** (or 1080p at 30). 60 fps doubles file size for no gain on a talking head.
- Formats: **Most Compatible** (H.264).
- **HDR Video: off.** iPhone HDR footage looks washed out or wrong unless it is tone-mapped.

Shoot in a quiet room, phone at eye level, about 1 m away. Say the hook line first, then pause for 2 s.
That gives the editor a clean first frame.

---

## A · Preflight (start of every session)
```bash
node --version && ffmpeg -version | head -1
npx hyperframes doctor
npx hyperframes preview --status
df -h .
```
**ASR smoke test:** transcribe a 5 s sample with the chosen engine (see C). If it fails, fix it now,
before any footage arrives. Stop and report on any failure.

## B · Ingest (one command)
```bash
scripts/ingest.sh inbox/IMG_0011.MOV <slug>
```
The script:
1. Moves the clip to `assets/raw/` and makes it read-only.
2. Probes it, including HDR and rotation.
3. Builds `proxy.mp4`: 1080×1920, 30 fps, H.264, tone-mapped to SDR.
4. Extracts `audio16k.wav`, `silences.txt` and `loudness.txt`.
5. Verifies the proxy's size and duration.
6. Writes `job.json` with status `ingested`.

**All editing uses `proxy.mp4`.** HEVC, 4K60 and HDR sources are slow or unreliable in a browser
renderer, and the output is 1080×1920 anyway.

## C · Transcribe
Engine preference, best first:
1. **HyperFrames built-in:** `npx hyperframes transcribe`. Check its flags in `/hyperframes-cli`
   before first use. It avoids Python entirely.
2. **whisper.cpp** (`whisper-cli`, `large-v3` model, `-l ar`). It's a native binary with no NumPy,
   and fast on Apple Silicon.
3. **faster-whisper in its own venv** — never in the system Python:
   ```bash
   python3 -m venv .venv-asr && .venv-asr/bin/pip install faster-whisper
   ```

Always pass the language (`ar`) and use a large model; small models garble Iraqi dialect.
Output `transcript.json` with word-level timestamps (timestamps come only from the ASR engine).

**Correction pass (model: `claude-haiku-5.5`, alt `claude-haiku-4.5`; see `model/MODELS.md`).** Claude cannot
hear audio, so send it the whisper *text* only (never audio/video) and ask it to fix Iraqi-dialect spelling,
brand names and English terms. Keep every word's `start`/`end`; only replace `text`. Save the raw ASR as
`transcript_raw.json`, diff against the corrected one, then set `transcript.verified: true`.

## D · Selects (the real editing decision)
*Model: shot log from sampled stills by `claude-sonnet-5.5` (fallback local `qwen3-vl:4b`); never raw video.*
A 5-minute take becomes a 36 s reel by **choosing**, not by templating. From the transcript:
- Propose **3 candidate stories** of 30–45 s. Each one gives:
  - the source time ranges
  - a hook line taken from the speaker's own words
  - a one-line payoff
  - why it works
- The hook is the strongest line in the take, wherever it occurs. It doesn't have to come from the first seconds.
- Use `silences.txt` to tighten: cut pauses over 0.4 s, false starts and filler.
- Write the stories to `job.json → selects`.

### GATE 1 → Hesham
Send one short message:
- the 3 stories, each with its hook line and duration
- a still frame for each

He replies with a number. Status → `planned` after his pick.

## E · Plan (content picks the slots)
*Director model: `claude-opus-5`, one call per pass, JSON only; every beat must name its media source.*
Build `scene_plan.json` from the chosen select:
- **Counter:** only if a real number is spoken. Never invent one to fill a slot.
- **FX:** one deliberate transition at a natural turn in the story.
- **Captions:** cover every spoken word.
- **CTA:** use the locked text (e.g. `علقلي متجر`) plus a one-line promise of what the commenter receives.
- Read the visual ledger and lessons first (AGENTS.md §6, §9).
- Search the registry for every slot: 3 candidates each.

### Optional formula: AI-tool explainer
When the reel is an AI-tool explainer, use the formula in `references/ai-tool-reel-teardown.md`:
- 32–42 s, 8–10 layout cuts, visual change ≈ every 1 s
- Five layout modes: A Split, B Full B-roll, C White card, D Face punch-in, E CTA
- Hook: two-line title + claim; Reveal: "It's called…" / problem; Proof: 3–5 beats with screen proof; CTA: comment "WORD"
- Captions: 1–3 words, word-by-word sync; one keyword per phrase in italic serif accent colour
- Script length ≈ 100–120 words, spoken fast with zero dead air

## F · Build on the proxy
- Run `git commit` before each scene.
- Use the real footage from the first build. A text-only teaser proves layout but not
  decode, sync, captions or render time, which are where reels actually fail.

## G · Verify
`npm run check`, then `snapshot` at the hook, every cut, and the last 2 s. Check:
- Arabic RTL joins
- captions inside the safe zones
- lip-sync at one mid-point
- voice loudness

**Vision QA gate (required before preview; model `claude-sonnet-5.5` on 8 stills after lint, fallback `qwen3-vl:4b`):**
- Inspect still frames from at least 3 points: hook, mid-reel, CTA.
- Confirm every beat shows a different visual source: different video segment, alternate angle, still, or B-roll.
- Confirm there is no dead stretch >3 s with no visual change; if a still must hold, mark it `data-hold`.
- Confirm captions remain readable against the current background; if contrast fails, add a dark overlay or move text.
- If Vision QA fails, fix the composition and re-check before sending the preview link.

## H · Preview → GATE 2
`npx hyperframes preview --background`, confirm with `--status`, and send Hesham the link plus the
job report (AGENTS.md §8). **One question at most.** Never end with a menu of options.
The agent picks the next step itself unless Hesham has to decide.

## I · Render (after approval only)
Use `--quality high --strict`, then check that the file exists and that its duration matches.
Draft renders count toward the cap of 3.

## J · Learn
- Append the reel to the visual ledger.
- Write at most 3 lessons, including every failure that was fixed, under *Known failures*.
- Status → `learned`.

---

## Folder rules
| Path | Use |
|---|---|
| `inbox/` | Drop zone only. Ingest empties it. |
| `assets/raw/` | Originals, read-only |
| `jobs/<date>-<slug>/` | Everything for one reel |
| `templates/` | Never edited during a job. Copy a template into the job folder, then edit the copy. |
| `spikes/` | Experiments only. Never referenced by a job. |
| `config/brand.json` | Handle, CTA defaults, brand tokens. Hesham sets these once. |
