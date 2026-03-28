# config-pic — Claude Code Guidelines

## Project Overview

Local web-based pin multiplexing configurator for Microchip dsPIC33 microcontrollers. Parses Device Family Pack (DFP) `.atpack` files, presents an interactive pin assignment UI, and generates MISRA C:2012 compliant initialization code.

## Architecture

```
config-pic/
  parser/          # EDC XML parsing, DFP pack management
    edc_parser.py  # Parses .PIC (XML) files into DeviceData
    dfp_manager.py # Finds/extracts .atpack files, caches devices
  codegen/         # C code generation
    generate.py    # PPS, TRIS, ANSEL, op-amp code generation
    oscillator.py  # PLL calculation and oscillator pragma generation
  web/             # FastAPI backend + vanilla JS frontend
    app.py         # API endpoints (/api/device, /api/codegen, etc.)
    static/app.js  # Single-page frontend (no framework)
    static/style.css
    templates/index.html
  devices/         # Cached device JSON files
  dfp_cache/       # Extracted .PIC files from DFP packs
  pinouts/         # Pinout overlay JSON files (alternate packages)
  tests/           # Unit tests (pytest)
```

## Key Data Flow

1. User enters part number -> `/api/device/{part}` -> `dfp_manager.load_device()` -> `edc_parser.parse_edc_file()`
2. Frontend renders package diagram + pin table from resolved pin data
3. User assigns peripherals -> frontend collects assignments
4. "Generate" -> `POST /api/codegen` -> `codegen.generate.generate_c_code()` -> C source returned

## Development

```bash
python run.py                    # Start server on http://127.0.0.1:8642
pytest tests/ -v                 # Run unit tests
```

## Conventions

- **Python**: Python 3.12+, type hints, dataclasses. No external dependencies beyond FastAPI/uvicorn/jinja2.
- **Frontend**: Vanilla JS, no build step, no framework. All state in global variables.
- **CSS**: CSS custom properties in `:root`, dark theme only. Peripheral colors: UART=`--uart`, SPI=`--spi`, I2C=`--i2c`, PWM=`--pwm`.
- **Code generation output**: MISRA C:2012 compliant C99. All register values use `U` suffix. Comments explain every write.
- **No auto-commit**: Never commit or push without explicit user permission.

## Important Patterns

- `DeviceData` (in `edc_parser.py`) is the central data model — pads, pinouts, PPS mappings, port registers, ANSEL bits.
- `resolve_pins(package)` on DeviceData returns the pin list for a specific package variant.
- ICSP pins (MCLR, PGC1, PGD1) are detected by regex and excluded from ANSEL/TRIS code generation — only a reservation comment is emitted.
- Pinout overlays in `pinouts/*.json` add alternate package variants not present in the EDC file.
- The Mouser API (key in `../bom-builder/.env`) can be used for part availability queries.

## Microchip dsPIC33 Domain Knowledge

- PPS (Peripheral Pin Select): remappable I/O via RPINR/RPOR registers, requires RPCON unlock/lock.
- FICD.ICS selects the active ICSP debug pair (PGC1/PGD1 is factory default).
- Part number format: `DSPIC33CK64MP102T-E/M6VAO` = base + T(tape/reel) + temp grade + /package + VAO(automotive).
- Config fuses: `#pragma config` for FICD, FWDT, FOSCSEL, FOSC, FBORPOR.

## What NOT to Do

- Don't add npm/webpack/bundler tooling — the frontend is intentionally dependency-free.
- Don't mock the EDC parser in integration tests — use real DeviceData fixtures.
- Don't generate ANSEL/TRIS writes for ICSP debug pins.
- Don't auto-format generated C code — the output formatting is intentional.
