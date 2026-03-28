# C Code Generator

The code generator (`codegen/generate.py`, `codegen/oscillator.py`, `codegen/fuses.py`) takes a device model and user pin assignments and produces two output files: `pin_config.h` and `pin_config.c`.

## Input Data Model

### PinAssignment

Each user-assigned pin is represented as a `PinAssignment` dataclass:

```python
@dataclass
class PinAssignment:
    pin_position: int           # Physical pin number on the package
    rp_number: int | None       # RP number (for PPS-remappable pins)
    peripheral: str             # e.g. "U1TX", "AN0", "OA1OUT"
    direction: str              # "in", "out", or "io"
    ppsval: int | None          # PPS output value (for output mappings)
    fixed: bool                 # True for fixed-function peripherals
```

### PinConfig

A complete configuration bundles the part number, all assignments, and any explicit digital pin overrides:

```python
@dataclass
class PinConfig:
    part_number: str
    assignments: list[PinAssignment]
    digital_pins: list[int]       # Additional pins forced to digital mode
```

### OscConfig

Oscillator configuration:

```python
@dataclass
class OscConfig:
    source: str          # "frc", "frc_pll", "pri", "pri_pll", "lprc"
    target_fosc_hz: int  # Desired system clock frequency
    crystal_hz: int      # Primary oscillator crystal (if applicable)
    poscmd: str          # "EC", "XT", "HS", or "NONE"
```

### FuseConfig

Configuration fuse settings:

```python
@dataclass
class FuseConfig:
    ics: int             # ICSP pair: 1, 2, or 3
    jtagen: str          # "ON" or "OFF"
    fwdten: str          # "OFF", "ON", or "SWON"
    wdtps: str           # "PS1" through "PS32768"
    boren: str           # "ON" or "OFF"
    borv: str            # "BOR_LOW", "BOR_MID", or "BOR_HIGH"
```

## Output Structure

### pin_config.h

The header file contains:

1. **File-level Doxygen comment** with device part number and package.
2. **Include guard** (`#ifndef PIN_CONFIG_H`).
3. **`#include <xc.h>`** for Microchip device headers.
4. **Signal name aliases** (if the user defined any). These map user-provided names to PORT/LAT/TRIS bit-fields:

```c
#define UART1_TX_PORT  (PORTBbits.RB5)
#define UART1_TX_LAT   (LATBbits.LATB5)
#define UART1_TX_TRIS  (TRISBbits.TRISB5)
```

5. **Function prototypes** for all generated functions:

```c
void configure_oscillator(void);  /* only if PLL mode */
void configure_pps(void);         /* only if PPS assignments exist */
void configure_ports(void);       /* always present */
void configure_analog(void);      /* only if op-amp assignments exist */
void system_init(void);           /* always present */
```

### pin_config.c

The implementation file contains, in order:

1. **File-level Doxygen comment**.
2. **`#include "pin_config.h"`**.
3. **Oscillator `#pragma config`** lines (FNOSC, IESO, POSCMD, FCKSM, PLLKEN, XTCFG).
4. **Fuse `#pragma config`** lines (ICS, JTAGEN, FWDTEN, WDTPS, BOREN, BORV).
5. **`configure_oscillator()`** -- PLL register programming (CLKDIV, PLLFBD, PLLDIV) with PLL lock wait loop.
6. **`configure_pps()`** -- PPS unlock, RPINR input mappings, RPOR output mappings, PPS lock.
7. **`configure_ports()`** -- ANSEL writes (analog/digital), TRIS writes (direction), ICSP pin reservations.
8. **`configure_analog()`** -- Op-amp module enables (AMPxCONbits.AMPEN).
9. **`system_init()`** -- Master init that calls the above in the correct order.

## system_init() Call Order

The generated `system_init()` calls subroutines in a fixed order chosen for hardware correctness:

```c
void system_init(void)
{
    configure_oscillator();   // Clock must be stable first
    configure_pps();          // PPS requires RPCON unlock/lock sequence
    configure_ports();        // ANSEL + TRIS after PPS is mapped
    configure_analog();       // Op-amp enables last (need stable power/clock)
}
```

Functions are only included if the corresponding configuration exists. For example, `configure_oscillator()` is omitted when the user selects plain FRC (no PLL registers to program -- only pragmas are needed).

## PPS Handling

### Unlock/Lock Sequence

PPS register writes require the RPCON register to be unlocked first:

