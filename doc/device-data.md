# Device Data

This document describes how device data flows through config-pic: from Microchip DFP files on disk, through the EDC XML parser, into the `DeviceData` model, and out to the API.

## DFP .atpack Files

Microchip distributes device support data in Device Family Packs (DFPs). Each DFP is a `.atpack` file, which is a standard ZIP archive. Inside, the `edc/` directory contains one `.PIC` file per device (e.g., `edc/DSPIC33CK64MP102.PIC`). These `.PIC` files are XML documents in Microchip's EDC (Electronic Data Capture) schema.

### Search Paths

`dfp_manager.py` searches these directories for `.atpack` files (in order):

1. `~/.mchp_packs/Microchip/` -- Microchip's standard pack install location
2. `~/Downloads/` -- common download location
3. `dfp_cache/` -- project-local directory

### Family Detection

The manager maps part numbers to DFP families using regex patterns:

```python
DSPIC33_FAMILIES = {
    "dsPIC33CK-MP": r"DSPIC33CK\d+MP\d+",
    "dsPIC33CK-MC": r"DSPIC33CK\d+MC\d+",
    "dsPIC33CH-MP": r"DSPIC33CH\d+MP\d+",
    "dsPIC33CD-MP": r"DSPIC33CD\d+MP\d+",
    "dsPIC33CD-MC": r"DSPIC33CD\d+MC\d+",
    "dsPIC33AK-MC": r"DSPIC33AK\d+MC\d+",
    "dsPIC33AK-MP": r"DSPIC33AK\d+MP\d+",
    ...
}
```

Supported families: dsPIC33CK, dsPIC33CH, dsPIC33CD, dsPIC33AK, dsPIC33E, and dsPIC33F.

## EDC XML Structure

The `.PIC` files use the namespace `http://crownking/edc`. The parser extracts data from two main sections.

### PinList Section

Contains `Pin` and `RemappablePin` elements.

**Pin elements** represent physical pins. Each has nested `VirtualPin` children listing multiplexed functions:

```xml
<edc:Pin>
    <edc:VirtualPin edc:name="RB5"/>
    <edc:VirtualPin edc:name="RP37"/>
    <edc:VirtualPin edc:name="AN5"/>
</edc:Pin>
```

Pin position is determined by sequential order in the PinList. The parser derives:

- **Canonical pad name**: prefers GPIO names (`RA0`--`RE15`) over RP names.
- **Port/bit**: extracted from names matching `R[A-E]\d+`.
- **RP number**: extracted from names matching `RP\d+`.
- **Analog channels**: names starting with `AN` followed by digits.
- **Power status**: VDD, VSS, AVDD, AVSS, MCLR pins flagged as power.

**RemappablePin elements** list available PPS peripherals:

```xml
<edc:RemappablePin edc:direction="out">
    <edc:VirtualPin edc:name="U1TX" edc:ppsval="1"/>
</edc:RemappablePin>
```

### SFRDataSector Section

Contains `SFRDef` elements for Special Function Registers. The parser extracts:

- **RPINR registers**: PPS input mapping registers. Each field (`SFRFieldDef`) maps a peripheral input to an RP pin number.
- **RPOR registers**: PPS output mapping registers. Each field maps an RP pin to a peripheral output function.
- **Port registers**: TRIS, ANSEL, LAT, PORT register addresses (matched by `(TRIS|ANSEL|LAT|PORT)[A-Z]$`).
- **ANSEL bit fields**: for each ANSELx register, the parser identifies which bit positions exist, establishing which port pins have analog capability.

## DeviceData Model

All parsed information is collected into a `DeviceData` dataclass:

```python
@dataclass
class DeviceData:
    part_number: str
    pads: dict[str, Pad]                     # pad_name -> Pad
    pinouts: dict[str, Pinout]               # package_name -> Pinout
    default_pinout: str                      # name of the default package
    remappable_inputs: list[RemappablePeripheral]
    remappable_outputs: list[RemappablePeripheral]
    pps_input_mappings: list[PPSInputMapping]
    pps_output_mappings: list[PPSOutputMapping]
    port_registers: dict[str, int]           # e.g. {"TRISA": 0x02C0, ...}
    ansel_bits: dict[str, list[int]]         # e.g. {"A": [0,1,2,3,4], "B": [0,1,...]}
```

### Key Dataclasses

