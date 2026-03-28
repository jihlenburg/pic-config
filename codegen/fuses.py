"""
Configuration fuse generation for dsPIC33CK devices.
Generates #pragma config lines for FICD, FWDT, and FBORPOR registers.
"""

from dataclasses import dataclass


# Valid values for each fuse field
ICS_VALUES = (1, 2, 3)
JTAGEN_VALUES = ("ON", "OFF")
FWDTEN_VALUES = ("OFF", "ON", "SWON")
WDTPS_VALUES = (
    "PS1", "PS2", "PS4", "PS8", "PS16", "PS32", "PS64", "PS128",
    "PS256", "PS512", "PS1024", "PS2048", "PS4096", "PS8192",
    "PS16384", "PS32768",
)
BOREN_VALUES = ("ON", "OFF")
BORV_VALUES = ("BOR_LOW", "BOR_MID", "BOR_HIGH")


@dataclass
class FuseConfig:
    """User-selected configuration fuse settings."""
    # FICD — Debug Configuration
    ics: int = 1            # PGCx/PGDx pair (1, 2, or 3)
    jtagen: str = "OFF"     # JTAG enable: ON or OFF

    # FWDT — Watchdog Timer
    fwdten: str = "OFF"     # Watchdog enable: OFF, ON, or SWON
    wdtps: str = "PS1024"   # Watchdog prescaler: PS1 through PS32768

    # FBORPOR — Brown-out / Power-on Reset
    boren: str = "ON"       # Brown-out reset enable: ON or OFF
    borv: str = "BOR_HIGH"  # Brown-out voltage: BOR_LOW, BOR_MID, BOR_HIGH


def generate_fuse_pragmas(fuse: FuseConfig) -> str:
    """Generate #pragma config lines for configuration fuses.

    Returns a string of pragma lines for FICD, FWDT, and FBORPOR registers.
    """
    pragma_lines = []

    # --- FICD: Debug Configuration ---
    pragma_lines.append("/* FICD — Debug Configuration */")
    pragma_lines.append(f"#pragma config ICS = ICS{fuse.ics}"
                        f"        /* Use PGC{fuse.ics}/PGD{fuse.ics} for debugging */")
    pragma_lines.append(f"#pragma config JTAGEN = {fuse.jtagen}"
                        f"{'      ' if len(fuse.jtagen) < 3 else '     '}"
                        f"/* JTAG port {'enabled' if fuse.jtagen == 'ON' else 'disabled'} */")

    pragma_lines.append("")

    # --- FWDT: Watchdog Timer ---
    pragma_lines.append("/* FWDT — Watchdog Timer */")
    if fuse.fwdten == "OFF":
        wdt_comment = "Watchdog timer disabled"
    elif fuse.fwdten == "ON":
        wdt_comment = "Watchdog timer always enabled"
    else:
        wdt_comment = "Watchdog timer controlled by software (WDTCON)"
    pragma_lines.append(f"#pragma config FWDTEN = {fuse.fwdten}"
                        f"{'     ' if len(fuse.fwdten) < 4 else '    '}"
                        f"/* {wdt_comment} */")
    pragma_lines.append(f"#pragma config WDTPS = {fuse.wdtps}"
                        f"{'  ' if len(fuse.wdtps) < 6 else ' '}"
                        f"/* Watchdog prescaler: {fuse.wdtps} */")

    pragma_lines.append("")

    # --- FBORPOR: Brown-out / Power-on Reset ---
    pragma_lines.append("/* FBORPOR — Brown-out / Power-on Reset */")
    pragma_lines.append(f"#pragma config BOREN = {fuse.boren}"
                        f"{'       ' if len(fuse.boren) < 3 else '      '}"
                        f"/* Brown-out reset {'enabled' if fuse.boren == 'ON' else 'disabled'} */")
    borv_labels = {
        "BOR_LOW": "low threshold",
        "BOR_MID": "mid threshold",
        "BOR_HIGH": "high threshold",
    }
    borv_label = borv_labels.get(fuse.borv, fuse.borv)
    pragma_lines.append(f"#pragma config BORV = {fuse.borv}"
                        f"{'  ' if len(fuse.borv) < 8 else ' '}"
                        f"/* Brown-out voltage: {borv_label} */")

    return "\n".join(pragma_lines)
