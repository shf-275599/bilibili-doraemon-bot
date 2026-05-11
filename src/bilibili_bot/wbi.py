from __future__ import annotations

import hashlib
import time
from functools import reduce
from typing import Any

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52
]

MIN_KEY_LENGTH = 64


def get_mixin_key(orig: str) -> str:
    if len(orig) < MIN_KEY_LENGTH:
        raise ValueError(f"WBI key too short: {len(orig)} chars, need >= {MIN_KEY_LENGTH}")
    return reduce(lambda s, i: s + orig[i], MIXIN_KEY_ENC_TAB, "")[:32]


def enc_wbi(params: dict[str, Any], img_key: str, sub_key: str) -> dict[str, Any]:
    mixin_key = get_mixin_key(img_key + sub_key)
    curr_time = round(time.time())

    filtered = {
        k: "".join(c for c in str(v) if c not in "!'()*")
        for k, v in sorted(params.items())
    }
    filtered["wts"] = curr_time
    params_str = "&".join(f"{k}={v}" for k, v in filtered.items())
    wbi_sign = hashlib.md5((params_str + mixin_key).encode()).hexdigest()

    filtered["w_rid"] = wbi_sign
    return filtered
