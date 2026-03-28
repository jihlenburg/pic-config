# Configuration Guide

This document describes how to use config-pic to configure a dsPIC33 microcontroller: loading a device, assigning pins, setting the oscillator and fuses, generating code, and saving/loading configurations.

## Loading a Device

1. Enter a part number in the input field (e.g., `DSPIC33CK64MP102`). Part numbers are case-insensitive.
2. Click **Load Device** (or press Enter).
3. The tool searches for a matching DFP file and loads the device data.
4. A package diagram and pin assignment table are rendered.

### Package Selection

If multiple package variants are available (e.g., SSOP and UQFN), a dropdown appears. Selecting a different package redraws the pin diagram while preserving existing assignments. Package variants come from the EDC file (default) and from pinout overlay files.

## Pin Assignments

Each pin in the assignment table shows:

- **Position**: physical pin number
- **Pad name**: canonical GPIO name (e.g., RB5)
- **Functions**: all multiplexed functions available on that pad
- **Assignment dropdown**: select a peripheral to assign
- **Signal name**: optional user-defined name for `#define` aliases

### PPS-Remappable Pins

Pins with an RP number can be assigned any PPS-remappable peripheral. The dropdown is populated from the device's `remappable_inputs` and `remappable_outputs` lists. PPS assignments generate RPINR (input) or RPOR (output) register writes with the RPCON unlock/lock sequence.

### Fixed-Function Peripherals

Some peripherals are fixed to specific pins (e.g., ADC analog inputs, op-amp I/O). These are marked as `fixed: true` in the assignment and do not generate PPS register writes -- only ANSEL and TRIS configuration.

### ICSP/Debug Pins

MCLR, PGC1/PGD1 (and PGC2/PGD2, PGC3/PGD3) are ICSP debug pins controlled by the FICD configuration register. The active debug pair is highlighted in gold on the package diagram and pin table; changing the ICS fuse setting dynamically moves the highlighting to the selected pair. Assigning ICSP pins generates only a reservation comment -- no ANSEL or TRIS writes, since the debug module controls them.

### Conflict Detection

The frontend checks for assignment conflicts:

- Two peripherals assigned to the same pin
- A PPS peripheral assigned to a pin without an RP number
- Duplicate PPS output values

Conflicts are highlighted in the UI.

### Undo / Redo

All assignment and signal name changes can be undone (Ctrl+Z) and redone (Ctrl+Y). The undo stack holds up to 50 snapshots. Each snapshot captures the full `assignments` and `signalNames` state via `structuredClone`.

## Oscillator Settings

The oscillator panel configures the system clock source and frequency. Settings are placed in `#pragma config` lines and, for PLL modes, in a `configure_oscillator()` function.

### Available Sources

| Source | Description | Generated Code |
|--------|-------------|----------------|
| (none) | No oscillator configuration | Nothing |
| FRC | Internal 8 MHz fast RC oscillator | Pragmas only |
| FRC + PLL | FRC through PLL to target frequency | Pragmas + init function |
| Primary | External crystal/clock | Pragmas only |
| Primary + PLL | External crystal through PLL | Pragmas + init function |
| LPRC | Internal 32 kHz low-power RC | Pragmas only |

### FRC (Fast RC Oscillator)

Selects the internal 8 MHz oscillator. No PLL, no runtime initialization needed.

- Fosc = 8 MHz, Fcy = 4 MHz
- Primary oscillator disabled (`POSCMD = NONE`)
- Clock switching disabled (`FCKSM = CSDCMD`)

### FRC + PLL

Routes the 8 MHz FRC through the PLL to achieve a higher target frequency. The PLL solver finds optimal divider values:

- **N1 (PLLPRE)**: 1--8
- **M (PLLFBDIV)**: 16--200
- **N2 (POST1DIV)**: 1--7
- **N3 (POST2DIV)**: 1--7

Formula: `Fosc = 8 MHz * M / (N1 * N2 * N3)`

Common target: 200 MHz Fosc (100 MHz Fcy) with M=100, N1=1, N2=2, N3=2.

The generated `configure_oscillator()` function programs CLKDIV, PLLFBD, and PLLDIV registers, then waits for the PLL to lock (`OSCCONbits.LOCK`).

### Primary Oscillator

External crystal or clock input. Three modes:

- **EC**: External clock input (single pin)
- **XT**: Crystal oscillator (low frequency, <= 10 MHz typical)
- **HS**: High-speed crystal oscillator (> 10 MHz)

For XT and HS modes, the generator selects the correct `XTCFG` gain setting based on crystal frequency (G0 for <= 8 MHz, G1 for <= 16 MHz, G2 for <= 24 MHz, G3 above).

