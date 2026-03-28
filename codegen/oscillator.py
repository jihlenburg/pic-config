"""
Oscillator and PLL configuration for dsPIC33CK devices.

Calculates PLL divider values (N1, M, N2, N3) to achieve a target system clock
frequency, and generates C initialization code with #pragma config lines and
a configure_oscillator() function.

Supported clock sources:
  - FRC: Internal 8 MHz fast RC oscillator
  - FRC + PLL: FRC through PLL for higher frequencies (up to 200 MHz Fosc)
  - Primary: External oscillator (EC, XT, or HS crystal modes)
  - Primary + PLL: External oscillator through PLL
  - LPRC: Low-power 32 kHz RC oscillator

PLL constraints are per the dsPIC33CK family datasheet (DS70005363):
  - VCO range: 400–1600 MHz
  - PFD minimum: 8 MHz (FPLLI / N1 >= 8 MHz)
  - M range: 16–200, N1: 1–8, N2: 1–7, N3: 1–7
"""

from dataclasses import dataclass
from typing import Optional


# dsPIC33CK FRC nominal frequency
FRC_FREQ_HZ = 8_000_000

# PLL constraints (dsPIC33CK)
PLL_M_MIN = 16
PLL_M_MAX = 200
PLL_N1_MIN = 1
PLL_N1_MAX = 8
PLL_N2_MIN = 1
PLL_N2_MAX = 7
PLL_N3_MIN = 1
PLL_N3_MAX = 7
VCO_MIN_HZ = 400_000_000
VCO_MAX_HZ = 1_600_000_000
FPFD_MIN_HZ = 8_000_000


@dataclass
class OscConfig:
    """User-selected oscillator configuration."""
    source: str          # "frc", "frc_pll", "pri", "pri_pll", "lprc"
    target_fosc_hz: int  # Desired Fosc (system clock before /2)
    crystal_hz: int = 0  # Primary oscillator crystal frequency (if applicable)
    poscmd: str = "EC"   # Primary oscillator mode: "EC", "XT", "HS", "NONE"


@dataclass
class PLLResult:
    """Calculated PLL divider values."""
    n1: int       # PLLPRE (prescaler)
    m: int        # PLLFBDIV (feedback)
    n2: int       # POST1DIV (postscaler 1)
    n3: int       # POST2DIV (postscaler 2)
    fplli: int    # PLL input frequency
    fvco: int     # VCO frequency
    fosc: int     # Actual output frequency
    fcy: int      # Instruction cycle frequency (Fosc/2)
    error_ppm: int  # Frequency error in ppm


def calculate_pll(fplli_hz: int, target_fosc_hz: int) -> Optional[PLLResult]:
    """Find PLL divider values (N1, M, N2, N3) to achieve target Fosc.

    Returns the best result (lowest error), or None if no valid solution exists.
    """
    best: Optional[PLLResult] = None

    for n1 in range(PLL_N1_MIN, PLL_N1_MAX + 1):
        fpfd = fplli_hz / n1
        if fpfd < FPFD_MIN_HZ:
            continue

        for n2 in range(PLL_N2_MIN, PLL_N2_MAX + 1):
            for n3 in range(PLL_N3_MIN, PLL_N3_MAX + 1):
                # M = target_fosc * N1 * N2 * N3 / fplli
                m_exact = target_fosc_hz * n1 * n2 * n3 / fplli_hz
                m = round(m_exact)
                if m < PLL_M_MIN or m > PLL_M_MAX:
                    continue

                fvco = fplli_hz * m / n1
                if fvco < VCO_MIN_HZ or fvco > VCO_MAX_HZ:
                    continue

                fosc = int(fvco / (n2 * n3))
                fcy = fosc // 2

                if target_fosc_hz > 0:
                    error_ppm = abs(fosc - target_fosc_hz) * 1_000_000 // target_fosc_hz
                else:
                    error_ppm = 0

                result = PLLResult(
                    n1=n1, m=m, n2=n2, n3=n3,
                    fplli=fplli_hz, fvco=int(fvco),
                    fosc=fosc, fcy=fcy,
                    error_ppm=error_ppm,
                )

                if best is None or error_ppm < best.error_ppm:
                    best = result
                    if error_ppm == 0:
                        return best  # exact match

    return best


