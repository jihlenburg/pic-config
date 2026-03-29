"""
DFP Pack Manager: find, fetch, and extract Microchip Device Family Pack files.
Loads pinout overlays for alternate package variants.
"""

import os
import zipfile
import json
import re
from pathlib import Path
from typing import Optional

from parser.edc_parser import parse_edc_file, DeviceData, Pinout, Pad
from parser.pack_index import lookup_device_pack, download_atpack, list_all_devices as _list_all_index_devices

DSPIC33_FAMILIES = {
    "dsPIC33CK-MP": r"DSPIC33CK\d+MP\d+",
    "dsPIC33CK-MC": r"DSPIC33CK\d+MC\d+",
    "dsPIC33CH-MP": r"DSPIC33CH\d+MP\d+",
    "dsPIC33CD-MP": r"DSPIC33CD\d+MP\d+",
    "dsPIC33CD-MC": r"DSPIC33CD\d+MC\d+",
    "dsPIC33E-GM-GP-MC-GU-MU": r"DSPIC33E[A-Z]+\d+[A-Z]*\d+",
    "dsPIC33F-GP-MC": r"DSPIC33F[A-Z]+\d+[A-Z]*\d+",
    "dsPIC33AK-MC": r"DSPIC33AK\d+MC\d+",
    "dsPIC33AK-MP": r"DSPIC33AK\d+MP\d+",
}

BASE_DIR = Path(__file__).resolve().parent.parent
DEVICES_DIR = BASE_DIR / "devices"
DFP_CACHE_DIR = BASE_DIR / "dfp_cache"
PINOUTS_DIR = BASE_DIR / "pinouts"


def _search_paths() -> list[Path]:
    home = Path.home()
    paths = [
        home / ".mchp_packs" / "Microchip",
        home / "Downloads",
        DFP_CACHE_DIR,
    ]
    return [p for p in paths if p.exists()]


def _find_atpack_for_part(part_number: str) -> Optional[Path]:
    part_upper = part_number.upper()
    family_key = None
    for fam, pattern in DSPIC33_FAMILIES.items():
        if re.match(pattern, part_upper):
            family_key = fam
            break

    for search_dir in _search_paths():
        for atpack in search_dir.rglob("*.atpack"):
            if family_key and family_key.replace("-", "") in atpack.name.replace("-", "").replace("_", ""):
                return atpack
            if part_upper[:10].lower() in atpack.name.lower():
                return atpack

        for pic_file in search_dir.rglob("*.PIC"):
            if part_upper in pic_file.stem.upper():
                return pic_file

    return None


def _extract_pic_from_atpack(atpack_path: Path, part_number: str) -> Optional[Path]:
    part_upper = part_number.upper()
    DFP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    edc_dir = DFP_CACHE_DIR / "edc"
    edc_dir.mkdir(exist_ok=True)

    output_path = edc_dir / f"{part_upper}.PIC"
    if output_path.exists():
        return output_path

    try:
        with zipfile.ZipFile(atpack_path, "r") as zf:
            names = zf.namelist()
            match = None
            for name in names:
                if name.upper() == f"edc/{part_upper}.PIC".upper():
                    match = name
                    break
            if match is None:
                for name in names:
                    if name.endswith(".PIC") and part_upper in name.upper():
                        match = name
                        break
            if match:
                zf.extract(match, DFP_CACHE_DIR)
                extracted = DFP_CACHE_DIR / match
                if extracted != output_path:
                    extracted.rename(output_path)
                return output_path
    except (zipfile.BadZipFile, KeyError) as e:
        print(f"Error extracting from {atpack_path}: {e}")
    return None


