"""
Vendor asset integrity pin.

``backend/static/vendor/jszip.min.js`` is a third-party script
shipped with the SPA. A pinned SHA-384 hash detects accidental
upgrades, supply-chain swaps, or partial downloads. To rotate the
asset deliberately, recompute the hash::

    python -c "import hashlib; \\
print(hashlib.sha384(open('backend/static/vendor/jszip.min.js','rb').read()).hexdigest())"

…and update ``EXPECTED_SHA384`` below in the same commit that
upgrades the vendor file.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

pytestmark = [pytest.mark.security]

_VENDOR = (
    Path(__file__).resolve().parent.parent
    / "backend"
    / "static"
    / "vendor"
    / "jszip.min.js"
)

EXPECTED_SHA384 = (
    "fa66d5d88635664fd7d69fe75a5946c9225250df2e32cfa0500375d0eafde540"
    "47d1fa63e867ca80f9a00b911789e5c6"
)


def test_jszip_min_js_matches_pinned_sha384() -> None:
    assert _VENDOR.is_file(), f"missing vendor asset: {_VENDOR}"
    actual = hashlib.sha384(_VENDOR.read_bytes()).hexdigest()
    assert actual == EXPECTED_SHA384, (
        "jszip.min.js sha384 mismatch — vendor asset was modified.\n"
        f"  expected: {EXPECTED_SHA384}\n"
        f"  actual:   {actual}\n"
        "If this change is intentional, update EXPECTED_SHA384 in this test."
    )