### Primary + PLL

Routes the external crystal through the PLL. Same divider search as FRC + PLL, but with the crystal frequency as the PLL input.

### LPRC (Low-Power RC Oscillator)

Selects the internal 32 kHz oscillator. Used for ultra-low-power modes.

- Fosc = 32 kHz, Fcy = 16 kHz

## Configuration Fuses

The fuses panel configures three configuration registers via `#pragma config` directives. These are burned into the device at programming time and control hardware behavior at reset.

### FICD -- Debug Configuration

| Setting | Options | Default | Description |
|---------|---------|---------|-------------|
| ICS | 1, 2, 3 | 1 | Selects the PGCx/PGDx ICSP debug pin pair |
| JTAGEN | ON, OFF | OFF | Enables or disables the JTAG debug port |

`ICS = ICS1` selects PGC1/PGD1 as the active debug pair (factory default). Setting JTAGEN to OFF frees the JTAG pins (typically TDI, TDO, TMS, TCK) for general I/O use.

### FWDT -- Watchdog Timer

| Setting | Options | Default | Description |
|---------|---------|---------|-------------|
| FWDTEN | OFF, ON, SWON | OFF | Watchdog enable mode |
| WDTPS | PS1 -- PS32768 | PS1024 | Watchdog prescaler period |

- **OFF**: watchdog disabled entirely
- **ON**: watchdog always running (hardware-controlled)
- **SWON**: watchdog controlled by software via the WDTCON register

The prescaler values range from PS1 (shortest timeout) to PS32768 (longest).

### FBORPOR -- Brown-out / Power-on Reset

| Setting | Options | Default | Description |
|---------|---------|---------|-------------|
| BOREN | ON, OFF | ON | Brown-out reset enable |
| BORV | BOR_LOW, BOR_MID, BOR_HIGH | BOR_HIGH | Brown-out voltage threshold |

Brown-out reset forces a device reset when the supply voltage drops below the configured threshold. BOR_HIGH provides the most conservative (highest voltage) threshold.

## Code Generation

After configuring pins, oscillator, and fuses:

1. Click **Generate C Code**.
2. The tool sends all configuration to `POST /api/codegen`.
3. Two files are returned: `pin_config.h` and `pin_config.c`.
4. Both files are displayed in a tabbed code viewer.
5. Click **Copy** to copy the active tab's contents to the clipboard.
6. Click **Export** to download both `pin_config.c` and `pin_config.h` files directly.

### Pin List Export

Click **Export Pin List** in the summary bar to download a formatted plain text pin assignment table. The output includes pin number, pad name, assigned function, and signal name in aligned columns. Use the **Grid** checkbox to toggle box-drawing grid lines on or off.

### Generated File Contents

**pin_config.h**: Include guard, `#include <xc.h>`, signal name `#define` macros, function prototypes.

**pin_config.c**: `#include "pin_config.h"`, oscillator pragmas, fuse pragmas, `configure_oscillator()`, `configure_pps()`, `configure_ports()`, `configure_analog()`, `system_init()`.

### Compile Check

If the Microchip XC16 compiler (`xc16-gcc`) is installed, a **Compile Check** button appears. This sends the generated code to `POST /api/compile-check`, which compiles it with `-Wall -Werror -std=c99` and reports any errors or warnings.

## Save / Load Workflow

### Saving a Configuration

Click **Save** to export the current state as a JSON file. The file is named `{PART_NUMBER}_{PACKAGE}.json` and contains:

```json
{
  "part_number": "DSPIC33CK64MP102",
  "package": "28-pin SSOP",
  "assignments": {
    "5": {"peripheral": "U1TX", "direction": "out", "ppsval": 1, "rp_number": 37, "fixed": false},
    ...
  },
  "signal_names": {
    "5": "UART1_TX",
    ...
  },
  "oscillator": {
    "source": "frc_pll",
    "target_fosc_mhz": 200,
    "crystal_mhz": 8,
    "poscmd": "EC"
  },
  "fuses": {
    "ics": 1,
    "jtagen": "OFF",
    "fwdten": "OFF",
    "wdtps": "PS1024",
    "boren": "ON",
    "borv": "BOR_HIGH"
  }
}
```

### Loading a Configuration

1. Click **Load** and select a previously saved JSON file.
2. The tool restores:
   - Part number and package selection
   - All pin assignments and signal names
   - Oscillator settings (source, target frequency, crystal frequency, POSCMD mode)
   - Fuse settings (ICS, JTAGEN, FWDTEN, WDTPS, BOREN, BORV)
3. The device is reloaded to ensure current data, then the saved assignments are applied.

Integer keys (pin positions) are automatically converted from string format during JSON deserialization.
