"""Place for the LTX video AI (config/project.json -> video_ai). Nothing here runs unless video_ai.enabled is true.
It only MAKES clips (B-roll from a picture, a short extension). It never decides cuts and never touches the speaker's face or voice.
generate() is a stub until the real LTX API call is filled in from the LTX docs (endpoint + request shape)."""
import json, os
from lib import config as cfg


class NotReady(Exception):
    pass


def conf():
    return cfg.PROJECT.get("video_ai", {})


def status():
    """Plain-words state: (ok, message). Free, offline."""
    c = conf()
    if not c.get("enabled"):
        return False, "Video AI is off (config/project.json -> video_ai.enabled)."
    if not c.get("endpoint"):
        return False, "Video AI endpoint is not filled in yet (video_ai.endpoint)."
    if not os.path.exists(os.path.expanduser(c.get("key_file", ""))):
        return False, f"Video AI key file is missing: {c.get('key_file')}"
    return True, "Video AI is ready."


def estimate(seconds):
    """Cost in USD of `seconds` of generated video, capped by max_seconds_per_reel."""
    c = conf()
    s = min(float(seconds), float(c.get("max_seconds_per_reel", 0)))
    return round(s * float(c.get("price_per_second_usd", 0)), 3)


def allowed(use):
    c = conf()
    return use in c.get("allowed_uses", []) and use not in c.get("never", [])


def generate(use, prompt, seconds, out_path, picture=None):
    """Make one clip. Refuses unless the use is allowed, the money fits and the setup is ready."""
    if not allowed(use):
        raise NotReady(f"'{use}' is not an allowed use of the video AI.")
    ok, msg = status()
    if not ok:
        raise NotReady(msg)
    raise NotReady("LTX call not written yet: fill in the endpoint and request shape from the LTX docs (T142).")
