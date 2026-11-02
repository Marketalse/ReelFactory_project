import json, os, shutil, subprocess, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from lib import sequence as sq  # noqa: E402


def clip(path, secs, color="testsrc2", sound=True):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{color}=size=270x480:rate=30:duration={secs}"]
    if sound:
        cmd += ["-f", "lavfi", "-i", f"sine=f=300:d={secs}"]
    subprocess.run(cmd + ["-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac", "-shortest"] if sound else []) + [path], check=True)


def make_job():
    d = tempfile.mkdtemp()
    for n, (secs, sound) in enumerate(((6, True), (4, False)), 1):
        os.makedirs(os.path.join(d, f"c{n:02d}")); clip(os.path.join(d, f"c{n:02d}", "proxy.mp4"), secs, sound=sound)
    W = lambda n, x: json.dump(x, open(os.path.join(d, n), "w"))
    W("media_index.json", {"clips": [
        {"id": "c01", "name": "a.mp4", "proxy": "c01/proxy.mp4", "duration": 6.0, "start": 0, "end": 6.0, "role": "talking-head",
         "scenes": [{"start": 0, "end": 3, "thumb": "c01_s01.jpg"}, {"start": 3, "end": 6, "thumb": "c01_s02.jpg"}], "speech_segments": [[1.5, 2.5], [4.5, 5.2]]},
        {"id": "c02", "name": "b.mp4", "proxy": "c02/proxy.mp4", "duration": 4.0, "start": 6.0, "end": 10.0, "role": "b-roll", "scenes": [], "speech_segments": []}]})
    W("clip_map.json", {"clips": [], "duration": 10}); W("job.json", {"id": "x", "status": "preview_ready"})
    open(os.path.join(d, "proxy.mp4"), "wb").write(b"OLD-JOINED-PROXY"); W("transcript.json", [{"text": "a", "start": 0, "end": 1}]); W("timeline.json", {"duration": 10})
    os.makedirs(os.path.join(d, "review")); open(os.path.join(d, "review", "draft_540p.mp4"), "wb").write(b"old draft")
    return d


