import os, sys, tempfile, types, unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import reel  # noqa: E402


def resp(text, finish="stop"):
    return {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "completion_tokens_details": {"reasoning_tokens": 5}, "cost": 0.0},
            "choices": [{"finish_reason": finish, "message": {"content": text}}]}


class EmptyAnswerTests(unittest.TestCase):
    def ctx(self):
        a = types.SimpleNamespace(budget=5.0, img_tok=800)
        return reel.Ctx(tempfile.mkdtemp(), a)

    def run_llm(self, answers):
        c = self.ctx()
        with mock.patch.object(reel, "nous", return_value=("http://x", "k")), \
             mock.patch.object(reel, "post_with_retry", side_effect=answers) as p, \
             mock.patch.object(reel.cfg, "month_spent", return_value=0.0), mock.patch.object(reel.cfg, "price", return_value=(1.0, 1.0)):
            try:
                return c.llm("selects", "a/b", [{"type": "text", "text": "hi"}], 1000), p.call_count
            except reel.Stop as e:
                return str(e), p.call_count

    def test_empty_answer_is_retried_once_with_more_room(self):
        out, calls = self.run_llm([resp(""), resp('{"ok": 1}')])
        self.assertEqual((out, calls), ('{"ok": 1}', 2))

    def test_empty_twice_is_a_clear_stop_not_a_crash(self):
        out, calls = self.run_llm([resp(None), resp("  ")])
        self.assertEqual(calls, 2); self.assertIn("empty answer twice", out)

    def test_unreadable_answer_is_a_stop(self):
        with self.assertRaises(reel.Stop):
            reel.parse_json("sorry, I cannot")
        with self.assertRaises(reel.Stop):
            reel.parse_json("")
        self.assertEqual(reel.parse_json('```json\n{"a": 1}\n```'), {"a": 1})


if __name__ == "__main__":
    unittest.main()
