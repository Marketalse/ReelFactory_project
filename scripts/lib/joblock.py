"""One run per reel (pre-UAT audit BUG-005). A reel folder gets an operating-system lock for as long as a run is alive; the system drops it by itself
when the process ends, even after kill -9, so a crashed run never blocks a restart. A second run on the same reel is refused with a plain message
instead of both writing the same files (which corrupted the video and lost cost records)."""
import os

try:
    import fcntl
except ImportError:                       # not on Unix: no lock (the dashboard still allows one reel at a time)
    fcntl = None


class Busy(Exception):
    pass


def acquire(job):
    """Hold the lock for the life of this process. Returns the open file (keep a reference). Raises Busy when another run holds it."""
    if fcntl is None:
        return None
    f = open(os.path.join(job, ".run.lock"), "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.seek(0); who = f.read().strip(); f.close()
        raise Busy(f"this reel is already being made by another run{' (process ' + who + ')' if who else ''}: wait for it to finish; nothing was changed")
    f.seek(0); f.truncate(); f.write(str(os.getpid())); f.flush()
    return f


def held(job):
    """True when some run holds this reel right now (reads only; used by status pages)."""
    if fcntl is None or not os.path.exists(os.path.join(job, ".run.lock")):
        return False
    f = open(os.path.join(job, ".run.lock"), "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(f, fcntl.LOCK_UN)
        return False
    except OSError:
        return True
    finally:
        f.close()
