from openevmbench.jcs import canonicalize


def test_key_ordering():
    assert canonicalize({"b": 2, "a": 1}) == b'{"a":1,"b":2}'


def test_nested_and_arrays():
    obj = {"z": [1, 2, {"y": "x"}], "a": {"c": True, "b": None}}
    assert canonicalize(obj) == b'{"a":{"b":null,"c":true},"z":[1,2,{"y":"x"}]}'


def test_no_whitespace():
    out = canonicalize({"a": [1, 2, 3], "b": {"c": "d"}})
    assert b" " not in out


def test_ecmascript_number_formatting():
    # 1e16 must serialize the ECMAScript way (not Python's repr "1e+16").
    assert canonicalize(1e16) == b"10000000000000000"
    assert canonicalize(0.456) == b"0.456"
    assert canonicalize(1) == b"1"


def test_unicode_stability():
    # Same content canonicalizes identically regardless of dict insertion order.
    a = canonicalize({"name": "ülrich", "x": 1})
    b = canonicalize({"x": 1, "name": "ülrich"})
    assert a == b
