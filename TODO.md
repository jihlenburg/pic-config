# config-pic — TODO

## Done (Phase 5)
- [x] **Documentation** — Architecture, codegen, device data, configuration, and API docs under /doc

## Phase 1 — Done
- [x] **Config fuse generation** — FICD (ICS pair, JTAG), FWDT (watchdog), FBORPOR (brown-out/POR) pragma generation with UI controls
- [x] **Pin conflict visualization** — highlight conflicting pins red on the package diagram (flash animation) and pin table rows

## Phase 2 — Done
- [x] **Multi-file output** — split generated code into `pin_config.h` (defines, prototypes) and `pin_config.c` (implementation) with tab UI to switch

## Phase 3 — Done
- [x] **system_init() function** — generate master init that calls oscillator/pps/ports/analog in correct order

## Phase 4 — Done
- [x] **Undo/redo** — Ctrl+Z / Ctrl+Shift+Z for pin assignments and signal names (snapshot-based, 50 levels)
- [x] **Unit tests** — pytest tests for PLL calculation, codegen output, fuse generation, ICSP pin detection

## Backlog
- [ ] Peripheral-centric view (select peripherals needed, auto-suggest pin placement)
- [ ] DFP auto-download from Microchip pack repository
- [ ] Interrupt vector stub generation for assigned peripherals
- [ ] Cross-reference between packages (gain/lose pins when switching)
- [ ] Proper device database (SQLite) for indexed queries
- [ ] Server-side validation layer for assignments
- [ ] Dark/light theme toggle

## Done (recent)
- [x] Dynamic ICSP highlighting — gold highlight follows ICS fuse pair selection (1/2/3)
- [x] Export C files — download generated pin_config.c and pin_config.h
- [x] Pin list export — formatted plain text pin assignment table for documentation
- [x] Comment alignment — inline comments in generated C code aligned to consistent columns

## Done (earlier work)
- [x] ICSP pin highlighting (MCLR, PGC1, PGD1) on package diagram and pin table
- [x] ICSP pins excluded from ANSEL/TRIS code generation (reservation comment only)
- [x] Sticky header fix for pin table
- [x] Scroll-to-pin from package diagram click
- [x] Device combo box (datalist) with all known devices
- [x] Pinout overlay support for alternate packages
- [x] Oscillator/PLL configuration and pragma generation
- [x] XC16 compile check integration
- [x] Save/load configuration as JSON
- [x] QFN/QFP package diagram rendering
