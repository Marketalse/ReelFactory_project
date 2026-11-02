import os, subprocess, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from lib import frames_dedup as fd  # noqa: E402


def frames(n, step=2.0):
    return [{"t": i * step, "file": f"f{i}.jpg"} for i in range(n)]


class DedupTests(unittest.TestCase):
    def test_same_looking_frames_are_dropped_but_changes_and_gaps_are_kept(self):
        fs = frames(40)
        hs = {f["file"]: 0 for f in fs}                       # a talking head: all identical...
        for i in (10, 11):
            hs[f"f{i}.jpg"] = (1 << 40) - 1                   # ...except two frames where something changes
        kept = fd.distinct(fs, "", hasher=lambda p: hs[os.path.basename(p)])
        ts = [f["t"] for f in kept]
        self.assertLess(len(kept), 15); self.assertEqual(ts[0], 0.0)
        self.assertIn(20.0, ts)                                # the change at frame 10 is kept
        self.assertTrue(all(b - a <= fd.MAX_GAP + 0.01 for a, b in zip(ts, ts[1:])))      # still covers the whole take

    def test_small_sets_and_unreadable_frames_are_kept(self):
        self.assertEqual(len(fd.distinct(frames(6), "", hasher=lambda p: 0)), 6)
        kept = fd.distinct(frames(30), "", hasher=lambda p: None)
        self.assertEqual(len(kept), 30)                        # can't tell = keep (never drop what we can't compare)

    def test_never_fewer_than_the_minimum(self):
        kept = fd.distinct(frames(60, 0.5), "", hasher=lambda p: 0, max_gap=100)
        self.assertGreaterEqual(len(kept), fd.MIN_KEEP); self.assertEqual(kept, sorted(kept, key=lambda f: f["t"]))

    def test_real_image_hash(self):
        d = tempfile.mkdtemp()
        for n, src in (("a.png", "testsrc2"), ("b.png", "testsrc2"), ("c.png", "smptebars")):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{src}=size=270x480:rate=1:duration=1", "-frames:v", "1", os.path.join(d, n)], check=True)
        ha, hb, hc = (fd.image_hash(os.path.join(d, n)) for n in ("a.png", "b.png", "c.png"))
        self.assertEqual(ha, hb); self.assertGreater(bin(ha ^ hc).count("1"), fd.BITS)
        self.assertIsNone(fd.image_hash(os.path.join(d, "missing.png")))


if __name__ == "__main__":
    unittest.main()
