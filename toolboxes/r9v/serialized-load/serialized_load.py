# SPDX-License-Identifier: Apache-2.0
"""Experimental startup-only lock; does not change weights or inference."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import time


def _memory():
    result = {}
    for filename, wanted in (("/proc/self/status", {"VmRSS", "RssAnon", "VmSwap"}),
                             ("/proc/meminfo", {"MemAvailable", "SwapFree"})):
        try:
            for line in Path(filename).read_text().splitlines():
                key, _, value = line.partition(":")
                if key in wanted:
                    result[key + "_bytes"] = int(value.split()[0]) * 1024
        except (OSError, ValueError):
            pass
    return result


@contextmanager
def serialized_expert_load(*, target_with_manifest, rank, logger):
    """Serialize target weight loading plus compaction between local TP workers.

    The file must remain at one shared path/inode for the entire startup; never
    unlink it. flock releases automatically on process death. The separate PLE
    stream and draft loading do not enter this critical section.
    """
    flag = os.environ.get("R9V_SERIALIZE_EXPERT_LOAD", "0")
    if not target_with_manifest or flag == "0":
        yield
        return
    if flag != "1":
        raise ValueError("R9V_SERIALIZE_EXPERT_LOAD must be 0 or 1")
    path = os.environ.get("R9V_EXPERT_LOAD_LOCK_PATH", "/cache/r9v-expert-load.lock")
    if not os.path.isabs(path):
        raise ValueError("R9V_EXPERT_LOAD_LOCK_PATH must be absolute")
    started = time.monotonic()
    def log(event, **extra):
        logger.warning("R9V_SERIALIZED_EXPERT_LOAD %s", json.dumps({
            "event": event, "rank": rank, "pid": os.getpid(), "path": path,
            "elapsed_seconds": time.monotonic() - started, **_memory(), **extra,
        }, sort_keys=True))
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    acquired = False
    try:
        log("wait")
        fcntl.flock(fd, fcntl.LOCK_EX)
        acquired = True
        held_since = time.monotonic()
        log("acquired", wait_seconds=held_since - started)
        try:
            yield
        except BaseException as error:
            log("failed", exception_type=type(error).__name__, message=str(error))
            raise
    finally:
        # Release before logging, including exception paths. close is a second
        # release guarantee and also handles an interrupted flock acquisition.
        try:
            if acquired:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
        if acquired:
            log("released", held_seconds=time.monotonic() - held_since)
