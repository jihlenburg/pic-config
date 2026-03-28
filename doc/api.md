# REST API Reference

All endpoints are served by FastAPI at `http://127.0.0.1:8642`. Interactive Swagger documentation is available at `/api/docs` when the server is running.

---

## GET /api/devices

List all known device part numbers.

### Response

```json
{
  "devices": ["DSPIC33CK32MP102", "DSPIC33CK64MP102", "DSPIC33CK64MP105"]
}
```

The list is aggregated from three sources:

- `devices/*.json` (cached device data)
- `dfp_cache/edc/*.PIC` (extracted EDC files)
- `pinouts/*.json` (pinout overlay files)

Results are sorted alphabetically and uppercased.

---

## GET /api/device/{part_number}

Load device data for a specific part number. Parses the DFP if not cached, resolves pins for the selected package, and merges pinout overlays.

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `part_number` | string | Device part number (case-insensitive), e.g., `DSPIC33CK64MP102` |

### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `package` | string | No | Package variant name (e.g., `28-pin UQFN`). Defaults to the EDC default pinout. |

### Response (200)

```json
{
  "part_number": "DSPIC33CK64MP102",
  "selected_package": "28-pin SSOP",
  "packages": {
    "28-pin SSOP": {"pin_count": 28, "source": "edc"},
    "28-pin UQFN": {"pin_count": 28, "source": "overlay"}
  },
  "pin_count": 28,
  "pins": [
    {
      "position": 1,
      "pad_name": "MCLR",
      "functions": ["MCLR"],
      "rp_number": null,
      "port": null,
      "port_bit": null,
      "analog_channels": [],
      "is_power": true
    },
    {
      "position": 2,
      "pad_name": "RA0",
      "functions": ["RA0", "RP16", "ANA0"],
      "rp_number": 16,
      "port": "A",
      "port_bit": 0,
      "analog_channels": ["ANA0"],
      "is_power": false
    }
  ],
  "remappable_inputs": [
    {"name": "U1RX", "direction": "in", "ppsval": null}
  ],
  "remappable_outputs": [
    {"name": "U1TX", "direction": "out", "ppsval": 1}
  ],
  "pps_input_mappings": [
    {
      "peripheral": "U1RXR",
      "register": "RPINR18",
      "register_addr": 1956,
      "field_name": "U1RXR",
      "field_mask": 63,
      "field_offset": 0
    }
  ],
  "pps_output_mappings": [
    {
      "rp_number": 32,
      "register": "RPOR0",
      "register_addr": 1992,
      "field_name": "RP32R",
      "field_mask": 63,
      "field_offset": 0
    }
  ],
  "port_registers": {
    "TRISA": 704,
    "PORTA": 708,
    "LATA": 712,
    "ANSELA": 716,
    "TRISB": 720,
    "PORTB": 724,
    "LATB": 728,
    "ANSELB": 732
  }
}
```

### Pin Object Fields

| Field | Type | Description |
|-------|------|-------------|
| `position` | int | Physical pin number on the package |
| `pad_name` | string | Canonical pad name (e.g., `RB5`, `MCLR`, `VDD`) |
| `functions` | array | All multiplexed function names for this pad |
| `rp_number` | int or null | Remappable pin number (null if not PPS-capable) |
| `port` | string or null | Port letter (e.g., `"A"`, `"B"`) or null for power/special |
| `port_bit` | int or null | Port bit number (e.g., `5` for RB5) |
| `analog_channels` | array | ADC channel names (e.g., `["AN5"]`) |
| `is_power` | bool | True for VDD, VSS, AVDD, AVSS, MCLR |

### Error (404)

```json
{"detail": "Device DSPIC33XX99XX99 not found"}
```

Returned when the part number does not match any cached device or discoverable DFP file.

---

## POST /api/codegen

Generate C initialization code from pin assignments and configuration settings.

### Request Body

