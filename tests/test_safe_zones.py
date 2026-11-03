"""Every template, filled with its LONGEST allowed text, rests inside the safe zone (style/SAFE_ZONES.md).
Also the cover. Needs node + playwright (dev machines); skipped otherwise."""
import json, os, re, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from lib import config as cfg, hfbuild  # noqa: E402

Z = cfg.RULES["safe_zone"]
BOX = {"x0": Z["left"], "x1": Z["canvas"][0] - Z["right"], "y0": Z["top"], "y1": Z["canvas"][1] - Z["bottom"]}
LONG_AR = "شنو تتصور الزبون راح يسوي لازم يكون عندك خدمة زبائن"
SKIP_IDS = re.compile(r"(-(scrim|bg|panel|glow)|^grid|^fade|^glow|^beam[12]|^person)$")


def long_text(n):
    t = (LONG_AR + " ") * 4
    return t[:n].rstrip() or t[:n]


def sample_values(block):
    vals = {}
    for k, v in hfbuild.REGISTRY["blocks"][block]["inputs"].items():
        if v["type"] == "string":
            vals[k] = long_text(v.get("maxLength") or 20)
        elif v["type"] == "enum":
            vals[k] = v["options"][-1]
    if block == "split":
        vals["value"] = "12,500,000"
    if block == "flash":
        vals["word"] = "الاستراتيجية"
    if block == "number_graph":
        vals["value"] = "12,500,000"; vals["percent"] = "100"
    if block == "cta_card":
        vals["handle"] = "@hesham_alshakarchi"; vals["keyword"] = "علقلي متجر"
    return vals


