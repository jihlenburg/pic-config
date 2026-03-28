"""
Unit tests for the PLL calculation engine in codegen.oscillator.

Tests cover exact-match scenarios, various crystal/target combinations,
VCO and FPFD constraint validation, and unreachable target edge cases.
"""

import pytest
from codegen.oscillator import (
    calculate_pll,
    PLLResult,
    VCO_MIN_HZ,
    VCO_MAX_HZ,
    FPFD_MIN_HZ,
    PLL_M_MIN,
    PLL_M_MAX,
    PLL_N1_MIN,
    PLL_N1_MAX,
    PLL_N2_MIN,
    PLL_N2_MAX,
    PLL_N3_MIN,
    PLL_N3_MAX,
)


class TestCalculatePllExactMatch:
    """Tests for exact PLL frequency matches."""

    def test_8mhz_to_200mhz(self):
        """8 MHz FRC input should reach exactly 200 MHz Fosc with zero error."""
        result = calculate_pll(8_000_000, 200_000_000)
        assert result is not None
        assert result.fosc == 200_000_000
        assert result.fcy == 100_000_000
        assert result.error_ppm == 0

    def test_8mhz_to_100mhz(self):
        """8 MHz input should reach exactly 100 MHz Fosc."""
        result = calculate_pll(8_000_000, 100_000_000)
        assert result is not None
        assert result.fosc == 100_000_000
        assert result.error_ppm == 0

    def test_8mhz_to_140mhz(self):
        """8 MHz input should reach exactly 140 MHz Fosc."""
        result = calculate_pll(8_000_000, 140_000_000)
        assert result is not None
        assert result.fosc == 140_000_000
        assert result.error_ppm == 0


class TestCalculatePllVariousCrystals:
    """Tests for various crystal frequencies targeting common Fosc values."""

    @pytest.mark.parametrize("crystal_hz,target_hz", [
        (10_000_000, 100_000_000),
        (10_000_000, 140_000_000),
        (10_000_000, 200_000_000),
        (12_000_000, 100_000_000),
        (12_000_000, 200_000_000),
        (16_000_000, 100_000_000),
        (16_000_000, 200_000_000),
    ])
    def test_crystal_to_target(self, crystal_hz, target_hz):
        """Various crystal inputs should find valid PLL configurations for common targets."""
        result = calculate_pll(crystal_hz, target_hz)
        assert result is not None, (
            f"No PLL solution for {crystal_hz/1e6:.0f} MHz -> {target_hz/1e6:.0f} MHz"
        )
        # Allow small frequency error (under 1000 ppm = 0.1%)
        assert result.error_ppm < 1000, (
            f"Error too large: {result.error_ppm} ppm for "
            f"{crystal_hz/1e6:.0f} MHz -> {target_hz/1e6:.0f} MHz"
        )

    @pytest.mark.parametrize("crystal_hz", [8_000_000, 10_000_000, 12_000_000, 16_000_000])
    def test_crystal_to_200mhz(self, crystal_hz):
        """All standard crystal values should reach 200 MHz Fosc."""
        result = calculate_pll(crystal_hz, 200_000_000)
        assert result is not None
        assert result.fosc == 200_000_000


