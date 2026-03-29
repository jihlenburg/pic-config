"""
FastAPI web application for the config-pic pin configurator.

Serves the single-page frontend and provides REST API endpoints for:
  - Device data loading and resolution (/api/device/{part})
  - C code generation (/api/codegen)
  - XC16 compiler syntax checking (/api/compile-check)
  - Available device listing (/api/devices)
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from parser.dfp_manager import load_device, list_cached_devices, list_all_known_devices
from parser.pack_index import get_pack_index
from parser.pinout_verifier import verify_pinout, save_overlay, _get_api_key
from codegen.generate import generate_c_code, generate_c_files, PinConfig, PinAssignment
from codegen.oscillator import OscConfig
from codegen.fuses import FuseConfig

# Locate xc16-gcc at startup
_XC16_GCC = shutil.which("xc16-gcc")
if not _XC16_GCC:
    # Check common Microchip install paths
    for candidate in [
        "/Applications/microchip/xc16/v2.10/bin/xc16-gcc",
        "/opt/microchip/xc16/v2.10/bin/xc16-gcc",
    ]:
        if Path(candidate).is_file():
            _XC16_GCC = candidate
            break

app = FastAPI(title="config-pic", docs_url="/api/docs")

WEB_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    return (WEB_DIR / "templates" / "index.html").read_text()


@app.get("/api/devices")
async def api_list_devices():
    """List all known devices (cached + pack index catalog)."""
    cached = set(list_cached_devices())
    all_devs = list_all_known_devices()
    return {
        "devices": all_devs,
        "cached": sorted(cached),
        "total": len(all_devs),
        "cached_count": len(cached),
    }


@app.post("/api/refresh-index")
async def api_refresh_index():
    """Force-refresh the pack index from Microchip servers."""
    try:
        index = get_pack_index(force_refresh=True)
        return {
            "success": True,
            "device_count": len(index.devices),
            "pack_count": len(index.packs),
            "age_hours": round(index.age_hours, 1),
        }
    except Exception as e:
        raise HTTPException(502, f"Failed to refresh pack index: {e}")


@app.get("/api/index-status")
async def api_index_status():
    """Return the current pack index status without fetching."""
    try:
        index = get_pack_index()
        return {
            "available": True,
            "device_count": len(index.devices),
            "pack_count": len(index.packs),
            "age_hours": round(index.age_hours, 1),
            "is_stale": index.is_stale,
        }
    except Exception:
        return {
            "available": False,
            "device_count": 0,
            "pack_count": 0,
            "age_hours": None,
            "is_stale": True,
        }


@app.get("/api/device/{part_number}")
async def api_get_device(part_number: str, package: str | None = None):
    """Load device data. Returns pad info, available packages, and resolved pins for the selected package."""
    device = load_device(part_number)
    if device is None:
        raise HTTPException(404, f"Device {part_number} not found")

    # Build response with resolved pins for the requested package
    selected_pkg = package or device.default_pinout
    if selected_pkg not in device.pinouts:
        selected_pkg = device.default_pinout

    resolved_pins = device.resolve_pins(selected_pkg)
    pinout = device.get_pinout(selected_pkg)

    return {
        "part_number": device.part_number,
        "selected_package": selected_pkg,
        "packages": {
            name: {"pin_count": po.pin_count, "source": po.source}
            for name, po in device.pinouts.items()
        },
        "pin_count": pinout.pin_count,
        "pins": resolved_pins,
        "remappable_inputs": [
            {"name": r.name, "direction": r.direction, "ppsval": r.ppsval}
            for r in device.remappable_inputs
        ],
        "remappable_outputs": [
            {"name": r.name, "direction": r.direction, "ppsval": r.ppsval}
            for r in device.remappable_outputs
        ],
        "pps_input_mappings": [
            {"peripheral": m.peripheral, "register": m.register,
             "register_addr": m.register_addr, "field_name": m.field_name,
             "field_mask": m.field_mask, "field_offset": m.field_offset}
            for m in device.pps_input_mappings
        ],
        "pps_output_mappings": [
            {"rp_number": m.rp_number, "register": m.register,
             "register_addr": m.register_addr, "field_name": m.field_name,
             "field_mask": m.field_mask, "field_offset": m.field_offset}
            for m in device.pps_output_mappings
        ],
        "port_registers": device.port_registers,
    }


class AssignmentRequest(BaseModel):
    pin_position: int
    rp_number: int | None = None
    peripheral: str
    direction: str
    ppsval: int | None = None
    fixed: bool = False


class OscRequest(BaseModel):
    source: str = ""          # "frc", "frc_pll", "pri", "pri_pll", "lprc", or "" for none
    target_fosc_mhz: float = 0.0
    crystal_mhz: float = 0.0
    poscmd: str = "EC"


class FuseRequest(BaseModel):
    ics: int = 1
    jtagen: str = "OFF"
    fwdten: str = "OFF"
    wdtps: str = "PS1024"
    boren: str = "ON"
    borv: str = "BOR_HIGH"


class CodegenRequest(BaseModel):
    part_number: str
    package: str | None = None
    assignments: list[AssignmentRequest]
    signal_names: dict[str, str] = {}  # pin_position (as string) -> name
    digital_pins: list[int] = []
    oscillator: OscRequest | None = None
    fuses: FuseRequest | None = None


@app.post("/api/codegen")
async def api_codegen(req: CodegenRequest):
    device = load_device(req.part_number)
    if device is None:
        raise HTTPException(404, f"Device {req.part_number} not found")

    pkg_name = req.package or device.default_pinout

    config = PinConfig(
        part_number=req.part_number,
        assignments=[
            PinAssignment(
                pin_position=a.pin_position,
                rp_number=a.rp_number,
                peripheral=a.peripheral,
                direction=a.direction,
                ppsval=a.ppsval,
                fixed=a.fixed,
            )
            for a in req.assignments
        ],
        digital_pins=req.digital_pins,
    )

    # Convert string keys to int
    sig_names = {int(k): v for k, v in req.signal_names.items()}

    # Build oscillator config if provided
    osc = None
    if req.oscillator and req.oscillator.source:
        osc = OscConfig(
            source=req.oscillator.source,
            target_fosc_hz=int(req.oscillator.target_fosc_mhz * 1_000_000),
            crystal_hz=int(req.oscillator.crystal_mhz * 1_000_000),
            poscmd=req.oscillator.poscmd,
        )

    # Build fuse config if provided
    fuse = None
    if req.fuses:
        fuse = FuseConfig(
            ics=req.fuses.ics,
            jtagen=req.fuses.jtagen,
            fwdten=req.fuses.fwdten,
            wdtps=req.fuses.wdtps,
            boren=req.fuses.boren,
            borv=req.fuses.borv,
        )

    files = generate_c_files(device, config, pkg_name, sig_names, osc, fuse)
    return {"files": files}


def _part_to_mcpu(part_number: str) -> str:
    """Convert our part number format to xc16-gcc -mcpu= value.
    e.g. DSPIC33CK64MP102 -> 33CK64MP102"""
    p = part_number.upper()
    if p.startswith("DSPIC"):
        return p[5:]   # strip "DSPIC" -> "33CK64MP102"
    if p.startswith("PIC"):
        return p[3:]
    return p


@app.get("/api/compiler")
async def api_compiler_info():
    """Return XC16 compiler availability and version."""
    if not _XC16_GCC:
        return {"available": False, "path": None, "version": None}
    try:
        result = subprocess.run(
            [_XC16_GCC, "--version"],
            capture_output=True, text=True, timeout=5,
        )
        version_line = result.stdout.splitlines()[0] if result.stdout else "unknown"
    except Exception:
        version_line = "unknown"
    return {"available": True, "path": _XC16_GCC, "version": version_line}


class CompileCheckRequest(BaseModel):
    code: str
    header: str = ""
    part_number: str


@app.post("/api/compile-check")
async def api_compile_check(req: CompileCheckRequest):
    """Compile the generated C code with xc16-gcc and return diagnostics."""
    if not _XC16_GCC:
        raise HTTPException(503, "XC16 compiler not found on this system")

    mcpu = _part_to_mcpu(req.part_number)

    with tempfile.TemporaryDirectory(prefix="config_pic_") as tmpdir:
        # Write header if provided (multi-file mode)
        if req.header:
            hdr = Path(tmpdir) / "pin_config.h"
            hdr.write_text(req.header)

        src = Path(tmpdir) / "pin_config.c"
        src.write_text(req.code)

        try:
            result = subprocess.run(
                [
                    _XC16_GCC,
                    f"-mcpu={mcpu}",
                    "-c",              # compile only, no link
                    f"-I{tmpdir}",     # find pin_config.h in temp dir
                    "-Wall",
                    "-Werror",
                    "-std=c99",
                    "-o", str(Path(tmpdir) / "pin_config.o"),
                    str(src),
                ],
                capture_output=True, text=True, timeout=15,
            )
        except subprocess.TimeoutExpired:
            return {"success": False, "errors": "Compiler timed out", "warnings": ""}

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode == 0:
            return {
                "success": True,
                "errors": "",
                "warnings": stderr if stderr else "",
            }
        else:
            return {
                "success": False,
                "errors": stderr if stderr else stdout,
                "warnings": "",
            }


# =============================================================================
# Pinout Verification (Claude API)
# =============================================================================

@app.post("/api/verify-pinout")
async def api_verify_pinout(
    pdf: UploadFile = File(...),
    part_number: str = Form(...),
    package: str = Form(None),
    api_key: str = Form(None),
):
    """
    Verify pinout data against a datasheet PDF using Claude.

    Accepts a multipart form with the PDF file, part number, and optional API key.
    Returns structured diff with proposed corrections.
    """
    # Resolve API key: form param > .env > error
    key = api_key if api_key else _get_api_key()
    if not key:
        raise HTTPException(
            400,
            "No API key configured. Set ANTHROPIC_API_KEY in .env or provide via settings.",
        )

    # Load current device data
    device = load_device(part_number)
    if device is None:
        raise HTTPException(404, f"Device {part_number} not found")

    pkg_name = package or device.default_pinout
    resolved_pins = device.resolve_pins(pkg_name)
    pinout = device.get_pinout(pkg_name)

    device_dict = {
        "part_number": device.part_number,
        "selected_package": pkg_name,
        "packages": {
            name: {"pin_count": po.pin_count, "source": po.source}
            for name, po in device.pinouts.items()
        },
        "pin_count": pinout.pin_count,
        "pins": resolved_pins,
    }

    # Read PDF
    pdf_bytes = await pdf.read()
    if len(pdf_bytes) < 1000:
        raise HTTPException(400, "PDF file appears too small or empty")

    try:
        result = verify_pinout(pdf_bytes, device_dict, api_key=key)
        return result.to_dict()
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    except Exception as e:
        raise HTTPException(500, f"Verification failed: {e}")


class ApplyOverlayRequest(BaseModel):
    part_number: str
    packages: dict  # package_name -> {pin_count, pins: {pos: pad}}


@app.post("/api/apply-overlay")
async def api_apply_overlay(req: ApplyOverlayRequest):
    """Save verified pinout corrections as an overlay JSON file."""
    from parser.pinout_verifier import VerifyResult, PackageResult

    # Build a VerifyResult from the request data
    vr = VerifyResult(part_number=req.part_number)
    for pkg_name, pkg_data in req.packages.items():
        pins = {}
        for pos_str, pad in pkg_data.get("pins", {}).items():
            try:
                pins[int(pos_str)] = pad
            except (ValueError, TypeError):
                continue
        vr.packages[pkg_name] = PackageResult(
            package_name=pkg_name,
            pin_count=pkg_data.get("pin_count", len(pins)),
            pins=pins,
            pin_functions=pkg_data.get("pin_functions", {}),
        )

    path = save_overlay(req.part_number, vr)
    return {"success": True, "path": str(path)}


@app.get("/api/api-key-status")
async def api_key_status():
    """Check if an API key is configured (without revealing it)."""
    key = _get_api_key()
    if key:
        # Show just the last 4 characters
        masked = "..." + key[-4:]
        return {"configured": True, "hint": masked}
    return {"configured": False, "hint": None}
