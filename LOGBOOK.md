# config-pic — Logbook

## 2026-03-28

### ICSP Pin Highlighting
- Added `isIcspPin()` detection for MCLR, PGC1, PGD1 (factory default debug pair)
- Gold highlighting on package diagram (`.pkg-pin.icsp`) and pin table rows (`.pin-row.icsp`)
- ICSP function tags in pin table colored gold (`.func-tag.icsp`)
- MCLR opacity override (`!important`) to prevent power-pin dimming

### ICSP Code Generation Fix
- PGD1/PGC1 assignments no longer generate ANSEL/TRIS writes
- Code generator emits reservation comments: `/* RBx reserved for PGDx — no ANSEL/TRIS configuration needed */`
- Debug pins are controlled by the debug module via FICD.ICS, not user code

### Device Combo Box
- Changed part input to use `<datalist>` for native dropdown + free text
- `list_cached_devices()` now scans devices/*.json, dfp_cache/edc/*.PIC, and pinouts/*.json

### Scroll-to-Pin Fix
- Switched from `offsetTop` to `getBoundingClientRect()` for reliable scroll positioning in nested containers

### Sticky Header Fix
- Changed `border-collapse: collapse` to `border-collapse: separate; border-spacing: 0` on `.pin-table`

### Research: Microchip Ordering Convention
- Part number structure: `DSPIC33CK64MP102T-E/M6VAO`
- `T` = tape/reel, `-E`/`-I`/`-H` = temp grade, `/M6` = package, `VAO` = automotive (AEC-Q100)
- VAO parts only available through Microchip Direct (not Mouser/Digi-Key)
- Microchip Direct blocks automated HTTP access

### Project Setup
- Created CLAUDE.md, README.md, TODO.md, LOGBOOK.md
- Planned implementation of: config fuses, conflict visualization, multi-file output, system_init(), undo/redo, unit tests

### Configuration Fuse Generation (Phase 1)
- Created `codegen/fuses.py` with `FuseConfig` dataclass and `generate_fuse_pragmas()`
- Supports FICD (ICS pair 1-3, JTAG ON/OFF), FWDT (OFF/ON/SWON, prescaler), FBORPOR (BOR enable/voltage)
- Added fuse UI section in HTML with conditional show/hide (WDT prescaler hidden when WDT OFF, BOR voltage hidden when BOR OFF)
- Integrated into `generate.py`, `app.py`, and save/load workflow

### Pin Conflict Visualization (Phase 1)
- `checkConflicts()` now returns a `Set<number>` of conflicting pin positions
- Adds `.conflict` class to both `pkg-pin-*` (diagram) and `pin-row-*` (table) elements
- CSS: red border on table rows, red background + 3-pulse flash animation on diagram pins

### Multi-file Output (Phase 2)
- Created `generate_c_files()` returning `{"pin_config.h": ..., "pin_config.c": ...}`
- Header: include guard, `#include <xc.h>`, signal name `#define` macros, function prototypes
- Source: `#include "pin_config.h"`, pragmas, function implementations
- `generate_c_code()` now delegates to `generate_c_files()` and merges for backward compat (compile check)
- API returns `{"files": {...}}` instead of `{"code": "..."}`
- Frontend: tab UI (pin_config.c / pin_config.h) with active tab tracking
- Compile check sends both files; xc16-gcc gets `-I{tmpdir}` to find the header

### system_init() (Phase 3)
- Generated automatically in pin_config.c with correct call order:
  1. `configure_oscillator()` (clock must be stable first)
  2. `configure_pps()` (requires unlock/lock)
  3. `configure_ports()` (ANSEL/TRIS)
  4. `configure_analog()` (op-amp enables)
- Only includes calls for functions that are actually generated
- Prototype in pin_config.h

### Undo/Redo (Phase 4)
- Snapshot-based: `structuredClone()` of assignments + signalNames
- 50-level undo stack, separate redo stack
- Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y keyboard shortcuts
- Signal name fields push undo on focus (before typing starts)
- Assignment dropdown pushes undo before state change
- Stacks cleared on part switch

### Code Comments
- Added JSDoc-style comments to all functions in app.js
- Section headers with `=====` separators for major code regions
- Updated module docstrings in oscillator.py, generate.py, app.py
- Added stylesheet header comment explaining color conventions

### Unit Tests (Phase 4)
- tests/test_pll.py — PLL divider calculation
- tests/test_codegen.py — Code generation output, ICSP handling, system_init order, multi-file split
- tests/test_fuses.py — Fuse pragma generation

### Dynamic ICSP Highlighting
- `isIcspPin()` and `isIcspFunction()` now read the ICS fuse dropdown to determine active debug pair
- `refreshIcspHighlight()` updates pin table rows, function tags, and package diagram pins on ICS change
- `setupFuseUI()` wires the `fuse-ics` change event to trigger refresh
- MCLR always highlighted regardless of pair selection

### Export C Files
- "Export" button in toolbar downloads both `pin_config.c` and `pin_config.h` as individual files
- Styled to match Copy button (transparent background, dim text, border)

### Pin List Export
- "Export Pin List" button in summary bar downloads a formatted `{PART}_pinlist.txt`
- Clean table with Pin, Name, Function, Signal columns
- Optional grid lines (box-drawing characters) via checkbox toggle
- Header includes part number, package, and date

### Comment Alignment in Generated Code
- `_align_comments()` helper aligns inline `/* ... */` comments to a consistent column
- Applied to PPS, TRIS, ANSEL, op-amp, oscillator pragma, and fuse pragma blocks
- Each block aligns independently based on the longest statement

### Cache Busting
- Added `?v=N` query strings to `style.css` and `app.js` script tags in index.html
- Prevents browser from serving stale cached files after code changes

### Documentation (Phase 5)
- doc/architecture.md — System architecture and data flow
- doc/codegen.md — Code generator internals
- doc/device-data.md — DFP parsing and device data model
- doc/configuration.md — User guide for all config options
- doc/api.md — REST API reference
- Updated README.md with all new features (fuses, multi-file, undo/redo, system_init, conflict detection)
- Updated TODO.md — documentation marked complete
