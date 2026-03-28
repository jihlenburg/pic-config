"""
Unit tests for C code generation in codegen.generate.

Tests build minimal DeviceData fixtures programmatically and verify
the generated code structure, ICSP pin handling, call ordering,
multi-file output format, signal name defines, and fuse pragma inclusion.
"""

import re
import pytest
from parser.edc_parser import (
    DeviceData,
    Pad,
    Pinout,
    PPSInputMapping,
    PPSOutputMapping,
    RemappablePeripheral,
)
from codegen.generate import (
    PinAssignment,
    PinConfig,
    generate_c_files,
    generate_c_code,
)
from codegen.oscillator import OscConfig
from codegen.fuses import FuseConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_minimal_device() -> DeviceData:
    """Build a minimal DeviceData with enough structure for codegen to work.

    Simulates a tiny device with:
      - 6 pads: RB0 (RP32), RB1 (RP33), RB2, RB3 (ICSP PGD1), RB4 (ICSP PGC1), VDD
      - A single pinout mapping positions 1-6
      - PPS input mapping for U1RXR on RPINR18
      - PPS output mapping for RP32 on RPOR0
      - TRISB and ANSELB port registers
      - ANSELB bits for 0, 1, 2
    """
    pads = {
        "RB0": Pad(name="RB0", functions=["RB0", "RP32", "AN0"],
                    rp_number=32, port="B", port_bit=0, analog_channels=["AN0"]),
        "RB1": Pad(name="RB1", functions=["RB1", "RP33"],
                    rp_number=33, port="B", port_bit=1),
        "RB2": Pad(name="RB2", functions=["RB2"],
                    rp_number=None, port="B", port_bit=2),
        "RB3": Pad(name="RB3", functions=["RB3", "PGD1"],
                    rp_number=None, port="B", port_bit=3),
        "RB4": Pad(name="RB4", functions=["RB4", "PGC1"],
                    rp_number=None, port="B", port_bit=4),
        "VDD": Pad(name="VDD", functions=["VDD"], is_power=True),
    }

    pinout = Pinout(
        package="TEST-6",
        pin_count=6,
        source="test",
        pins={1: "RB0", 2: "RB1", 3: "RB2", 4: "RB3", 5: "RB4", 6: "VDD"},
    )

    pps_input_mappings = [
        PPSInputMapping(
            peripheral="U1RXR",
            register="RPINR18",
            register_addr=0x0740,
            field_name="U1RXR",
            field_mask=0x3F,
            field_offset=0,
        ),
    ]

    pps_output_mappings = [
        PPSOutputMapping(
            rp_number=32,
            register="RPOR0",
            register_addr=0x0780,
            field_name="RP32R",
            field_mask=0x3F,
            field_offset=0,
        ),
    ]

    return DeviceData(
        part_number="dsPIC33CK256MP508",
        pads=pads,
        pinouts={"TEST-6": pinout},
        default_pinout="TEST-6",
        remappable_inputs=[
            RemappablePeripheral(name="U1RX", direction="in", ppsval=None),
        ],
        remappable_outputs=[
            RemappablePeripheral(name="U1TX", direction="out", ppsval=1),
        ],
        pps_input_mappings=pps_input_mappings,
        pps_output_mappings=pps_output_mappings,
        port_registers={"TRISB": 0x0200, "ANSELB": 0x0210},
        ansel_bits={"B": [0, 1, 2]},
    )


def _make_pin_config_with_icsp() -> PinConfig:
    """Build a PinConfig that includes ICSP pins (PGD1, PGC1) and regular pins."""
    return PinConfig(
        part_number="dsPIC33CK256MP508",
        assignments=[
            PinAssignment(pin_position=1, rp_number=32, peripheral="U1TX",
                          direction="out", ppsval=1),
            PinAssignment(pin_position=2, rp_number=33, peripheral="U1RX",
                          direction="in"),
            PinAssignment(pin_position=3, peripheral="GPIO", direction="out",
                          fixed=True),
            PinAssignment(pin_position=4, peripheral="PGD1", direction="in",
                          fixed=True),
            PinAssignment(pin_position=5, peripheral="PGC1", direction="in",
                          fixed=True),
        ],
    )


