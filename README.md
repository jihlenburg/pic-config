# config-pic

**Version 0.5.0.0**

Pin multiplexing configurator for Microchip dsPIC33 microcontrollers.

Parses Microchip Device Family Pack (DFP) files, presents an interactive web UI for pin assignment, and generates ready-to-compile C initialization code.

## Features

- **Interactive package diagram** — DIP/SSOP and QFN/QFP layouts with clickable pins
- **Pin assignment** — assign PPS-remappable and fixed-function peripherals per pin
- **ICSP highlighting** — active debug pins (MCLR + selected PGCx/PGDx pair) highlighted in gold, updates dynamically with ICS fuse setting
- **Pin conflict detection** — conflicting assignments highlighted red with flash animation
- **Oscillator configuration** — PLL calculator with FRC, primary crystal, and LPRC sources
- **Configuration fuses** — FICD (ICSP pair, JTAG), FWDT (watchdog), FBORPOR (brown-out) pragma generation
- **Multi-file C output** — generates `pin_config.h` (defines, prototypes) and `pin_config.c` (implementation) with tab UI
- **system_init()** — master initialization function with correct call order (oscillator → PPS → ports → analog)
- **C code generation** — MISRA C:2012 compliant output with PPS unlock/lock, ANSEL, TRIS, and op-amp configuration
- **XC16 compile check** — optional syntax verification against the Microchip XC16 compiler
- **Undo/Redo** — Ctrl+Z / Ctrl+Shift+Z for pin assignments and signal names (50 levels)
- **Export** — download generated `pin_config.c` and `pin_config.h` files directly
- **Pin list export** — download a formatted pin assignment table for documentation (with optional grid lines)
- **Save/Load** — export and import pin configurations as JSON (includes fuse and oscillator settings)
- **Multi-package support** — switch between package variants (SSOP, UQFN, TQFP) for the same device

## Supported Devices

dsPIC33CK, dsPIC33CH, dsPIC33CD, dsPIC33AK, dsPIC33E, and dsPIC33F families. Device data is extracted from Microchip's `.atpack` DFP files.

## Quick Start

### Prerequisites

- Python 3.12+
- A Microchip DFP `.atpack` file (download from [Microchip Packs Repository](https://packs.download.microchip.com/))

### Install

```bash
pip install -r requirements.txt
```

### Run

```bash
python run.py
```

Open http://127.0.0.1:8642 in your browser.

### DFP Pack Location

Place `.atpack` files in any of these locations:

- `~/.mchp_packs/Microchip/`
- `~/Downloads/`
- `dfp_cache/` (project directory)

The tool searches these paths automatically when loading a device.

## Usage

1. Enter a part number (e.g., `DSPIC33CK64MP102`) and click **Load Device**
2. Select a package variant from the dropdown (if multiple available)
3. Assign peripherals to pins using the **Assignment** dropdown in each row
4. Optionally add signal names (e.g., `UART1_TX`) for `#define` aliases
5. Configure the oscillator source and target frequency
6. Configure fuse settings (ICSP pair, watchdog, brown-out reset)
7. Click **Generate C Code** to produce the initialization source
8. Use **Copy** to copy to clipboard, **Export** to download the `.c`/`.h` files, or **Save** to export the full configuration
9. Use **Export Pin List** to download a formatted pin assignment table for documentation

## Project Structure

```
config-pic/
  run.py               # Server entry point (uvicorn, port 8642)
  parser/
    edc_parser.py       # .PIC XML parser -> DeviceData model
    dfp_manager.py      # DFP discovery, extraction, caching
  codegen/
    generate.py         # C code generator (PPS, ports, op-amps)
    oscillator.py       # PLL divider calculation and pragma generation
    fuses.py            # Configuration fuse pragma generation
  web/
    app.py              # FastAPI API endpoints
    static/
      app.js            # Frontend application
      style.css         # Dark theme styles
      pin_descriptions.js  # Peripheral description tooltips
    templates/
      index.html        # Single-page HTML
  devices/              # Cached device JSON (auto-generated)
  dfp_cache/            # Extracted EDC files from .atpack
  pinouts/              # Pinout overlay files for alternate packages
  tests/                # Unit tests (pytest)
  doc/                  # Project documentation
```

## Versioning

This project uses four-segment versioning: `major.minor.patch.build` (e.g., `0.5.0.0`). The current version is recorded in the `VERSION` file at the repository root.

## License

Private project. All rights reserved.

## Disclaimer

**This project is not affiliated with, endorsed by, sponsored by, or in any way officially connected with Microchip Technology Inc. or any of its subsidiaries or affiliates.**

"Microchip", "dsPIC", "MPLAB", "XC16", and all related product names, logos, and trade dress are registered trademarks or trademarks of Microchip Technology Incorporated in the United States and other countries. All other trademarks are the property of their respective owners.

This tool parses publicly available Device Family Pack (DFP) files distributed by Microchip Technology Inc. for use with their development tools. The DFP files, their contents, and all device-specific data (register definitions, pin mappings, peripheral descriptions) remain the intellectual property of Microchip Technology Inc. and are subject to Microchip's own license terms.

This project does not redistribute any Microchip proprietary files. Users must obtain DFP `.atpack` files directly from Microchip's official distribution channels.
