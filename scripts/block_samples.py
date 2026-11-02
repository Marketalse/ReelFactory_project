#!/usr/bin/env python3
"""Build one sample reel that shows every block, for Hesham to approve the looks (task T24/T25).

    python3 scripts/block_samples.py --video jobs/<job>/proxy.mp4 [--start 0] [--out jobs/_samples/blocks]
    python3 scripts/block_samples.py --test-pattern            (no footage: a generated test video)

Then, inside the output folder:
    npx hyperframes check             (must pass)
    npx hyperframes snapshot --at 0.3,3.5,6,9,12.6,14.5,16,19
    npx hyperframes render --quality draft -o sample_draft.mp4

Free: no model calls. Sample text is Hesham's own line from the IMG_0020 take.
"""
import argparse, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import config as cfg      # noqa: E402
from lib import hfbuild            # noqa: E402

LOGO = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"><rect width="200" height="200" rx="44" fill="{bg}"/>
<text x="100" y="128" font-family="sans-serif" font-size="96" font-weight="700" fill="{fg}" text-anchor="middle">{t}</text></svg>"""

# Sample words on the reel timeline (Hesham's own phrasing from the IMG_0020 transcript).
SAMPLE = ("يعني لما انت حاط بيج و تبيع بيه و ما حاط رقم تواصل وياك شنو تتصور الزبون راح يسوي "
          "لازم يكون عندك customer service لان شغلك كله خدمة زبائن و اذا ما ترد عليه راح تخسر 300 طلب "
          "بالشهر و هاي مو مزحة تابعني حتى تتعلم كل يوم شي جديد").split()


def test_pattern(path, dur):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", f"testsrc2=size=1080x1920:rate=30:duration={dur}",
                    "-f", "lavfi", "-i", f"sine=frequency=220:duration={dur}",
                    "-c:v", "libx264", "-g", "30", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", path], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", help="a proxy.mp4 (1080x1920) of Hesham talking")
    ap.add_argument("--start", type=float, default=0.0, help="where in the proxy to start (seconds)")
    ap.add_argument("--test-pattern", action="store_true", help="no footage: use a generated test video")
    ap.add_argument("--new-blocks", action="store_true", help="sample reel of the 5 newer blocks (name tag, info card, number graph, before/after, tier list)")
    ap.add_argument("--out", default=os.path.join(cfg.ROOT, "jobs", "_samples", "blocks"))
    a = ap.parse_args()
    D = 24.0 if a.new_blocks else 21.0
    os.makedirs(a.out, exist_ok=True)
    if a.video:
        video = os.path.abspath(a.video)
    elif a.test_pattern:
        video = os.path.join(a.out, "test_pattern.mp4"); test_pattern(video, D + 1)
    else:
        sys.exit("give --video <proxy.mp4> or --test-pattern")

    os.makedirs(os.path.join(a.out, "assets", "logos"), exist_ok=True)
    c = cfg.BRAND["colors"]
    open(os.path.join(a.out, "assets", "logos", "sample_a.svg"), "w").write(LOGO.format(bg=c["secondary"], fg="#ffffff", t="A"))
    open(os.path.join(a.out, "assets", "logos", "sample_b.svg"), "w").write(LOGO.format(bg=c["accent"], fg=c["bg"], t="B"))

    s0 = a.start
    face = lambda i, t0, t1, **k: dict(id=f"seg{i}", t_in=t0, t_out=t1, src_in=s0 + t0, **k)
    face_cuts = [
        face(0, 0, 2.6),
        face(1, 2.6, 5.0, scale=1.28, cy=0.36),           # punch-in
        face(2, 5.0, 7.5),                                  # under the text card (hidden, voice continues)
        face(3, 7.5, 11.5, y=480),                          # split: face moves to the lower half
        face(4, 11.5, 14.0),
        face(5, 14.0, 15.0),                                # under the flash
        face(6, 15.0, 17.0, scale=1.18, cy=0.36),
        face(7, 17.0, D),
    ]
    words, t = [], 0.15
    for w in SAMPLE:
        words.append({"text": w, "start": t, "end": t + 0.3}); t += 0.36
        if w in ("يسوي", "زبائن", "مزحة"): t += 0.3       # natural pauses
    kw = [i for i, w in enumerate(words) if w["text"] in ("بيج", "customer", "300", "تخسر", "تابعني")]
    if a.new_blocks:                                  # more words so the captions run the whole sample
        t = 0.15; words = []
        for w in (SAMPLE * 2):
            words.append({"text": w, "start": t, "end": t + 0.3}); t += 0.36
    cap_words = [w for w in words if w["start"] < D - 0.4]
    scenes = [
        dict(id="hook", block="hook_two_tone", t_in=0, t_out=2.6, values={"line1": "حاط بيج وما حاط رقم تواصل؟", "line2": "شنو تتصور؟"}),
        dict(id="card1", block="text_card", t_in=5.0, t_out=7.5, values={"kicker": "القاعدة 1", "headline": "شغلك كله خدمة زبائن", "sub": "مو بس الإعلان"}),
        dict(id="split1", block="split", t_in=7.5, t_out=11.5, values={"value": "300", "label": "طلب تخسره بالشهر بدون رد"}),
        dict(id="logos1", block="logo_card", t_in=11.5, t_out=14.0, values={"logo_a": "assets/logos/sample_a.svg", "name_a": "Page", "joiner": "+", "logo_b": "assets/logos/sample_b.svg", "name_b": "Store"}),
        dict(id="flash1", block="flash", t_in=14.0, t_out=15.0, values={"word": "300"}),
        dict(id="cta", block="cta_card", t_in=17.0, t_out=D, values={"line": "إذا عجبك المحتوى تابعني", "promise": "كل يوم شي جديد بالتسويق والبزنس", "keyword": "", "handle": "@hesham_alshakarchi"}),
        dict(id="caps", block="captions", t_in=0, t_out=D, values={},
             groups_html=hfbuild.caption_groups(cap_words, kw, "caps")),
    ]
    # captions hide while a full-screen card or the CTA is up
    full = [(5.0, 7.5), (14.0, 15.0), (17.0, D)]
    keep = [w for w in cap_words if not any(s <= w["start"] < e for s, e in full)]
    kw2 = [keep.index(w) for w in keep if w in [cap_words[i] for i in kw]]
    scenes[-1]["groups_html"] = hfbuild.caption_groups(keep, kw2, "caps")
    if a.new_blocks:
        face_cuts = [face(0, 0, 3.0), face(1, 3.0, 3.5, scale=1.28, cy=0.36), face(2, 3.5, D)]
        scenes = [
            dict(id="hook", block="hook_two_tone", t_in=0, t_out=2.6, values={"line1": "حاط بيج وما حاط رقم تواصل؟", "line2": "شنو تتصور؟"}),
            dict(id="tag1", block="name_tag", t_in=3.0, t_out=5.5, values={"name": "هشام الشكرجي", "role": "مسوّق في أربيل"}),
            dict(id="info1", block="info_card", t_in=6.0, t_out=9.5, values={"kicker": "القاعدة 1", "headline": "الرد السريع يبيع", "caption": "الزبون ما ينتظر ساعات"}),
            dict(id="num1", block="number_graph", t_in=10.0, t_out=13.5, values={"value": "70%", "label": "من الزبائن يشترون بعد الرد", "percent": "70"}),
            dict(id="ba1", block="before_after", t_in=14.0, t_out=18.0, values={"before_label": "قبل", "before": "رد بعد يومين", "after_label": "بعد", "after": "رد خلال دقيقة"}),
            dict(id="tier1", block="tier_list", t_in=18.5, t_out=D - 0.2, values={"title": "أفضل قنوات الرد", "tier_s": "واتساب", "tier_a": "انستغرام", "tier_b": "تيك توك", "tier_c": ""}),
        ]
        full = [(10.0, 13.5), (14.0, 18.0), (18.5, D - 0.2)]
        keep = [w for w in cap_words if not any(s_ <= w["start"] < e_ for s_, e_ in full)]
        scenes.append(dict(id="caps", block="captions", t_in=0, t_out=D, values={}, groups_html=hfbuild.caption_groups(keep, [], "caps")))
    idx = hfbuild.build_project(a.out, duration=D, face_cuts=face_cuts, scenes=scenes, video_src=video)
    print("built", idx)
    print("next:  cd", a.out, "&& npx hyperframes check && npx hyperframes snapshot --at 0.3,3.5,6,9,12.6,14.5,16,19")


if __name__ == "__main__":
    main()