def _xtcfg_for_crystal(crystal_hz: int) -> str:
    """Return the XTCFG pragma value for a given crystal frequency."""
    mhz = crystal_hz / 1_000_000
    if mhz <= 8:
        return "G0"
    elif mhz <= 16:
        return "G1"
    elif mhz <= 24:
        return "G2"
    else:
        return "G3"


def generate_osc_code(osc: OscConfig) -> tuple[str, str]:
    """Generate oscillator configuration code.

    Returns (pragmas, init_function) as separate strings so the caller
    can place pragmas at file top and the function with other code.
    """
    pragma_lines = []
    init_lines = []

    if osc.source == "frc":
        # Plain FRC, no PLL
        pragma_lines.append("/* Oscillator configuration: FRC (8 MHz), Fcy = 4 MHz */")
        pragma_lines.append("#pragma config FNOSC = FRC        /* Fast RC Oscillator */")
        pragma_lines.append("#pragma config IESO = OFF         /* Start with selected oscillator */")
        pragma_lines.append("#pragma config POSCMD = NONE      /* Primary oscillator disabled */")
        pragma_lines.append("#pragma config FCKSM = CSDCMD     /* Clock switching disabled */")
        return "\n".join(pragma_lines), ""

    elif osc.source == "lprc":
        pragma_lines.append("/* Oscillator configuration: LPRC (32 kHz), Fcy = 16 kHz */")
        pragma_lines.append("#pragma config FNOSC = LPRC       /* Low-Power RC Oscillator */")
        pragma_lines.append("#pragma config IESO = OFF         /* Start with selected oscillator */")
        pragma_lines.append("#pragma config POSCMD = NONE      /* Primary oscillator disabled */")
        pragma_lines.append("#pragma config FCKSM = CSDCMD     /* Clock switching disabled */")
        return "\n".join(pragma_lines), ""

    elif osc.source == "pri":
        # Primary oscillator without PLL
        fosc = osc.crystal_hz
        fcy = fosc // 2
        pragma_lines.append(f"/* Oscillator configuration: Primary ({osc.poscmd}), "
                          f"Fosc = {fosc/1e6:.3f} MHz, Fcy = {fcy/1e6:.3f} MHz */")
        pragma_lines.append(f"#pragma config FNOSC = PRI        /* Primary Oscillator */")
        pragma_lines.append(f"#pragma config IESO = OFF         /* Start with selected oscillator */")
        pragma_lines.append(f"#pragma config POSCMD = {osc.poscmd}"
                          f"{'  ' if len(osc.poscmd) < 4 else ' '}/* Primary oscillator mode */")
        if osc.poscmd in ("XT", "HS"):
            xtcfg = _xtcfg_for_crystal(osc.crystal_hz)
            pragma_lines.append(f"#pragma config XTCFG = {xtcfg}"
                              f"          /* Crystal range: {xtcfg} */")
        pragma_lines.append(f"#pragma config FCKSM = CSDCMD     /* Clock switching disabled */")
        return "\n".join(pragma_lines), ""

    elif osc.source in ("frc_pll", "pri_pll"):
        # PLL mode
        if osc.source == "frc_pll":
            fplli = FRC_FREQ_HZ
            fnosc = "FRCPLL"
            fnosc_comment = "FRC with PLL"
            poscmd = "NONE"
        else:
            fplli = osc.crystal_hz
            fnosc = "PRIPLL"
            fnosc_comment = "Primary Oscillator with PLL"
            poscmd = osc.poscmd

        pll = calculate_pll(fplli, osc.target_fosc_hz)
        if pll is None:
            pragma_lines.append("/* ERROR: no valid PLL configuration found for target frequency */")
            return "\n".join(pragma_lines), ""

        pragma_lines.append(f"/* Oscillator configuration: {fnosc_comment} */")
        pragma_lines.append(f"/* Fosc = {pll.fosc/1e6:.3f} MHz, Fcy = {pll.fcy/1e6:.3f} MHz */")
        pragma_lines.append(f"/* PLL: FPLLI={pll.fplli/1e6:.1f} MHz, "
                          f"M={pll.m}, N1={pll.n1}, N2={pll.n2}, N3={pll.n3}, "
                          f"FVCO={pll.fvco/1e6:.1f} MHz */")
        if pll.error_ppm > 0:
            pragma_lines.append(f"/* Frequency error: {pll.error_ppm} ppm */")
        pragma_lines.append(f"#pragma config FNOSC = {fnosc}"
                          f"{'  ' if len(fnosc) < 6 else ' '}/* {fnosc_comment} */")
        pragma_lines.append(f"#pragma config IESO = OFF         /* Start with selected oscillator */")
        pragma_lines.append(f"#pragma config POSCMD = {poscmd}"
                          f"{'  ' if len(poscmd) < 4 else ' '}/* Primary oscillator mode */")
        if poscmd in ("XT", "HS"):
            xtcfg = _xtcfg_for_crystal(osc.crystal_hz)
            pragma_lines.append(f"#pragma config XTCFG = {xtcfg}"
                              f"          /* Crystal range: {xtcfg} */")
        pragma_lines.append(f"#pragma config FCKSM = CSDCMD     /* Clock switching disabled */")
        pragma_lines.append(f"#pragma config PLLKEN = ON        /* Disable output if PLL loses lock */")

        # Generate PLL init function
        init_lines.append("/* ---------------------------------------------------------------------------")
        init_lines.append(" * configure_oscillator")
        init_lines.append(" *")
        init_lines.append(f" * Configures the PLL for Fosc = {pll.fosc/1e6:.3f} MHz "
                        f"(Fcy = {pll.fcy/1e6:.3f} MHz).")
        init_lines.append(f" * PLL input: {pll.fplli/1e6:.1f} MHz, "
                        f"VCO: {pll.fvco/1e6:.1f} MHz")
        init_lines.append(f" * Fosc = FPLLI * M / (N1 * N2 * N3) "
                        f"= {pll.fplli/1e6:.1f} * {pll.m} / "
                        f"({pll.n1} * {pll.n2} * {pll.n3})")
        init_lines.append(" * -------------------------------------------------------------------------*/")
        init_lines.append("void configure_oscillator(void)")
        init_lines.append("{")
        init_lines.append(f"    /* PLL prescaler: N1 = {pll.n1} */")
        init_lines.append(f"    CLKDIVbits.PLLPRE = {pll.n1}U;")
        init_lines.append("")
        init_lines.append(f"    /* PLL feedback divider: M = {pll.m} */")
        init_lines.append(f"    PLLFBDbits.PLLFBDIV = {pll.m}U;")
        init_lines.append("")
        init_lines.append(f"    /* PLL postscaler #1: N2 = {pll.n2} */")
        init_lines.append(f"    PLLDIVbits.POST1DIV = {pll.n2}U;")
        init_lines.append("")
        init_lines.append(f"    /* PLL postscaler #2: N3 = {pll.n3} */")
        init_lines.append(f"    PLLDIVbits.POST2DIV = {pll.n3}U;")
        init_lines.append("")
        init_lines.append("    /* Wait for PLL to lock */")
        init_lines.append("    while (OSCCONbits.LOCK != 1U)")
        init_lines.append("    {")
        init_lines.append("        /* Intentionally empty — MISRA C:2012 Rule 15.6 */")
        init_lines.append("    }")
        init_lines.append("}")
        init_lines.append("")

        return "\n".join(pragma_lines), "\n".join(init_lines)

    return "", ""