```json
{
  "part_number": "DSPIC33CK64MP102",
  "package": "28-pin SSOP",
  "assignments": [
    {
      "pin_position": 5,
      "rp_number": 37,
      "peripheral": "U1TX",
      "direction": "out",
      "ppsval": 1,
      "fixed": false
    },
    {
      "pin_position": 6,
      "rp_number": 38,
      "peripheral": "U1RX",
      "direction": "in",
      "ppsval": null,
      "fixed": false
    },
    {
      "pin_position": 10,
      "rp_number": null,
      "peripheral": "AN0",
      "direction": "in",
      "ppsval": null,
      "fixed": true
    }
  ],
  "signal_names": {
    "5": "UART1_TX",
    "6": "UART1_RX"
  },
  "digital_pins": [3, 4],
  "oscillator": {
    "source": "frc_pll",
    "target_fosc_mhz": 200.0,
    "crystal_mhz": 0.0,
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

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `part_number` | string | Yes | Device part number |
| `package` | string | No | Package variant name (defaults to device default) |
| `assignments` | array | Yes | List of pin-to-peripheral assignments |
| `signal_names` | object | No | Map of pin position (string key) to user-defined signal name |
| `digital_pins` | array | No | Additional pin positions to force to digital mode |
| `oscillator` | object | No | Oscillator configuration (omit or set source to `""` for none) |
| `fuses` | object | No | Configuration fuse settings |

#### Assignment Object

| Field | Type | Description |
|-------|------|-------------|
| `pin_position` | int | Physical pin number on the package |
| `rp_number` | int or null | RP number for PPS-remappable pins |
| `peripheral` | string | Peripheral name (e.g., `U1TX`, `AN0`, `OA1OUT`) |
| `direction` | string | `"in"`, `"out"`, or `"io"` |
| `ppsval` | int or null | PPS output function value (for output mappings only) |
| `fixed` | bool | `true` for fixed-function peripherals, `false` for PPS-remappable |

#### Oscillator Object

| Field | Type | Description |
|-------|------|-------------|
| `source` | string | `"frc"`, `"frc_pll"`, `"pri"`, `"pri_pll"`, `"lprc"`, or `""` |
| `target_fosc_mhz` | float | Target system clock in MHz (for PLL modes) |
| `crystal_mhz` | float | External crystal frequency in MHz (for primary modes) |
| `poscmd` | string | Primary oscillator mode: `"EC"`, `"XT"`, `"HS"`, or `"NONE"` |

#### Fuses Object

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `ics` | int | 1 | ICSP debug pair: 1, 2, or 3 |
| `jtagen` | string | `"OFF"` | JTAG enable: `"ON"` or `"OFF"` |
| `fwdten` | string | `"OFF"` | Watchdog enable: `"OFF"`, `"ON"`, or `"SWON"` |
| `wdtps` | string | `"PS1024"` | Watchdog prescaler: `"PS1"` through `"PS32768"` |
| `boren` | string | `"ON"` | Brown-out reset: `"ON"` or `"OFF"` |
| `borv` | string | `"BOR_HIGH"` | Brown-out voltage: `"BOR_LOW"`, `"BOR_MID"`, or `"BOR_HIGH"` |

### Response (200)

```json
{
  "files": {
    "pin_config.h": "/**\n * @file   pin_config.h\n * @brief  ...\n */\n...",
    "pin_config.c": "/**\n * @file   pin_config.c\n * @brief  ...\n */\n..."
  }
}
```

The `files` object contains two keys:

- **`pin_config.h`** -- Include guard, `#include <xc.h>`, signal name `#define` macros, function prototypes.
- **`pin_config.c`** -- `#include "pin_config.h"`, `#pragma config` lines for oscillator and fuses, function implementations (`configure_oscillator`, `configure_pps`, `configure_ports`, `configure_analog`), and the `system_init()` master initializer.

### Error (404)

Returned when the specified part number is not found.

---

## POST /api/compile-check

Compile the generated C code with the Microchip XC16 compiler and return diagnostics. Requires `xc16-gcc` to be installed on the host system.

### Request Body

```json
{
  "code": "/* pin_config.c contents */",
  "header": "/* pin_config.h contents */",
  "part_number": "DSPIC33CK64MP102"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `code` | string | Yes | Contents of `pin_config.c` |
| `header` | string | No | Contents of `pin_config.h` (written to temp dir alongside the source) |
| `part_number` | string | Yes | Used to derive the `-mcpu=` compiler flag |

### Part Number to mcpu Conversion

The part number is converted by stripping the `DSPIC` or `PIC` prefix:

- `DSPIC33CK64MP102` becomes `33CK64MP102`
- `PIC24FJ256GA705` becomes `24FJ256GA705`

### Compiler Invocation

```
xc16-gcc -mcpu=33CK64MP102 -c -I<tmpdir> -Wall -Werror -std=c99 -o pin_config.o pin_config.c
```

The code is compiled only (`-c`), not linked. Both header and source are written to a temporary directory. The compile has a 15-second timeout.

### Response (200) -- Success

```json
{
  "success": true,
  "errors": "",
  "warnings": ""
}
```

Warnings (if any with `-Wall`) appear in the `warnings` field when compilation succeeds.

### Response (200) -- Failure

```json
{
  "success": false,
  "errors": "pin_config.c:42: error: 'RPINR99' undeclared ...",
  "warnings": ""
}
```

### Error (503)

```json
{"detail": "XC16 compiler not found on this system"}
```

Returned when `xc16-gcc` is not found in `PATH` or in the standard Microchip install directories:

- macOS: `/Applications/microchip/xc16/v2.10/bin/xc16-gcc`
- Linux: `/opt/microchip/xc16/v2.10/bin/xc16-gcc`

---

## GET /api/compiler

Check whether the XC16 compiler is available and return its version string.

### Response -- Compiler Found

```json
{
  "available": true,
  "path": "/Applications/microchip/xc16/v2.10/bin/xc16-gcc",
  "version": "xc16-gcc (Microchip XC16 Compiler) v2.10"
}
```

### Response -- Compiler Not Found

```json
{
  "available": false,
  "path": null,
  "version": null
}
```

The compiler path is resolved once at application startup using `shutil.which("xc16-gcc")`, then checked against known install paths as a fallback.

---

## Static Routes

### GET /

Serves the single-page HTML frontend from `web/templates/index.html`. Returns `text/html`.

### /static/*

Static assets served from `web/static/`:

| Path | Description |
|------|-------------|
| `/static/app.js` | Frontend application (vanilla JS, no framework) |
| `/static/style.css` | Dark theme stylesheet |
| `/static/pin_descriptions.js` | Peripheral description tooltip data |