```c
__builtin_write_RPCON(0x0000U);  /* Unlock (clear IOLOCK) */
/* ... RPINR / RPOR writes ... */
__builtin_write_RPCON(0x0800U);  /* Lock (set IOLOCK) */
```

### Input Mappings (RPINR)

Each PPS input assignment writes to an RPINR register field. The generator looks up the peripheral name (e.g., `U1RXR`) in the device's `pps_input_mappings` to find the register and field:

```c
RPINR18bits.U1RXR = 45U;  /* U1RX <- RP45/RB13 */
```

### Output Mappings (RPOR)

Each PPS output assignment writes to an RPOR register field using the `ppsval` from the device data:

```c
RPOR2bits.RP37R = 1U;  /* RP37/RB5 -> U1TX */
```

## ICSP Pin Handling

Pins matching the ICSP debug pattern (MCLR, PGC1-3, PGD1-3, PGEC1-3, PGED1-3) receive special treatment. The regex used for detection:

```python
_ICSP_RE = re.compile(r"^MCLR$|^PGC\d$|^PGD\d$|^PGEC\d$|^PGED\d$")
```

ICSP pins are **excluded** from both ANSEL and TRIS code generation. Instead, a reservation comment is emitted:

```c
/* ICSP/debug pins -- directly controlled by the debug module (FICD.ICS) */
/* RB0 reserved for PGD1 -- no ANSEL/TRIS configuration needed */
/* RB1 reserved for PGC1 -- no ANSEL/TRIS configuration needed */
```

This prevents user code from interfering with the in-circuit debug interface.

## Signal Name Defines

When the user provides signal names (e.g., "UART1_TX" for pin 5), the generator creates `#define` macros in the header that map the signal name to three register accessors:

- `_PORT` -- read the pin state
- `_LAT` -- write the output latch
- `_TRIS` -- control pin direction

The signal name is sanitized: non-alphanumeric characters are replaced with underscores, and the result is uppercased.

## Port Configuration

### ANSEL (Analog/Digital Selection)

Pins assigned to ADC channels (matching `^AN[A-Z]?\d+$`) get `ANSELxbits.ANSELxy = 1U` (analog mode). All other assigned pins get `ANSELxbits.ANSELxy = 0U` (digital mode). The generator checks `device.ansel_bits` to confirm the bit actually exists before emitting a write.

### TRIS (Direction)

Each assigned pin gets a TRIS write based on its direction:

- `direction == "out"` -> `TRISxbits.TRISxy = 0U`
- `direction == "in"` -> `TRISxbits.TRISxy = 1U`
- `direction == "io"` -> `TRISxbits.TRISxy = 1U` with a comment noting the user should modify as needed

## Oscillator Code Generation

### Supported Modes

| Source      | FNOSC Pragma | PLL Init Function | Notes |
|-------------|-------------|-------------------|-------|
| `frc`       | `FRC`       | No                | 8 MHz FRC, Fcy = 4 MHz |
| `lprc`      | `LPRC`      | No                | 32 kHz LPRC, Fcy = 16 kHz |
| `pri`       | `PRI`       | No                | Crystal frequency, no PLL |
| `frc_pll`   | `FRCPLL`    | Yes               | FRC -> PLL -> target Fosc |
| `pri_pll`   | `PRIPLL`    | Yes               | Crystal -> PLL -> target Fosc |

### PLL Calculation

The PLL solver (`calculate_pll()`) searches all valid combinations of N1, M, N2, N3 within hardware constraints:

- **N1 (PLLPRE)**: 1--8
- **M (PLLFBDIV)**: 16--200
- **N2 (POST1DIV)**: 1--7
- **N3 (POST2DIV)**: 1--7
- **VCO frequency**: 400--1600 MHz
- **PLL input (FPFD)**: >= 8 MHz

Formula: `Fosc = FPLLI * M / (N1 * N2 * N3)`

The solver returns the combination with the lowest frequency error in ppm. If an exact match is found, it returns immediately.

## MISRA C:2012 Compliance

The generated code follows these MISRA C:2012 guidelines:

- All integer constants use the `U` suffix (e.g., `0x0800U`, `1U`, `45U`).
- No implicit conversions or missing suffixes on literals.
- Empty loop bodies contain an explicit comment: `/* Intentionally empty -- MISRA C:2012 Rule 15.6 */`.
- All functions have `void` parameter lists.
- C99 standard (`-std=c99` compatible).
- Every register write has a trailing comment explaining its purpose.
- Inline comments within each code block are aligned to a consistent column for readability. Each section (PPS, TRIS, ANSEL, pragmas) aligns independently.
