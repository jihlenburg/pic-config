# System Architecture

config-pic is a local web application for configuring pin multiplexing on Microchip dsPIC33 microcontrollers. It parses Device Family Pack (DFP) files, presents an interactive pin assignment UI, and generates MISRA C:2012 compliant initialization code.

## High-Level Architecture

```
+------------------------------------------------------+
|                     Browser (Frontend)                |
|                                                       |
|  index.html + app.js + style.css                      |
|  - Package diagram (DIP/SSOP, QFN/QFP layouts)       |
|  - Pin assignment table with dropdowns                |
|  - Oscillator / fuse configuration panels             |
|  - Code viewer with copy/save                         |
|  - Undo/redo (snapshot-based, structuredClone)        |
+------------------------------------------------------+
           |                          ^
           | HTTP (localhost:8642)    | JSON responses
           v                          |
+------------------------------------------------------+
|                FastAPI Backend (web/app.py)            |
|                                                       |
|  GET  /api/devices         -> list cached devices     |
|  GET  /api/device/{part}   -> load & resolve pins     |
|  POST /api/codegen         -> generate C files        |
|  POST /api/compile-check   -> xc16-gcc syntax check   |
|  GET  /api/compiler        -> compiler availability   |
+------------------------------------------------------+
           |                          |
           v                          v
+---------------------+   +------------------------+
|   parser/            |   |   codegen/              |
|                      |   |                         |
|   dfp_manager.py     |   |   generate.py           |
|   edc_parser.py      |   |   oscillator.py         |
+---------------------+   |   fuses.py               |
           |               +------------------------+
           v
+---------------------+
|   Data Stores        |
|                      |
|   dfp_cache/edc/     |  Extracted .PIC XML files
|   devices/           |  Cached DeviceData JSON
|   pinouts/           |  Pinout overlay JSON
+---------------------+
```

## Module Responsibilities

### `web/app.py` -- API Layer

FastAPI application mounted at `127.0.0.1:8642`. Serves the single-page HTML frontend via Jinja2, mounts `web/static/` for JS and CSS, and exposes five REST endpoints. Converts Pydantic request models into internal dataclasses before delegating to the parser and codegen modules.

### `parser/edc_parser.py` -- EDC XML Parser

Parses Microchip `.PIC` files (EDC XML format) into the `DeviceData` model. Extracts:

- **Pads**: logical I/O pads with multiplexed functions, RP numbers, port/bit info, analog channels.
- **Pinouts**: physical pin-position-to-pad mappings per package variant.
- **PPS mappings**: RPINR (input) and RPOR (output) register fields with addresses, masks, and offsets.
- **Port registers**: TRIS, ANSEL, LAT, PORT register addresses.
- **ANSEL bits**: which port bits have analog capability.

### `parser/dfp_manager.py` -- DFP Pack Manager

Locates `.atpack` files on disk, extracts `.PIC` files from them (they are ZIP archives), caches parsed `DeviceData` as JSON in `devices/`, and merges pinout overlays from `pinouts/`.

### `codegen/generate.py` -- C Code Generator

Takes a `DeviceData` and a `PinConfig` (list of pin assignments) and produces `pin_config.h` and `pin_config.c`. Handles PPS unlock/lock, RPINR/RPOR register writes, ANSEL digital/analog selection, TRIS direction, op-amp enables, and the `system_init()` call chain.

### `codegen/oscillator.py` -- PLL Calculator

Calculates PLL divider values (N1, M, N2, N3) for dsPIC33CK devices given a target Fosc. Generates `#pragma config` lines and a `configure_oscillator()` function that programs CLKDIV, PLLFBD, and PLLDIV registers.

### `codegen/fuses.py` -- Configuration Fuse Generator

Generates `#pragma config` lines for FICD (debug pair selection, JTAG), FWDT (watchdog timer), and FBORPOR (brown-out reset) configuration registers.

### `web/static/app.js` -- Frontend

Vanilla JavaScript single-page application. No framework, no build step. State is held in global variables (`deviceData`, `assignments`, `signalNames`). Rendering is imperative DOM manipulation. Supports undo/redo via snapshot cloning.

## Request/Response Cycle

### Device Loading

```
User types "DSPIC33CK64MP102", clicks Load Device
  |
  v
GET /api/device/DSPIC33CK64MP102
  |
  v
dfp_manager.load_device("DSPIC33CK64MP102")
  |
  +-- 1. Check devices/DSPIC33CK64MP102.json (cached)
  |      If found: DeviceData.from_json() -> merge overlays -> return
  |
  +-- 2. Search for .atpack in:
  |        ~/.mchp_packs/Microchip/
  |        ~/Downloads/
  |        dfp_cache/
  |
  +-- 3. Extract edc/DSPIC33CK64MP102.PIC from .atpack (ZIP)
  |
  +-- 4. edc_parser.parse_edc_file() -> DeviceData
  |
  +-- 5. Save to devices/DSPIC33CK64MP102.json
  |
  +-- 6. Load pinout overlays from pinouts/DSPIC33CK64MP102.json
  |
  v
Response JSON:
  {
    part_number, selected_package, packages,
    pin_count, pins (resolved for package),
    remappable_inputs, remappable_outputs,
    pps_input_mappings, pps_output_mappings,
    port_registers
  }
  |
  v
Frontend renders package diagram + pin assignment table
```

### Code Generation

```
User assigns peripherals, configures oscillator/fuses, clicks Generate
  |
  v
POST /api/codegen
  Body: {
    part_number, package,
    assignments: [{pin_position, rp_number, peripheral, direction, ppsval, fixed}],
    signal_names: {"1": "UART1_TX", ...},
    digital_pins: [3, 5, ...],
    oscillator: {source, target_fosc_mhz, crystal_mhz, poscmd},
    fuses: {ics, jtagen, fwdten, wdtps, boren, borv}
  }
  |
  v
generate_c_files(device, config, package, signal_names, osc_config, fuse_config)
  |
  +-- generate_osc_code()    -> pragmas + configure_oscillator()
  +-- generate_fuse_pragmas() -> #pragma config lines
  +-- PPS input/output writes (RPINR/RPOR with unlock/lock)
  +-- ANSEL writes (analog vs digital)
  +-- TRIS writes (pin direction)
  +-- Op-amp enables (AMPxCON)
  +-- system_init() orchestrator
  |
  v
Response: {
  files: {
    "pin_config.h": "...",
    "pin_config.c": "..."
  }
}
  |
  v
Frontend displays code in tabbed viewer (pin_config.h / pin_config.c)
```

### Compile Check

```
User clicks "Compile Check"
  |
  v
POST /api/compile-check
  Body: { code, header, part_number }
  |
  v
Write pin_config.h + pin_config.c to temp directory
  |
  v
xc16-gcc -mcpu=33CK64MP102 -c -Wall -Werror -std=c99 pin_config.c
  |
  v
Response: { success: true/false, errors: "...", warnings: "..." }
```

## Data Flow Summary

```
.atpack (ZIP)
    |
    v
.PIC (EDC XML)  --->  edc_parser  --->  DeviceData  --->  devices/*.json (cache)
                                              |
                        pinouts/*.json  ------+  (overlay merge)
                                              |
                                              v
                                         API response
                                              |
                                              v
                                    Frontend (assignments)
                                              |
                                              v
                                    POST /api/codegen
                                              |
                                              v
                                  pin_config.h + pin_config.c
```