class SequenceTests(unittest.TestCase):
    def test_default_validate_save(self):
        d = make_job()
        seq = sq.load(d)
        self.assertEqual([(s["clip"], s["in"], s["out"]) for s in seq["segments"]], [("c01", 0, 6.0), ("c02", 0, 4.0)]); self.assertEqual(sq.duration(seq), 10.0)
        bad = {"segments": [{"clip": "zz", "in": 0, "out": 2}, {"clip": "c01", "in": 1, "out": 1.1}, {"clip": "c01", "in": "x", "out": 2}]}
        self.assertEqual(len(sq.validate(d, bad)[1]), 3)
        self.assertFalse(sq.save(d, {"segments": []})[0])
        ok, msg, clean = sq.save(d, {"segments": [{"id": "a", "clip": "c01", "in": -5, "out": 99}]})
        self.assertTrue(ok); self.assertEqual((clean["segments"][0]["in"], clean["segments"][0]["out"]), (0.0, 6.0))      # clamped to the clip

    def test_split_and_cut_range(self):
        d = make_job(); seq = sq.default(d)
        s2 = sq.split(seq, "s1", 2.0)
        self.assertEqual([(s["id"], s["in"], s["out"]) for s in s2["segments"][:2]], [("s1", 0.0, 2.0), ("s1b", 2.0, 6.0)])
        self.assertEqual(sq.split(seq, "s1", 0.1), seq)                                                       # too close to the edge: no change
        c = sq.cut_range(seq, "c01", 2.0, 4.0)
        self.assertEqual([(s["in"], s["out"]) for s in c["segments"] if s["clip"] == "c01"], [(0.0, 2.0), (4.0, 6.0)])
        self.assertEqual(len(sq.cut_range(seq, "c01", 0.0, 6.0)["segments"]), 1)                              # whole piece removed

    def test_check_my_cuts_marks_silences_and_pauses_with_reasons(self):
        d = make_job()
        m = sq.check_cuts(d)
        kinds = {(x["kind"], x["in"], x["out"]) for x in m}
        self.assertTrue(any(k == "silence" and a == 0.0 for k, a, b in kinds))                                # 1.5 s of silence before talking
        self.assertTrue(any(k == "pause" for k, a, b in kinds))                                               # 2.5 -> 4.5 is a 2 s pause
        self.assertTrue(all(x["why"] for x in m))
        d2 = sq.cut_range(sq.default(d), "c01", 0.0, 1.4)                                                     # after cutting the start, that marker is gone
        self.assertFalse(any(x["kind"] == "silence" and x["in"] < 1.0 for x in sq.check_cuts(d, d2)))

    def test_apply_builds_exact_footage_keeps_the_old_and_undo_restores(self):
        d = make_job()
        seq = {"segments": [{"id": "s1", "clip": "c02", "in": 0.0, "out": 4.0}, {"id": "s2", "clip": "c01", "in": 1.0, "out": 3.0}]}      # reordered + trimmed, one silent clip
        ok, msg = sq.apply(d, seq)
        self.assertTrue(ok, msg)
        r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_entries", "stream=codec_type,nb_read_frames,duration", "-of", "csv=p=0", os.path.join(d, "proxy.mp4")],
                           capture_output=True, text=True).stdout.split()
        v = [x for x in r if x.startswith("video")][0].split(","); a = [x for x in r if x.startswith("audio")][0].split(",")
        self.assertEqual(v[2], "180"); self.assertAlmostEqual(float(a[1]), 6.0, delta=0.06)                    # 4 s + 2 s at 30 fps, sound for all of it (silent part padded)
        self.assertFalse(os.path.exists(os.path.join(d, "transcript.json"))); self.assertFalse(os.path.exists(os.path.join(d, "review")))
        bk = os.path.join(d, "before_sequence", os.listdir(os.path.join(d, "before_sequence"))[0])
        self.assertEqual(open(os.path.join(bk, "proxy.mp4"), "rb").read(), b"OLD-JOINED-PROXY"); self.assertTrue(os.path.exists(os.path.join(bk, "review", "draft_540p.mp4")))
        idx = json.load(open(os.path.join(d, "media_index.json")))
        self.assertEqual([(c["clip_id"], c["start"], c["end"], c["source_in"]) for c in idx["clips"]], [("c02", 0.0, 4.0, 0.0), ("c01", 4.0, 6.0, 1.0)])
        self.assertEqual(idx["clips"][1]["speech_segments"], [[0.5, 1.5]])                                    # speech 1.5-2.5 in the clip, shifted by the trim (in=1.0)
        self.assertEqual(json.load(open(os.path.join(d, "job.json")))["status"], "ingested")
        self.assertTrue(os.path.getsize(os.path.join(d, "audio16k.wav")) > 1000)
        self.assertTrue(sq.state(d)["can_undo"])
        ok, msg = sq.undo(d)
        self.assertTrue(ok, msg)
        self.assertEqual(open(os.path.join(d, "proxy.mp4"), "rb").read(), b"OLD-JOINED-PROXY")
        self.assertTrue(os.path.exists(os.path.join(d, "transcript.json"))); self.assertTrue(os.path.exists(os.path.join(d, "review", "draft_540p.mp4")))
        self.assertTrue(os.path.isdir(os.path.join(d, "after_sequence_undone")))                              # nothing deleted: the timeline's own results are set aside
        self.assertFalse(sq.undo(d)[0])

    def test_apply_refuses_a_bad_sequence_and_changes_nothing(self):
        d = make_job()
        ok, msg = sq.apply(d, {"segments": [{"clip": "c01", "in": 0, "out": 0.1}]})
        self.assertFalse(ok); self.assertEqual(open(os.path.join(d, "proxy.mp4"), "rb").read(), b"OLD-JOINED-PROXY")

    def test_state_has_clips_waveforms_and_sequence(self):
        d = make_job(); s = sq.state(d)
        self.assertEqual([c["id"] for c in s["clips"]], ["c01", "c02"]); self.assertTrue(s["clips"][0]["waveform"]["peaks"]); self.assertEqual(s["duration"], 10.0)
        self.assertFalse(s["can_undo"])


if __name__ == "__main__":
    unittest.main()
