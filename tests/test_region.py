import pytest

from nlmclean.core.region import Region


def test_parse():
    assert Region.parse("10,20,30,40") == Region(10, 20, 30, 40)


@pytest.mark.parametrize("bad", ["10,20,30", "a,b,c,d", "10,20,0,40", "10,20,-5,40"])
def test_parse_rejects(bad):
    with pytest.raises(ValueError):
        Region.parse(bad)


def test_clamped_keeps_margin():
    r = Region(0, 0, 2000, 2000).clamped(1470, 956, margin=1)
    assert r.x == 1 and r.y == 1
    assert r.x + r.w < 1470 and r.y + r.h < 956


def test_padded_then_clamped():
    r = Region(1400, 900, 60, 50).padded(20).clamped(1470, 956)
    assert r.x + r.w <= 1470 and r.y + r.h <= 956
    assert r.x < 1400 and r.y < 900  # padding extended the rect


def test_scaled():
    assert Region(100, 100, 50, 50).scaled(2.0) == Region(200, 200, 100, 100)
