#!/usr/bin/env python3
"""Measure the NATURAL box of each block (the rectangle its visible text and shapes cover on the 1080x1920 canvas, with its longest allowed text).
A layout (templates/layouts/*.json) can then FIT a block into one of its zones by scaling and moving the block's host: the box says how big it is.
Needs node + playwright (a dev machine). Free, no AI.
    python3 scripts/measure_blocks.py              print the boxes
    python3 scripts/measure_blocks.py --write      store them in templates/blocks/registry.json as "natural_box": [x0, y0, x1, y1]"""
import json, os, shutil, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts")); sys.path.insert(0, os.path.join(ROOT, "tests"))
import test_safe_zones as tz                                              # noqa: E402  (its page builder: every block filled with its longest text)
from lib import hfbuild                                                   # noqa: E402

BLOCKS = ["hook_two_tone", "text_card", "info_card", "number_graph", "pixel_scene", "motion_card", "logo_card", "name_tag", "split", "flash", "doc_card", "ui_card", "before_after", "tier_list"]
JS = r"""
const { chromium } = require('playwright');
(async () => {
  const pages = JSON.parse(process.argv[2]);
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1080, height: 1920 } });
  const out = {};
  for (const [name, file] of Object.entries(pages)) {
    await p.goto('file://' + file); await p.evaluate(() => document.fonts.ready);
    out[name] = await p.evaluate(() => {
      for (const tl of Object.values(window.__timelines || {})) tl.seek(window.SEEK);
      const visible = el => { for (let e = el; e && e.id !== 'stage'; e = e.parentElement) { const s = getComputedStyle(e);
        if (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity) < 0.05) return false; } return true; };
      let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
      const add = r => { if (r.width < 2 || r.height < 2) return; x0 = Math.min(x0, r.left); y0 = Math.min(y0, r.top); x1 = Math.max(x1, r.right); y1 = Math.max(y1, r.bottom); };
      const w = document.createTreeWalker(document.getElementById('stage'), NodeFilter.SHOW_TEXT);
      for (let n; (n = w.nextNode());) { if (!n.textContent.trim() || !visible(n.parentElement)) continue; const r = document.createRange(); r.selectNodeContents(n); add(r.getBoundingClientRect()); }
      document.querySelectorAll('#stage *').forEach(el => { const s = getComputedStyle(el);
        const filled = s.backgroundColor !== 'rgba(0, 0, 0, 0)' || s.backgroundImage !== 'none' || el.tagName === 'IMG' || el.tagName === 'SVG' || el.tagName === 'svg';
        if (!filled || el.id === 'root' || /-(scrim|bg|glow)$/.test(el.id || '') || !visible(el)) return; const r = el.getBoundingClientRect();
        if (r.width >= 1079 && r.height >= 1900) return;            /* a full-canvas backdrop is not content */ add(r); });
      return [Math.round(x0), Math.round(y0), Math.round(x1), Math.round(y1)];
    });
  }
  console.log(JSON.stringify(out)); await b.close();
})();
"""


def main():
    if not tz.node_ok(): sys.exit("needs node + playwright")
    t = tz.SafeZoneTests(); tz.SafeZoneTests.setUpClass(); t.d = tz.SafeZoneTests.d
    pages = {b: t.page(b) for b in BLOCKS if b in hfbuild.REGISTRY["blocks"]}
    js = os.path.join(t.d, "boxes.js"); open(js, "w").write(JS)
    r = subprocess.run(["node", js, json.dumps(pages)], capture_output=True, text=True, timeout=240,
                       env=dict(os.environ, NODE_PATH=subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()))
    if r.returncode: sys.exit(r.stderr[-600:])
    boxes = json.loads(r.stdout.strip().splitlines()[-1])
    for k, v in boxes.items(): print(f"{k:14s} {v}  ({v[2] - v[0]}x{v[3] - v[1]})")
    if "--write" in sys.argv:
        p = os.path.join(ROOT, "templates", "blocks", "registry.json"); reg = json.load(open(p, encoding="utf-8"))
        for k, v in boxes.items(): reg["blocks"][k]["natural_box"] = v
        json.dump(reg, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1); print("written to", p)


if __name__ == "__main__":
    main()