**Pad** -- A logical I/O pad with its multiplexed functions:

```python
@dataclass
class Pad:
    name: str                  # "RB5", "AVDD", "MCLR"
    functions: list[str]       # ["RB5", "RP37", "AN5"]
    rp_number: int | None      # 37
    port: str | None           # "B"
    port_bit: int | None       # 5
    analog_channels: list[str] # ["AN5"]
    is_power: bool             # False
```

**Pinout** -- Maps physical pin positions to pad names for one package variant:

```python
@dataclass
class Pinout:
    package: str               # "28-pin SSOP"
    pin_count: int             # 28
    source: str                # "edc" or "overlay"
    pins: dict[int, str]       # {1: "MCLR", 2: "RA0", 3: "RA1", ...}
```

**PPSInputMapping** / **PPSOutputMapping** -- Register-level PPS mapping info:

```python
@dataclass
class PPSInputMapping:
    peripheral: str       # "U1RXR"
    register: str         # "RPINR18"
    register_addr: int    # 0x07A4
    field_name: str       # "U1RXR"
    field_mask: int       # 0x3F
    field_offset: int     # 0

@dataclass
class PPSOutputMapping:
    rp_number: int        # 37
    register: str         # "RPOR2"
    register_addr: int    # 0x07CC
    field_name: str       # "RP37R"
    field_mask: int       # 0x3F
    field_offset: int     # 0
```

### resolve_pins(package)

The `resolve_pins()` method on `DeviceData` is the primary way to get a flat list of pins for a given package. It iterates through the selected pinout's position-to-pad mapping and enriches each entry with full pad data (functions, RP number, port info, analog channels, power status).

For duplicate power pins (e.g., multiple VSS), the method strips the `_\d+` suffix to find the base pad.

## Pinout Overlays

EDC files typically contain only one package pinout. Alternate packages (e.g., UQFN vs SSOP) are provided via JSON overlay files in `pinouts/`.

### Overlay File Format

```json
{
  "part_number": "DSPIC33CK64MP102",
  "datasheet": "DS70005363E",
  "packages": {
    "28-pin SSOP": {
      "source": "edc",
      "pin_count": 28,
      "note": "Default pinout from DFP EDC file"
    },
    "28-pin UQFN": {
      "source": "overlay",
      "pin_count": 28,
      "note": "From datasheet DS70005363E Table 3",
      "pins": {
        "1":  "RB14",
        "2":  "RB15",
        "3":  "MCLR",
        ...
      }
    }
  }
}
```

- Entries with `"source": "edc"` are informational only (the EDC parser already loaded them).
- Entries with `"source": "overlay"` are merged into `DeviceData.pinouts` by `_load_pinout_overlays()`.
- Pin values reference existing pad names. For duplicate power pins (e.g., `VSS_2`), alias pads are created automatically.

Overlay files are stored at `pinouts/{PART_NUMBER}.json` (uppercase).

## Caching Strategy

```
First load of DSPIC33CK64MP102:
    1. No devices/DSPIC33CK64MP102.json found
    2. Search .atpack files in search paths
    3. Extract edc/DSPIC33CK64MP102.PIC to dfp_cache/edc/
    4. Parse EDC XML -> DeviceData
    5. Serialize to devices/DSPIC33CK64MP102.json
    6. Merge pinout overlays from pinouts/DSPIC33CK64MP102.json

Subsequent loads:
    1. Load devices/DSPIC33CK64MP102.json -> DeviceData.from_json()
    2. Merge pinout overlays (always re-applied, not cached)
    3. Return immediately
```

Key points:

- The JSON cache in `devices/` stores the full `DeviceData` model (pads, pinouts, PPS mappings, registers, ANSEL bits).
- Pinout overlays are always re-merged on load, so overlay file edits take effect immediately without clearing the cache.
- Extracted `.PIC` files are kept in `dfp_cache/edc/` to avoid re-extracting from the `.atpack` archive.
- The `list_cached_devices()` function aggregates device names from all three sources: `devices/*.json`, `dfp_cache/edc/*.PIC`, and `pinouts/*.json`.

## Device List API

`GET /api/devices` returns a sorted list of all known device part numbers by scanning:

- `devices/*.json` file stems
- `dfp_cache/edc/*.PIC` file stems
- `pinouts/*.json` file stems

This allows the frontend to show available devices even before they have been fully parsed.
