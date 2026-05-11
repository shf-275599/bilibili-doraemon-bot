import pytest
from bilibili_bot.wbi import get_mixin_key, enc_wbi, MIN_KEY_LENGTH


def test_get_mixin_key():
    orig = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ01234567"
    key = get_mixin_key(orig)
    assert len(key) == 32
    assert isinstance(key, str)


def test_get_mixin_key_too_short():
    with pytest.raises(ValueError, match="too short"):
        get_mixin_key("short")


def test_enc_wbi():
    params = {"a": 1, "b": 2}
    img_key = "a" * MIN_KEY_LENGTH
    sub_key = "b" * MIN_KEY_LENGTH
    result = enc_wbi(params, img_key, sub_key)

    assert "wts" in result
    assert "w_rid" in result
    assert result["a"] == "1"
    assert result["b"] == "2"


def test_enc_wbi_filters_special_chars():
    params = {"key": "val!ue'wit(h)spec*ial"}
    img_key = "a" * MIN_KEY_LENGTH
    sub_key = "b" * MIN_KEY_LENGTH
    result = enc_wbi(params, img_key, sub_key)

    assert result["key"] == "valuewithspecial"


def test_enc_wbi_sorts_params():
    params = {"z": 1, "a": 2}
    img_key = "a" * MIN_KEY_LENGTH
    sub_key = "b" * MIN_KEY_LENGTH
    result = enc_wbi(params, img_key, sub_key)
    keys = [k for k in result if k not in ("wts", "w_rid")]
    assert keys == sorted(keys)