def _make_pin_config_basic() -> PinConfig:
    """Build a simple PinConfig without ICSP pins."""
    return PinConfig(
        part_number="dsPIC33CK256MP508",
        assignments=[
            PinAssignment(pin_position=1, rp_number=32, peripheral="U1TX",
                          direction="out", ppsval=1),
            PinAssignment(pin_position=2, rp_number=33, peripheral="U1RX",
                          direction="in"),
            PinAssignment(pin_position=3, peripheral="GPIO", direction="out",
                          fixed=True),
        ],
    )


# ---------------------------------------------------------------------------
# ICSP Pin Tests
# ---------------------------------------------------------------------------

class TestICSPPins:
    """Tests that ICSP/debug pins are handled correctly."""

    def test_icsp_pins_produce_reservation_comments(self):
        """ICSP pins (PGD1, PGC1) should produce reservation comments,
        not ANSEL or TRIS register writes."""
        device = _make_minimal_device()
        config = _make_pin_config_with_icsp()
        files = generate_c_files(device, config)
        c_code = files["pin_config.c"]

        # Should have reservation comments
        assert "reserved for PGD1" in c_code
        assert "reserved for PGC1" in c_code

    def test_icsp_pins_no_ansel_writes(self):
        """ICSP pins should NOT get ANSEL register writes."""
        device = _make_minimal_device()
        config = _make_pin_config_with_icsp()
        files = generate_c_files(device, config)
        c_code = files["pin_config.c"]

        # RB3 and RB4 are ICSP pins — should not appear in ANSEL writes
        assert "ANSELB3" not in c_code
        assert "ANSELB4" not in c_code

    def test_icsp_pins_no_tris_writes(self):
        """ICSP pins should NOT get TRIS register writes."""
        device = _make_minimal_device()
        config = _make_pin_config_with_icsp()
        files = generate_c_files(device, config)
        c_code = files["pin_config.c"]

        # RB3 and RB4 are ICSP pins — should not appear in TRIS writes
        assert "TRISB3" not in c_code or "reserved" in c_code.split("TRISB3")[0].split("\n")[-1]
        # More precise: no "TRISBbits.TRISB3 =" line
        assert "TRISBbits.TRISB3" not in c_code
        assert "TRISBbits.TRISB4" not in c_code

    def test_icsp_debug_module_comment(self):
        """ICSP section should reference the debug module (FICD.ICS)."""
        device = _make_minimal_device()
        config = _make_pin_config_with_icsp()
        files = generate_c_files(device, config)
        c_code = files["pin_config.c"]

        assert "FICD.ICS" in c_code


# ---------------------------------------------------------------------------
# system_init() Call Order Tests
# ---------------------------------------------------------------------------

class TestSystemInitOrder:
    """Tests that system_init() calls functions in the correct order."""

    def test_osc_before_pps_before_ports(self):
        """system_init() should call configure_oscillator() before configure_pps()
        before configure_ports()."""
        device = _make_minimal_device()
        config = _make_pin_config_basic()
        osc = OscConfig(source="frc_pll", target_fosc_hz=200_000_000)
        files = generate_c_files(device, config, osc_config=osc)
        c_code = files["pin_config.c"]

        # Extract system_init body
        init_match = re.search(
            r"void system_init\(void\)\s*\{([^}]+)\}", c_code, re.DOTALL
        )
        assert init_match is not None, "system_init() function not found"
        init_body = init_match.group(1)

        osc_pos = init_body.find("configure_oscillator()")
        pps_pos = init_body.find("configure_pps()")
        ports_pos = init_body.find("configure_ports()")

        assert osc_pos >= 0, "configure_oscillator() not called in system_init()"
        assert pps_pos >= 0, "configure_pps() not called in system_init()"
        assert ports_pos >= 0, "configure_ports() not called in system_init()"
        assert osc_pos < pps_pos < ports_pos, (
            "Call order must be: oscillator -> pps -> ports"
        )

    def test_no_osc_when_not_configured(self):
        """system_init() should NOT call configure_oscillator() when no osc_config given."""
        device = _make_minimal_device()
        config = _make_pin_config_basic()
        files = generate_c_files(device, config)
        c_code = files["pin_config.c"]

        init_match = re.search(
            r"void system_init\(void\)\s*\{([^}]+)\}", c_code, re.DOTALL
        )
        assert init_match is not None
        init_body = init_match.group(1)
        assert "configure_oscillator" not in init_body

    def test_ports_always_called(self):
        """system_init() should always call configure_ports()."""
        device = _make_minimal_device()
        config = _make_pin_config_basic()
        files = generate_c_files(device, config)
        c_code = files["pin_config.c"]

        init_match = re.search(
            r"void system_init\(void\)\s*\{([^}]+)\}", c_code, re.DOTALL
        )
        assert init_match is not None
        assert "configure_ports()" in init_match.group(1)


