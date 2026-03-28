"""
Unit tests for fuse pragma generation in codegen.fuses.

Tests cover default configuration, custom values for each field,
and verification that all fuse fields appear in the output.
"""

import pytest
from codegen.fuses import FuseConfig, generate_fuse_pragmas


class TestDefaultFuseConfig:
    """Tests for the default FuseConfig values."""

    def test_default_produces_pragma_lines(self):
        """Default FuseConfig should produce a non-empty string of pragmas."""
        fuse = FuseConfig()
        output = generate_fuse_pragmas(fuse)
        assert output
        assert "#pragma config" in output

    def test_default_ics_pair_1(self):
        """Default ICS pair should be PGC1/PGD1."""
        fuse = FuseConfig()
        output = generate_fuse_pragmas(fuse)
        assert "#pragma config ICS = ICS1" in output
        assert "PGC1/PGD1" in output

    def test_default_jtag_off(self):
        """Default JTAG should be OFF."""
        fuse = FuseConfig()
        output = generate_fuse_pragmas(fuse)
        assert "#pragma config JTAGEN = OFF" in output
        assert "disabled" in output

    def test_default_watchdog_off(self):
        """Default watchdog should be OFF."""
        fuse = FuseConfig()
        output = generate_fuse_pragmas(fuse)
        assert "#pragma config FWDTEN = OFF" in output
        assert "Watchdog timer disabled" in output

    def test_default_wdtps(self):
        """Default watchdog prescaler should be PS1024."""
        fuse = FuseConfig()
        output = generate_fuse_pragmas(fuse)
        assert "#pragma config WDTPS = PS1024" in output

    def test_default_bor_on(self):
        """Default brown-out reset should be ON."""
        fuse = FuseConfig()
        output = generate_fuse_pragmas(fuse)
        assert "#pragma config BOREN = ON" in output
        assert "Brown-out reset enabled" in output

    def test_default_borv_high(self):
        """Default brown-out voltage should be BOR_HIGH."""
        fuse = FuseConfig()
        output = generate_fuse_pragmas(fuse)
        assert "#pragma config BORV = BOR_HIGH" in output
        assert "high threshold" in output


class TestCustomFuseConfig:
    """Tests for custom fuse configuration values."""

    def test_ics_pair_2(self):
        """Setting ICS pair to 2 should generate ICS2 pragma."""
        fuse = FuseConfig(ics=2)
        output = generate_fuse_pragmas(fuse)
        assert "#pragma config ICS = ICS2" in output
        assert "PGC2/PGD2" in output

    def test_ics_pair_3(self):
        """Setting ICS pair to 3 should generate ICS3 pragma."""
        fuse = FuseConfig(ics=3)
        output = generate_fuse_pragmas(fuse)
        assert "#pragma config ICS = ICS3" in output
        assert "PGC3/PGD3" in output

    def test_jtag_on(self):
        """Enabling JTAG should generate JTAGEN = ON pragma."""
        fuse = FuseConfig(jtagen="ON")
        output = generate_fuse_pragmas(fuse)
        assert "#pragma config JTAGEN = ON" in output
        assert "enabled" in output

    def test_wdt_swon(self):
        """Watchdog SWON should generate software-controlled watchdog pragma."""
        fuse = FuseConfig(fwdten="SWON")
        output = generate_fuse_pragmas(fuse)
        assert "#pragma config FWDTEN = SWON" in output
        assert "controlled by software" in output

    def test_wdt_on(self):
        """Watchdog ON should generate always-enabled pragma."""
        fuse = FuseConfig(fwdten="ON")
        output = generate_fuse_pragmas(fuse)
        assert "#pragma config FWDTEN = ON" in output
        assert "always enabled" in output

    def test_custom_wdtps(self):
        """Custom watchdog prescaler should appear in output."""
        fuse = FuseConfig(wdtps="PS32768")
        output = generate_fuse_pragmas(fuse)
        assert "#pragma config WDTPS = PS32768" in output

    def test_bor_off(self):
        """Disabling brown-out reset should generate BOREN = OFF pragma."""
        fuse = FuseConfig(boren="OFF")
        output = generate_fuse_pragmas(fuse)
        assert "#pragma config BOREN = OFF" in output
        assert "Brown-out reset disabled" in output

    def test_borv_low(self):
        """Setting brown-out voltage to BOR_LOW should appear in output."""
        fuse = FuseConfig(borv="BOR_LOW")
        output = generate_fuse_pragmas(fuse)
        assert "#pragma config BORV = BOR_LOW" in output
        assert "low threshold" in output

    def test_borv_mid(self):
        """Setting brown-out voltage to BOR_MID should appear in output."""
        fuse = FuseConfig(borv="BOR_MID")
        output = generate_fuse_pragmas(fuse)
        assert "#pragma config BORV = BOR_MID" in output
        assert "mid threshold" in output


class TestFuseOutputCompleteness:
    """Tests that all fuse sections appear in the output."""

    def test_all_sections_present(self):
        """Output should contain FICD, FWDT, and FBORPOR section comments."""
        fuse = FuseConfig()
        output = generate_fuse_pragmas(fuse)
        assert "FICD" in output
        assert "FWDT" in output
        assert "FBORPOR" in output

    def test_all_pragma_fields_present(self):
        """Output should contain pragma lines for all six fuse fields."""
        fuse = FuseConfig()
        output = generate_fuse_pragmas(fuse)
        expected_fields = ["ICS", "JTAGEN", "FWDTEN", "WDTPS", "BOREN", "BORV"]
        for field_name in expected_fields:
            assert f"#pragma config {field_name}" in output, (
                f"Missing pragma for {field_name}"
            )

    def test_fully_custom_config(self):
        """A fully customized FuseConfig should reflect all custom values."""
        fuse = FuseConfig(
            ics=2,
            jtagen="ON",
            fwdten="SWON",
            wdtps="PS256",
            boren="OFF",
            borv="BOR_MID",
        )
        output = generate_fuse_pragmas(fuse)
        assert "ICS2" in output
        assert "JTAGEN = ON" in output
        assert "FWDTEN = SWON" in output
        assert "WDTPS = PS256" in output
        assert "BOREN = OFF" in output
        assert "BORV = BOR_MID" in output