LOGO = "data:image/svg+xml;base64," + __import__("base64").b64encode(
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" fill="#7D53FF"/></svg>').decode()

PAGE = """<!doctype html><html lang="ar"><head><meta charset="UTF-8">
<script src="gsap.min.js"></script>
<style>@font-face {{ font-family:"Readex Pro"; src:url("ReadexPro.ttf"); font-weight:160 700; }}
:root {{ {vars} }} * {{ margin:0; padding:0; box-sizing:border-box; }}
html,body {{ width:1080px; height:1920px; overflow:hidden; background:#000; }}
#stage {{ position:relative; width:1080px; height:1920px; overflow:hidden; }}</style></head>
<body><div id="stage">{markup}</div>
<script>window.__timelines = {{}}; const VALS = {vals};
document.querySelectorAll("[data-var-text]").forEach(e => {{ if (e.dataset.varText in VALS) e.textContent = VALS[e.dataset.varText]; }});
document.querySelectorAll("img[data-var-src]").forEach(e => {{ e.src = "{logo}"; }});
</script>
{script}
<script>window.SEEK = {seek};</script></body></html>"""

MEASURE = r"""
const { chromium } = require('playwright');
(async () => {
  const [pages, box] = [JSON.parse(process.argv[2]), JSON.parse(process.argv[3])];
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1080, height: 1920 } });
  const out = {};
  for (const [name, file] of Object.entries(pages)) {
    await p.goto('file://' + file); await p.evaluate(() => document.fonts.ready);
    out[name] = await p.evaluate(([box, skip]) => {
      for (const tl of Object.values(window.__timelines || {})) tl.seek(window.SEEK);
      const bad = []; const re = new RegExp(skip);
      const visible = el => { for (let e = el; e && e.id !== 'stage'; e = e.parentElement) { const s = getComputedStyle(e);
        if (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity) < 0.05) return false; } return true; };
      const check = (r, what) => { if (r.width < 1 || r.height < 1) return;
        const m = { left: box.x0 - r.left, right: r.right - box.x1, top: box.y0 - r.top, bottom: r.bottom - box.y1 };
        const over = Object.entries(m).filter(([, v]) => v > 2).map(([k, v]) => `${k} +${Math.round(v)}px`);
        if (over.length) bad.push(`${what}: ${over.join(', ')}`); };
      const w = document.createTreeWalker(document.getElementById('stage'), NodeFilter.SHOW_TEXT);
      for (let n; (n = w.nextNode());) { if (!n.textContent.trim() || !visible(n.parentElement)) continue;
        const r = document.createRange(); r.selectNodeContents(n); check(r.getBoundingClientRect(), 'text "' + n.textContent.trim().slice(0, 20) + '"'); }
      document.querySelectorAll('#stage *').forEach(el => { const s = getComputedStyle(el);
        const filled = s.backgroundColor !== 'rgba(0, 0, 0, 0)' || s.backgroundImage !== 'none' || el.tagName === 'IMG';
        if (!filled || re.test(el.id || '') || el.id === 'root' || !visible(el) || el.closest('#photo')) return;
        check(el.getBoundingClientRect(), 'box #' + (el.id || el.className)); });
      return bad;
    }, [box, SKIP]);
  }
  console.log(JSON.stringify(out)); await b.close();
})();
""".replace("SKIP", json.dumps(SKIP_IDS.pattern))


def node_ok():
    if not shutil.which("node"):
        return False
    return subprocess.run(["node", "-e", "require('playwright')"], capture_output=True).returncode == 0


@unittest.skipUnless(node_ok(), "needs node + playwright")
class SafeZoneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        fonts = [f for f in os.listdir(os.path.join(ROOT, "style", "fonts")) if f.endswith(".ttf")]
        shutil.copy(os.path.join(ROOT, "style", "fonts", fonts[0]), os.path.join(cls.d, "ReadexPro.ttf"))
        shutil.copy(os.path.join(ROOT, "templates", "vendor", "gsap.min.js"), os.path.join(cls.d, "gsap.min.js"))

    def page(self, block):
        spec = hfbuild.REGISTRY["blocks"][block]
        dur = min(spec["duration_s"]["max"], 3.0)
        groups = ""
        if block == "captions":
            words = [{"text": t, "start": 0.2 + i * 0.3, "end": 0.45 + i * 0.3} for i, t in enumerate(["الاستراتيجية", "التسويقية", "الإلكترونية"])]
            groups = hfbuild.caption_groups(words, [1], "b", max_words=3)
        if block in ("pack_frame", "recap_chain"):                  # Format Pack: longest titles, 7 sections, both themes' worst case
            from lib import pack
            o = {"sections": [{"title": long_text(24), "kind": "step", "t_in": k * 0.4} for k in range(7)]}
            ic = ["icon-truck.svg"] * 7
            groups = (pack.frame_groups("b", o, dur, ic, "dark", long_text(18), long_text(22)) if block == "pack_frame" else pack.recap_groups("b", o, ic, "dark"))
        src = hfbuild.stamp(block, "b", dur, groups, sample_values(block))
        inner = src.split("<template>", 1)[1].rsplit("</template>", 1)[0]
        style = re.search(r"<style>.*?</style>", inner, re.S).group(0)
        script = re.search(r"<script>.*?</script>", inner, re.S).group(0)
        markup = style + re.sub(r"<style>.*?</style>|<script>.*?</script>", "", inner, flags=re.S)
        seek = 0.9 if block == "captions" else (2.9 if block in ("pack_frame", "recap_chain") else round(dur * 0.55, 2))
        f = os.path.join(self.d, block + ".html")
        open(f, "w", encoding="utf-8").write(PAGE.format(vars=hfbuild.brand_vars(), markup=markup, script=script, seek=seek,
                                                          vals=json.dumps(sample_values(block), ensure_ascii=False), logo=LOGO))
        return f

    def test_blocks_and_cover(self):
        pages = {b: self.page(b) for b in hfbuild.REGISTRY["blocks"] if b != "face_cut"}
        import cover
        j = tempfile.mkdtemp()
        v = {"line1": long_text(28), "line2": long_text(22), "tag": "STOCK TIPS NOW!!", "sticker": "OUT OF STOCK????",
             "card_label": "SAFE STOCK FORMULA HERE!", "card_value": "12,000 × 3 = 36,000"}
        photo = os.path.join(j, "p.jpg")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=gray:s=600x800", "-frames:v", "1", photo], check=True)
        proj = cover.build(j, v, photo)
        shutil.copy(os.path.join(proj, "assets", "fonts", "ReadexPro.ttf"), os.path.join(proj, "ReadexPro.ttf"))
        html_ = open(os.path.join(proj, "index.html"), encoding="utf-8").read().replace('id="root"', 'id="stage"')
        html_ = html_.replace("<head>", "<head><script>window.__timelines={}</script>", 1).replace("</body>", "<script>window.SEEK=0.5</script></body>")
        open(os.path.join(proj, "index.html"), "w", encoding="utf-8").write(html_)
        pages["cover"] = os.path.join(proj, "index.html")
        j2 = tempfile.mkdtemp(); cutpng = os.path.join(j2, "cut.png")                         # the hero layout (title behind the head) with a long hook
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=gray:s=400x700", "-frames:v", "1", cutpng], check=True)
        proj2 = cover.build(j2, dict(v, line1=long_text(28), line2=long_text(22)), photo, cut=cutpng, face={"x": .3, "y": .2, "w": .4, "h": .2})
        shutil.copy(os.path.join(proj2, "assets", "fonts", "ReadexPro.ttf"), os.path.join(proj2, "ReadexPro.ttf"))
        h2 = open(os.path.join(proj2, "index.html"), encoding="utf-8").read().replace('id="root"', 'id="stage"')
        h2 = h2.replace("<head>", "<head><script>window.__timelines={}</script>", 1).replace("</body>", "<script>window.SEEK=0.5</script></body>")
        open(os.path.join(proj2, "index.html"), "w", encoding="utf-8").write(h2)
        pages["cover_hero"] = os.path.join(proj2, "index.html")
        js = os.path.join(self.d, "measure.js"); open(js, "w").write(MEASURE)
        r = subprocess.run(["node", js, json.dumps(pages), json.dumps(BOX)], capture_output=True, text=True, timeout=180,
                           env=dict(os.environ, NODE_PATH=subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()))
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        res = json.loads(r.stdout.strip().splitlines()[-1])
        bad = {k: v for k, v in res.items() if v}
        self.assertEqual(bad, {}, json.dumps(bad, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    unittest.main()


class TemplateContractTests(unittest.TestCase):
    def test_no_visibility_tweens(self):
        """HyperFrames shows/hides clips itself; a script that sets visibility/display/autoAlpha makes them vanish in the
        real render (captions were missing from drafts until 2026-11-01) even though snapshots look fine."""
        bad = []
        for f in sorted(os.listdir(os.path.join(ROOT, "templates", "blocks"))):
            if f.endswith(".html"):
                src = open(os.path.join(ROOT, "templates", "blocks", f), encoding="utf-8").read()
                script = "".join(re.findall(r"<script>(.*?)</script>", src, re.S))
                if re.search(r"\b(visibility|display|autoAlpha)\s*:", script):
                    bad.append(f)
        self.assertEqual(bad, [])
