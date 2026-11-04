import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))
from tools import convert_units, voltage_divider  # noqa: E402


def test_divider_equal_resistors_halves():
    assert voltage_divider(5, 10_000, 10_000) == pytest.approx(2.5)


def test_divider_esp32_example():
    assert voltage_divider(3.3, 10_000, 4_700) == pytest.approx(1.0551, abs=1e-4)


def test_divider_rejects_bad_resistors():
    with pytest.raises(ValueError):
        voltage_divider(5, 0, 0)
    with pytest.raises(ValueError):
        voltage_divider(5, -1, 100)


@pytest.mark.parametrize("value, src, dst, expected", [
    (4.7, "kohm", "ohm", 4700),
    (4.7, "kΩ", "ohm", 4700),
    (250, "mA", "A", 0.25),
    (3300, "mV", "V", 3.3),
    (0.1, "uF", "nF", 100),
    (16, "MHz", "kHz", 16_000),
    (10, "ms", "us", 10_000),
])
def test_convert_known_values(value, src, dst, expected):
    assert convert_units(value, src, dst) == pytest.approx(expected)


def test_convert_refuses_different_units():
    with pytest.raises(ValueError):
        convert_units(1, "mA", "V")


def test_convert_refuses_unknown_unit():
    with pytest.raises(ValueError):
        convert_units(1, "furlong", "m")