def _load_pinout_overlays(device: DeviceData) -> None:
    """Load pinout overlay file and merge alternate packages into device data."""
    overlay_path = PINOUTS_DIR / f"{device.part_number.upper()}.json"
    if not overlay_path.exists():
        return

    overlay = json.loads(overlay_path.read_text())
    packages = overlay.get("packages", {})

    for pkg_name, pkg_data in packages.items():
        if pkg_name in device.pinouts:
            continue  # already loaded (e.g. the EDC default)
        if pkg_data.get("source") != "overlay":
            continue

        pin_map = {}
        for pos_str, pad_name in pkg_data.get("pins", {}).items():
            pin_map[int(pos_str)] = pad_name

            # Ensure the pad exists (power pads with suffixes)
            if pad_name not in device.pads:
                base = re.sub(r"_\d+$", "", pad_name)
                if base in device.pads:
                    # Create alias pad for power duplicates
                    src = device.pads[base]
                    device.pads[pad_name] = Pad(
                        name=pad_name,
                        functions=src.functions,
                        rp_number=src.rp_number,
                        port=src.port,
                        port_bit=src.port_bit,
                        analog_channels=src.analog_channels,
                        is_power=src.is_power,
                    )

        device.pinouts[pkg_name] = Pinout(
            package=pkg_name,
            pin_count=pkg_data.get("pin_count", len(pin_map)),
            source="overlay",
            pins=pin_map,
        )


def get_cached_device(part_number: str) -> Optional[DeviceData]:
    DEVICES_DIR.mkdir(exist_ok=True)
    json_path = DEVICES_DIR / f"{part_number.upper()}.json"
    if json_path.exists():
        return DeviceData.from_json(json_path.read_text())
    return None


def save_cached_device(device: DeviceData) -> Path:
    DEVICES_DIR.mkdir(exist_ok=True)
    json_path = DEVICES_DIR / f"{device.part_number.upper()}.json"
    json_path.write_text(device.to_json())
    return json_path


def list_cached_devices() -> list[str]:
    """List devices that are already cached locally (fast, no network)."""
    names: set[str] = set()
    DEVICES_DIR.mkdir(exist_ok=True)
    for p in DEVICES_DIR.glob("*.json"):
        names.add(p.stem.upper())
    edc_dir = DFP_CACHE_DIR / "edc"
    if edc_dir.is_dir():
        for p in edc_dir.glob("*.PIC"):
            names.add(p.stem.upper())
    if PINOUTS_DIR.is_dir():
        for p in PINOUTS_DIR.glob("*.json"):
            names.add(p.stem.upper())
    return sorted(names)


def list_all_known_devices() -> list[str]:
    """List all devices: locally cached + full pack index catalog."""
    local = set(list_cached_devices())
    try:
        remote = set(_list_all_index_devices())
    except Exception:
        remote = set()
    return sorted(local | remote)


def load_device(part_number: str) -> Optional[DeviceData]:
    """
    Load device data:
    1. Check local cache (devices/*.json)
    2. Find DFP atpack locally
    3. Auto-download from Microchip pack repository if needed
    4. Merge pinout overlays from pinouts/ directory
    """
    part_upper = part_number.upper()

    # 1. Check cache
    cached = get_cached_device(part_upper)
    if cached:
        _load_pinout_overlays(cached)
        return cached

    # 2. Find and parse from DFP (local search first)
    found = _find_atpack_for_part(part_upper)

    # 3. Auto-download from Microchip pack repository if not found locally
    if found is None:
        pack_info = lookup_device_pack(part_upper)
        if pack_info:
            url, filename = pack_info
            try:
                found = download_atpack(url, filename)
            except Exception as e:
                print(f"Failed to download DFP for {part_upper}: {e}")
                return None
        else:
            return None

    pic_path = None
    if found.suffix == ".PIC":
        pic_path = found
    elif found.suffix == ".atpack":
        pic_path = _extract_pic_from_atpack(found, part_upper)

    if pic_path is None or not pic_path.exists():
        return None

    device = parse_edc_file(str(pic_path))
    save_cached_device(device)

    # 4. Load overlays
    _load_pinout_overlays(device)

    return device


if __name__ == "__main__":
    import sys
    part = sys.argv[1] if len(sys.argv) > 1 else "DSPIC33CK64MP102"
    device = load_device(part)
    if device:
        print(f"Loaded {device.part_number}")
        for name, po in device.pinouts.items():
            print(f"  Package: {name} ({po.pin_count} pins, source={po.source})")
    else:
        print(f"Device {part} not found")