class TestPllConstraints:
    """Tests that all PLL results satisfy hardware constraints."""

    @pytest.mark.parametrize("crystal_hz,target_hz", [
        (8_000_000, 100_000_000),
        (8_000_000, 200_000_000),
        (10_000_000, 140_000_000),
        (12_000_000, 200_000_000),
        (16_000_000, 100_000_000),
    ])
    def test_vco_within_range(self, crystal_hz, target_hz):
        """VCO frequency must be within the allowed range (400 MHz to 1600 MHz)."""
        result = calculate_pll(crystal_hz, target_hz)
        assert result is not None
        assert result.fvco >= VCO_MIN_HZ, (
            f"VCO {result.fvco/1e6:.1f} MHz below minimum {VCO_MIN_HZ/1e6:.0f} MHz"
        )
        assert result.fvco <= VCO_MAX_HZ, (
            f"VCO {result.fvco/1e6:.1f} MHz above maximum {VCO_MAX_HZ/1e6:.0f} MHz"
        )

    @pytest.mark.parametrize("crystal_hz,target_hz", [
        (8_000_000, 100_000_000),
        (8_000_000, 200_000_000),
        (10_000_000, 140_000_000),
        (12_000_000, 200_000_000),
        (16_000_000, 100_000_000),
    ])
    def test_fpfd_above_minimum(self, crystal_hz, target_hz):
        """PLL phase-frequency detector input (FPFD = FPLLI / N1) must be >= 8 MHz."""
        result = calculate_pll(crystal_hz, target_hz)
        assert result is not None
        fpfd = result.fplli / result.n1
        assert fpfd >= FPFD_MIN_HZ, (
            f"FPFD {fpfd/1e6:.1f} MHz below minimum {FPFD_MIN_HZ/1e6:.0f} MHz"
        )

    @pytest.mark.parametrize("crystal_hz,target_hz", [
        (8_000_000, 100_000_000),
        (8_000_000, 200_000_000),
        (16_000_000, 200_000_000),
    ])
    def test_divider_values_in_range(self, crystal_hz, target_hz):
        """All PLL divider values must be within their hardware-defined ranges."""
        result = calculate_pll(crystal_hz, target_hz)
        assert result is not None
        assert PLL_N1_MIN <= result.n1 <= PLL_N1_MAX, f"N1={result.n1} out of range"
        assert PLL_M_MIN <= result.m <= PLL_M_MAX, f"M={result.m} out of range"
        assert PLL_N2_MIN <= result.n2 <= PLL_N2_MAX, f"N2={result.n2} out of range"
        assert PLL_N3_MIN <= result.n3 <= PLL_N3_MAX, f"N3={result.n3} out of range"

    @pytest.mark.parametrize("crystal_hz,target_hz", [
        (8_000_000, 200_000_000),
        (10_000_000, 100_000_000),
    ])
    def test_fosc_formula_consistent(self, crystal_hz, target_hz):
        """Verify Fosc = FPLLI * M / (N1 * N2 * N3) matches the reported fosc."""
        result = calculate_pll(crystal_hz, target_hz)
        assert result is not None
        computed_fosc = int(result.fplli * result.m / (result.n1 * result.n2 * result.n3))
        assert computed_fosc == result.fosc, (
            f"Formula gives {computed_fosc}, result reports {result.fosc}"
        )


class TestPllEdgeCases:
    """Tests for edge cases and unreachable targets."""

    def test_unreachable_target_returns_none(self):
        """A target frequency that cannot be reached should return None.

        5 GHz is well beyond the dsPIC33CK PLL output range (~1600 MHz max VCO,
        with minimum postscalers of 1*1 giving max Fosc = 1600 MHz).
        """
        result = calculate_pll(8_000_000, 5_000_000_000)
        assert result is None

    def test_very_low_unreachable_target(self):
        """A very low target (1 MHz) may not be reachable because the VCO minimum
        constrains the minimum Fosc to VCO_MIN / (N2_MAX * N3_MAX)."""
        # VCO_MIN = 400 MHz, max postscaler product = 7*7 = 49
        # min achievable fosc ~ 400/49 ~ 8.16 MHz
        result = calculate_pll(8_000_000, 1_000_000)
        assert result is None

    def test_result_dataclass_fields(self):
        """PLLResult should contain all expected fields with correct types."""
        result = calculate_pll(8_000_000, 200_000_000)
        assert result is not None
        assert isinstance(result.n1, int)
        assert isinstance(result.m, int)
        assert isinstance(result.n2, int)
        assert isinstance(result.n3, int)
        assert isinstance(result.fplli, int)
        assert isinstance(result.fvco, int)
        assert isinstance(result.fosc, int)
        assert isinstance(result.fcy, int)
        assert isinstance(result.error_ppm, int)
