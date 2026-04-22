"""
``/api/diff`` must not hang on max-sized inputs.

The route caps each side at 256 KB (see ``_DIFF_MAX_BYTES`` in
``backend/blueprints/runs_bp.py``). Even at the cap, with no shared
lines (worst-case for difflib), the call must complete in well under
two seconds. This guards against an algorithmic DoS regression.
"""
from __future__ import annotations

import time

import pytest

pytestmark = [pytest.mark.security]


def _payload_at(target_bytes: int) -> str:
    """Build a unique-line text body whose UTF-8 byte length is just
    below ``target_bytes``. Each line is distinct so difflib has no
    shared anchors to exploit."""
    lines: list[str] = []
    total = 0
    i = 0
    # Each line is ~48 bytes: "PRE_LINE_<i>_xxxxxxxxxxxxxxxxxxxxxxxxxx\n".
    pad = "x" * 24
    while total < target_bytes:
        line = f"L{i:08d}_{pad}\n"
        lines.append(line)
        total += len(line)
        i += 1
        if total + 64 >= target_bytes:
            break
    return "".join(lines)[:target_bytes]


def test_diff_call_completes_under_2s_for_max_inputs(client) -> None:
    pre = _payload_at(256 * 1024)
    # Different prefix → no shared lines between pre and post.
    post = _payload_at(256 * 1024).replace("L", "R")
    assert len(pre) <= 256 * 1024
    assert len(post) <= 256 * 1024

    start = time.perf_counter()
    r = client.post("/api/diff", json={"pre": pre, "post": post})
    elapsed = time.perf_counter() - start

    # Either a clean 200 (diff produced) or a 4xx envelope (cap hit) is
    # acceptable — the assertion is that the route did not hang.
    assert r.status_code in (200, 400, 413), (
        f"unexpected status {r.status_code}: {r.get_data(as_text=True)[:200]}"
    )
    assert elapsed < 2.0, (
        f"/api/diff took {elapsed:.2f}s on max inputs; potential algorithmic DoS"
    )
