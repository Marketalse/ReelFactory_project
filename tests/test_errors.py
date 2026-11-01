"""Provider errors are explained in plain words; temporary ones are retried once; no key is ever printed."""
import io, json, os, sys, unittest, urllib.error
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import reel  # noqa: E402


def http_error(code, body=b'{"message":"x"}', headers=None):
    return urllib.error.HTTPError("https://x/v1", code, "err", headers or {}, io.BytesIO(body))


class Ok:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return json.dumps({"ok": 1}).encode()


class ErrorTests(unittest.TestCase):
    def setUp(self):
        self.waits = []
        self.sleep = self.waits.append

    def test_401_says_key_or_credit_and_where_the_key_comes_from(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_error(401, b'{"status":401,"message":"invalid"}')):
            with self.assertRaises(reel.Stop) as c:
                reel.post_with_retry(None, "fix", sleep=self.sleep)
        msg = str(c.exception)
        self.assertIn("refused the API key", msg); self.assertIn("portal.nousresearch.com", msg); self.assertIn("HTTP 401", msg)
        self.assertEqual(self.waits, [])                       # never retried

    def test_busy_service_is_retried_once_then_succeeds(self):
        with mock.patch("urllib.request.urlopen", side_effect=[http_error(429, headers={"Retry-After": "7"}), Ok()]):
            self.assertEqual(reel.post_with_retry(None, "plan", sleep=self.sleep), {"ok": 1})
        self.assertEqual(self.waits, [7])

    def test_busy_twice_stops_with_wait_advice(self):
        with mock.patch("urllib.request.urlopen", side_effect=[http_error(503), http_error(503)]):
            with self.assertRaises(reel.Stop) as c:
                reel.post_with_retry(None, "plan", sleep=self.sleep)
        self.assertIn("busy", str(c.exception)); self.assertEqual(self.waits, [20])

    def test_no_internet_is_retried_then_explained(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("no route")):
            with self.assertRaises(reel.Stop) as c:
                reel.post_with_retry(None, "fix", sleep=self.sleep)
        self.assertIn("internet", str(c.exception))

    def test_402_and_404(self):
        self.assertIn("out of credit", reel.explain_http("fix", 402, b""))
        self.assertIn("model name", reel.explain_http("fix", 404, b""))

    def test_mac_notification_skipped_while_a_tab_watches(self):
        with mock.patch.object(reel, "dashboard_watching", return_value=True), mock.patch("subprocess.run") as run:
            reel.notify("Draft ready", "/x/jobs/2026-11-01-aa")
        run.assert_not_called()
        with mock.patch.object(reel, "dashboard_watching", return_value=False), mock.patch("subprocess.run") as run:
            reel.notify("Draft ready", "/x/jobs/2026-11-01-aa")
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