# ---------------------------------------------------------------------------
# Multi-File Output Tests
# ---------------------------------------------------------------------------

class TestMultiFileOutput:
    """Tests for the split .h/.c file generation."""

    def test_header_has_include_guard(self):
        """pin_config.h should have proper include guard."""
        device = _make_minimal_device()
        config = _make_pin_config_basic()
        files = generate_c_files(device, config)
        header = files["pin_config.h"]

        assert "#ifndef PIN_CONFIG_H" in header
        assert "#define PIN_CONFIG_H" in header
        assert "#endif /* PIN_CONFIG_H */" in header

    def test_header_has_prototypes(self):
        """pin_config.h should declare function prototypes."""
        device = _make_minimal_device()
        config = _make_pin_config_basic()
        files = generate_c_files(device, config)
        header = files["pin_config.h"]

        assert "void configure_pps(void);" in header
        assert "void configure_ports(void);" in header
        assert "void system_init(void);" in header

    def test_source_includes_header(self):
        """pin_config.c should include pin_config.h."""
        device = _make_minimal_device()
        config = _make_pin_config_basic()
        files = generate_c_files(device, config)
        c_code = files["pin_config.c"]

        assert '#include "pin_config.h"' in c_code

    def test_output_keys(self):
        """generate_c_files() should return a dict with exactly two keys."""
        device = _make_minimal_device()
        config = _make_pin_config_basic()
        files = generate_c_files(device, config)

        assert set(files.keys()) == {"pin_config.h", "pin_config.c"}

    def test_header_includes_xc_h(self):
        """pin_config.h should include xc.h."""
        device = _make_minimal_device()
        config = _make_pin_config_basic()
        files = generate_c_files(device, config)
        header = files["pin_config.h"]

        assert "#include <xc.h>" in header


# ---------------------------------------------------------------------------
# Signal Name Defines Tests
# ---------------------------------------------------------------------------

class TestSignalNameDefines:
    """Tests that user-defined signal names produce #define macros in the header."""

    def test_signal_defines_in_header(self):
        """Signal names should produce PORT, LAT, and TRIS defines in the header."""
        device = _make_minimal_device()
        config = _make_pin_config_basic()
        signal_names = {1: "UART_TX", 2: "UART_RX"}
        files = generate_c_files(device, config, signal_names=signal_names)
        header = files["pin_config.h"]

        assert "#define UART_TX_PORT" in header
        assert "#define UART_TX_LAT" in header
        assert "#define UART_TX_TRIS" in header
        assert "#define UART_RX_PORT" in header
        assert "#define UART_RX_LAT" in header
        assert "#define UART_RX_TRIS" in header

    def test_signal_defines_reference_correct_port(self):
        """Signal defines should reference the correct port bits."""
        device = _make_minimal_device()
        config = _make_pin_config_basic()
        signal_names = {1: "UART_TX"}
        files = generate_c_files(device, config, signal_names=signal_names)
        header = files["pin_config.h"]

        # Pin 1 is RB0
        assert "PORTB" in header
        assert "RB0" in header

    def test_no_signal_defines_when_none(self):
        """When no signal names are given, no defines should appear."""
        device = _make_minimal_device()
        config = _make_pin_config_basic()
        files = generate_c_files(device, config, signal_names=None)
        header = files["pin_config.h"]

        assert "Signal name" not in header

    def test_signal_name_sanitization(self):
        """Signal names with special characters should be sanitized to valid C identifiers."""
        device = _make_minimal_device()
        config = _make_pin_config_basic()
        signal_names = {1: "my-signal.1"}
        files = generate_c_files(device, config, signal_names=signal_names)
        header = files["pin_config.h"]

        # Hyphens and dots replaced with underscores, uppercased
        assert "#define MY_SIGNAL_1_PORT" in header


# ---------------------------------------------------------------------------
# Fuse Pragma in C Output Tests
# ---------------------------------------------------------------------------

