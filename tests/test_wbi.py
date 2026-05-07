import pytest
from bilibili_bot.wbi import get_mixin_key, enc_wbi


def test_get_mixin_key():
    orig = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ01234567"
    key = get_mixin_key(orig)
    assert len(key) == 32
    assert isinstance(key, str)


def test_enc_wbi():
    params = {"a": 1, "b": 2}
    img_key = "abcdefghijklmnopqrstuvwxyz0123456789ABC"
    sub_key = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abc"
    result = enc_wbi(params, img_key, sub_key)

    assert "wts" in result
    assert "w_rid" in result
    assert result["a"] == 1
    assert result["b"] == 2
