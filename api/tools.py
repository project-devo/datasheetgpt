"""Calculator tools the LLM can call: a voltage divider and a unit converter."""

PREFIXES = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6,
            "m": 1e-3, "": 1.0, "k": 1e3, "M": 1e6, "G": 1e9}
BASE_UNITS = ["ohm", "Hz", "V", "A", "W", "F", "s"]  # longest first, so "Hz" wins over "s"


def voltage_divider(vin: float, r1: float, r2: float) -> float:
    """Output voltage of a resistor divider: vin through r1 (top) then r2 (bottom) to ground.

    Args:
        vin: input voltage in volts
        r1: top resistor in ohms (between vin and the output)
        r2: bottom resistor in ohms (between the output and ground)
    """
    if r1 < 0 or r2 < 0 or r1 + r2 == 0:
        raise ValueError("resistors must be >= 0 and not both zero")
    return vin * r2 / (r1 + r2)


def split_unit(unit):
    """'kohm' -> (1000.0, 'ohm'), 'mA' -> (0.001, 'A')."""
    unit = unit.strip().replace("Ω", "ohm").replace("ohms", "ohm")
    for base in BASE_UNITS:
        if unit.endswith(base) and unit[: -len(base)] in PREFIXES:
            return PREFIXES[unit[: -len(base)]], base
    raise ValueError(f"unknown unit '{unit}'")


def convert_units(value: float, from_unit: str, to_unit: str) -> float:
    """Convert between metric prefixes of the same unit, like mA to A or kohm to ohm.

    Args:
        value: the number to convert
        from_unit: unit of value, e.g. "mA", "kohm", "MHz", "uF", "mV"
        to_unit: unit to convert to, e.g. "A", "ohm", "Hz", "nF", "V"
    """
    f1, base1 = split_unit(from_unit)
    f2, base2 = split_unit(to_unit)
    if base1 != base2:
        raise ValueError(f"can't convert {base1} to {base2}")
    return float(f"{value * f1 / f2:.12g}")  # 12 significant digits hides float noise


if __name__ == "__main__":
    print(voltage_divider(3.3, 10_000, 4_700))
    print(convert_units(4.7, "kohm", "ohm"))
    print(convert_units(250, "mA", "A"))