class TestFusePragmasInOutput:
    """Tests that fuse pragmas appear in the .c output when FuseConfig is provided."""

    def test_fuse_pragmas_present_in_c_file(self):
        """When a FuseConfig is provided, its pragmas should appear in pin_config.c."""
        device = _make_minimal_device()
        config = _make_pin_config_basic()
        fuse = FuseConfig()
        files = generate_c_files(device, config, fuse_config=fuse)
        c_code = files["pin_config.c"]

        assert "#pragma config ICS" in c_code
        assert "#pragma config FWDTEN" in c_code
        assert "#pragma config BOREN" in c_code

    def test_no_fuse_pragmas_without_config(self):
        """When no FuseConfig is given, no fuse pragmas should appear."""
        device = _make_minimal_device()
        config = _make_pin_config_basic()
        files = generate_c_files(device, config, fuse_config=None)
        c_code = files["pin_config.c"]

        assert "#pragma config ICS" not in c_code
        assert "#pragma config FWDTEN" not in c_code

    def test_custom_fuse_values_in_output(self):
        """Custom fuse values should be reflected in the generated C code."""
        device = _make_minimal_device()
        config = _make_pin_config_basic()
        fuse = FuseConfig(ics=2, jtagen="ON", fwdten="SWON")
        files = generate_c_files(device, config, fuse_config=fuse)
        c_code = files["pin_config.c"]

        assert "ICS2" in c_code
        assert "JTAGEN = ON" in c_code
        assert "FWDTEN = SWON" in c_code

    def test_fuse_pragmas_also_in_single_file_output(self):
        """generate_c_code() single-file output should also contain fuse pragmas."""
        device = _make_minimal_device()
        config = _make_pin_config_basic()
        fuse = FuseConfig()
        single = generate_c_code(device, config, fuse_config=fuse)

        assert "#pragma config ICS" in single
        assert "#pragma config BOREN" in single


# ---------------------------------------------------------------------------
# PPS Code Generation Tests
# ---------------------------------------------------------------------------

class TestPPSCodeGeneration:
    """Tests for PPS input/output mapping code generation."""

    def test_pps_unlock_and_lock(self):
        """PPS configuration should include RPCON unlock and lock calls."""
        device = _make_minimal_device()
        config = _make_pin_config_basic()
        files = generate_c_files(device, config)
        c_code = files["pin_config.c"]

        assert "__builtin_write_RPCON(0x0000U)" in c_code
        assert "__builtin_write_RPCON(0x0800U)" in c_code

    def test_pps_input_mapping_register(self):
        """PPS input mapping should write to the correct RPINR register field."""
        device = _make_minimal_device()
        config = _make_pin_config_basic()
        files = generate_c_files(device, config)
        c_code = files["pin_config.c"]

        # U1RX mapped to RP33
        assert "RPINR18bits.U1RXR = 33U;" in c_code

    def test_pps_output_mapping_register(self):
        """PPS output mapping should write to the correct RPOR register field."""
        device = _make_minimal_device()
        config = _make_pin_config_basic()
        files = generate_c_files(device, config)
        c_code = files["pin_config.c"]

        # U1TX on RP32, ppsval=1
        assert "RPOR0bits.RP32R = 1U;" in c_code


# ---------------------------------------------------------------------------
# Port Configuration Tests
# ---------------------------------------------------------------------------

class TestPortConfiguration:
    """Tests for ANSEL and TRIS register generation."""

    def test_digital_pin_ansel_cleared(self):
        """Digital GPIO pins with ANSEL capability should have ANSEL cleared to 0."""
        device = _make_minimal_device()
        config = _make_pin_config_basic()
        files = generate_c_files(device, config)
        c_code = files["pin_config.c"]

        # RB0 has analog (AN0) but is used as U1TX (digital) -- ANSEL should be cleared
        assert "ANSELBbits.ANSELB0 = 0U;" in c_code

    def test_output_tris_set_to_zero(self):
        """Output pins should have TRIS set to 0."""
        device = _make_minimal_device()
        config = _make_pin_config_basic()
        files = generate_c_files(device, config)
        c_code = files["pin_config.c"]

        # RB2 is GPIO output
        assert "TRISBbits.TRISB2 = 0U;" in c_code

    def test_input_tris_set_to_one(self):
        """Input pins should have TRIS set to 1."""
        device = _make_minimal_device()
        config = _make_pin_config_basic()
        files = generate_c_files(device, config)
        c_code = files["pin_config.c"]

        # RB1 (U1RX) is input
        assert "TRISBbits.TRISB1 = 1U;" in c_code
