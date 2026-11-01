# How Hermes works with the task board

Give Hermes this file at the start of every session. `dashboard/tasks.json` is the **only** task list. Hermes never creates status, index, queue or board files of any other kind.

## Each session
1. Read `dashboard/tasks.json`, `DECISIONS.md` and `AGENTS.md`. Nothing else unless the task needs it.
2. Pick **one** task where all of these are true:
   - `owner` is `"Hermes"`
   - `status` is `"todo"`
   - every task in `depends` is `"done"`

   Take the lowest ID first. If none qualifies, say so in one line and stop.
3. Set that task's `status` to `"in_progress"`. Add a `log` entry: `{"time": "<now>", "who": "Hermes", "task": "<id>", "change": "started"}`. Increase `version` by 1.
4. Do the task. Do nothing outside it.
5. When finished:
   - Set `status` to `"review"`. **Never `"done"`**: only Hesham marks tasks done.
   - Put the proof path (file, log, screenshot) in `evidence`.
   - Write 1–3 lines in `notes` about what happened.
   - Update `updated`, add a `log` entry, and increase `version`.
6. If blocked: set `status` to `"blocked"`, write the reason and what you need from Hesham in `notes`, add a log entry, and stop. Never retry the same failing step more than 3 times.

## Rules
- One task per session. No new tasks unless Hesham asks. If you discover a needed task, add it with `owner: "Hesham"` and status `todo`, and say so in its notes.
- Edit `tasks.json` with a script or careful JSON edit; keep it valid JSON. If the dashboard server is running, saving through it is safer: it refuses a save when the file changed underneath.
- Don't edit tasks owned by Claude or Hesham except to add a note.
- Never claim something works without evidence in the `evidence` field.
- Spending money (any paid model call) only inside `scripts/reel.py`, which enforces the caps.
