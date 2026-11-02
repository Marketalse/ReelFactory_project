"""Stress test (part of the test suite): random transcripts (pauses, fillers, retakes, short words) + random Director plans
through the real EDL, resolver, rhythm check, face cuts and compile. Reports every crash or refusal."""
import json, os, random, shutil, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from lib import edl, director, hfbuild
import compile as comp
VOC = "يعني لما انت حاط بيج و تبيع بيه ما رقم تواصل وياك شنو تتصور الزبون راح يخسر طلب لان شغلك كله customer service".split()

def transcript():
    words, t = [], random.choice([0.0, 0.05, 0.3, 1.2])
    n = random.randint(80, 220)
    for i in range(n):
        r = random.random()
        txt = random.choice(VOC + ["300", "5", "1000"]) if r > 0.08 else random.choice(["اممم", "ااا"])
        d = random.choice([0.08, 0.12, 0.2, 0.3, 0.45, 0.7])
        words.append({"text": txt, "start": round(t, 3), "end": round(t + d, 3)})
        t += d + random.choice([0.02, 0.05, 0.1, 0.2, 0.36, 0.5, 0.9, 1.5, 3.0] if random.random() < .3 else [0.03, 0.06, 0.1])
        if random.random() < 0.04 and i > 5:          # retake: repeat the last 3-4 words
            for w in words[-random.randint(3, 4):]:
                words.append({"text": w["text"], "start": round(t, 3), "end": round(t + 0.25, 3)}); t += 0.3
    return words, t

def plan(e):
    w = e["words"]; n = len(w); spoken = director.spoken_numbers(w)
    num = random.choice(spoken) if spoken else None
    moments = []
    for _ in range(random.randint(0, 7)):
        b = random.choice(director.DIRECTOR_BLOCKS)
        vals = {"text_card": {"kicker": "القاعدة 1", "headline": "شغلك كله خدمة زبائن"},
                "split": {"value": num or "خدمة", "label": "طلب تخسره"},
                "flash": {"word": num or "ركز"},
                "logo_card": {"logo_a": "store.svg", "name_a": "Store"},
            "name_tag": {"name": "هشام", "role": "مسوّق"}, "info_card": {"headline": "الرد السريع يبيع"},
            "number_graph": {"value": num or "70", "label": "من الزبائن", "percent": ""},
            "before_after": {"before": "رد بعد يومين", "after": "رد خلال دقيقة"},
            "tier_list": {"title": "ترتيب", "tier_s": "واتساب", "tier_a": "انستغرام"},
                "ui_card": {"title": "لوحة الإعلانات", "headline": "هنا النتيجة", "image": "store.svg"},
                "doc_card": {"title": "خطة المحتوى", "highlight": "رد خلال دقيقة"},
                "pixel_scene": {"scene": "meeting", "headline": "فريق التسويق"}}[b]
        moments.append({"block": b, "at_word": random.randint(0, n - 1), "duration": round(random.uniform(0.5, 6.5), 2), "values": vals})
    return {"hook": {"line1": "حاط بيج وما حاط رقم؟", "line2": "شنو تتصور؟"},
            "keyword_ids": random.sample(range(n), min(n, random.randint(0, 6))), "moments": moments,
            "punch_ins": [{"at_word": random.randint(0, n - 1), "scale": random.choice([1.1, 1.2, 1.25, 1.5])} for _ in range(random.randint(0, 12))],
            "cta": {"type": "follow", "line": "إذا عجبك المحتوى تابعني", "promise": "كل يوم شي جديد", "keyword": ""}}



class StressTest(unittest.TestCase):
    """60 random reels (pauses, fillers, retakes, very short words, zooms right after cuts) must never
    leave a gap, a piece under 0.3 s, or a plan that compile refuses. Found 3 real bugs on 2026-11-01."""
    def test_random_reels_compile(self):
        problems = []
        work = tempfile.mkdtemp()
        try:
            for seed in range(60):
                random.seed(seed)
                words, _ = transcript()
                e = edl.build(words, 0.0, words[-1]["end"])
                if any(s["t_out"] - s["t_in"] < 0.3 - 1e-6 for s in e["segments"]):
                    problems.append((seed, "edl piece < 0.3 s")); continue
                tl, err, _ = director.resolve(plan(e), e["words"], e["duration"], logos=["store.svg"])
                if err:
                    continue
                tl["face_cy"] = 0.36
                cuts = director.face_cuts(tl, e["segments"])
                if any(abs(a["t_out"] - b["t_in"]) > 1e-3 for a, b in zip(cuts, cuts[1:])) or abs(cuts[-1]["t_out"] - tl["duration"]) > 1e-3:
                    problems.append((seed, "gap between face pieces"))
                job = os.path.join(work, f"j{seed}"); os.makedirs(os.path.join(job, "assets"))
                open(os.path.join(job, "proxy.mp4"), "wb").write(b"0")
                open(os.path.join(job, "assets", "store.svg"), "w").write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"/>')
                json.dump(tl, open(os.path.join(job, "timeline.json"), "w")); json.dump(e, open(os.path.join(job, "edl.json"), "w"))
                try:
                    comp.compile_job(job)
                except hfbuild.BuildError as ex:
                    problems.append((seed, str(ex)))
        finally:
            shutil.rmtree(work, ignore_errors=True)
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
