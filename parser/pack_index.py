"""
Pack Index Manager: fetch, parse, and cache the Microchip pack repository index.

Provides a device→pack mapping so the DFP manager can auto-download
.atpack files on demand. The index is cached locally and refreshed
when stale (default: 7 days).
"""

import json
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
INDEX_CACHE_DIR = BASE_DIR / "dfp_cache"
INDEX_CACHE_FILE = INDEX_CACHE_DIR / "pack_index.json"
INDEX_URL = "https://packs.download.microchip.com/index.idx"
PACK_BASE_URL = "https://packs.download.microchip.com/"

STALE_SECONDS = 7 * 24 * 3600  # 7 days

# Only include dsPIC33 and PIC24 packs (16-bit focus)
_RELEVANT_PREFIXES = ("dsPIC33", "PIC24")

ATMEL_NS = "http://packs.download.atmel.com/pack-idx-atmel-extension"


@dataclass
class PackInfo:
    """Metadata for a single DFP pack."""
    name: str           # e.g. "dsPIC33CK-MP_DFP"
    version: str        # e.g. "1.15.423"
    pdsc_name: str      # e.g. "Microchip.dsPIC33CK-MP_DFP.pdsc"

    @property
    def atpack_url(self) -> str:
        return f"{PACK_BASE_URL}Microchip.{self.name}.{self.version}.atpack"

    @property
    def atpack_filename(self) -> str:
        return f"Microchip.{self.name}.{self.version}.atpack"


@dataclass
class DeviceEntry:
    """A device found in the pack index."""
    name: str           # e.g. "dsPIC33CK64MP102"
    family: str         # e.g. "dsPIC33CK-MP"
    pack_name: str      # e.g. "dsPIC33CK-MP_DFP"
    pack_version: str   # e.g. "1.15.423"


@dataclass
class PackIndex:
    """Cached pack index with device→pack mapping."""
    fetched_at: float = 0.0
    packs: dict[str, PackInfo] = field(default_factory=dict)
    devices: dict[str, DeviceEntry] = field(default_factory=dict)

    @property
    def is_stale(self) -> bool:
        if self.fetched_at == 0:
            return True
        return (time.time() - self.fetched_at) > STALE_SECONDS

    @property
    def age_hours(self) -> float:
        if self.fetched_at == 0:
            return float("inf")
        return (time.time() - self.fetched_at) / 3600

    def to_json(self) -> str:
        data = {
            "fetched_at": self.fetched_at,
            "packs": {k: asdict(v) for k, v in self.packs.items()},
            "devices": {k: asdict(v) for k, v in self.devices.items()},
        }
        return json.dumps(data, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "PackIndex":
        data = json.loads(text)
        packs = {
            k: PackInfo(**v) for k, v in data.get("packs", {}).items()
        }
        devices = {
            k: DeviceEntry(**v) for k, v in data.get("devices", {}).items()
        }
        return cls(
            fetched_at=data.get("fetched_at", 0.0),
            packs=packs,
            devices=devices,
        )


def _fetch_index_xml() -> bytes:
    """Download the pack index from Microchip."""
    req = urllib.request.Request(INDEX_URL, headers={
        "User-Agent": "config-pic/0.5 (pin configurator)",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _parse_index_xml(xml_bytes: bytes) -> PackIndex:
    """Parse index.idx XML into a PackIndex."""
    root = ET.fromstring(xml_bytes)
    ns = {"atmel": ATMEL_NS}

    index = PackIndex(fetched_at=time.time())

    for pdsc in root.findall("pdsc"):
        pack_name = pdsc.get(f"{{{ATMEL_NS}}}name", "")
        if not pack_name:
            continue

        # Filter to relevant families only
        if not any(pack_name.startswith(prefix) for prefix in _RELEVANT_PREFIXES):
            continue

        version = pdsc.get("version", "")
        pdsc_name = pdsc.get("name", "")

        pack_info = PackInfo(
            name=pack_name,
            version=version,
            pdsc_name=pdsc_name,
        )
        index.packs[pack_name] = pack_info

        # Extract device names from nested releases
        for release in pdsc.findall(".//atmel:release", ns):
            for device_el in release.findall(".//atmel:device", ns):
                dev_name = device_el.get("name", "")
                dev_family = device_el.get("family", "")
                if dev_name:
                    # Normalize to uppercase for consistent lookup
                    key = dev_name.upper()
                    index.devices[key] = DeviceEntry(
                        name=dev_name,
                        family=dev_family,
                        pack_name=pack_name,
                        pack_version=version,
                    )

    return index


def _load_cached_index() -> Optional[PackIndex]:
    """Load the cached index from disk."""
    if not INDEX_CACHE_FILE.exists():
        return None
    try:
        return PackIndex.from_json(INDEX_CACHE_FILE.read_text())
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def _save_cached_index(index: PackIndex) -> None:
    """Save the index to disk cache."""
    INDEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_CACHE_FILE.write_text(index.to_json())


def get_pack_index(force_refresh: bool = False) -> PackIndex:
    """
    Get the pack index, fetching from Microchip if stale or missing.

    Args:
        force_refresh: If True, ignore cache and re-fetch.

    Returns:
        PackIndex with device→pack mappings.
    """
    if not force_refresh:
        cached = _load_cached_index()
        if cached and not cached.is_stale:
            return cached

    try:
        xml_bytes = _fetch_index_xml()
        index = _parse_index_xml(xml_bytes)
        _save_cached_index(index)
        return index
    except Exception as e:
        # Fall back to stale cache if fetch fails
        cached = _load_cached_index()
        if cached:
            print(f"Warning: pack index fetch failed ({e}), using stale cache")
            return cached
        raise RuntimeError(f"Cannot fetch pack index and no cache available: {e}")


def lookup_device_pack(part_number: str) -> Optional[tuple[str, str]]:
    """
    Look up the DFP pack for a device.

    Returns:
        (atpack_url, atpack_filename) or None if not found.
    """
    index = get_pack_index()
    key = part_number.upper()
    entry = index.devices.get(key)
    if entry is None:
        return None

    pack = index.packs.get(entry.pack_name)
    if pack is None:
        return None

    return (pack.atpack_url, pack.atpack_filename)


def list_all_devices() -> list[str]:
    """Return sorted list of all device names from the pack index."""
    index = get_pack_index()
    return sorted(index.devices.keys())


def download_atpack(url: str, filename: str) -> Path:
    """
    Download an .atpack file to the DFP cache directory.

    Returns:
        Path to the downloaded file.
    """
    INDEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = INDEX_CACHE_DIR / filename
    if dest.exists():
        return dest

    print(f"Downloading {filename}...")
    req = urllib.request.Request(url, headers={
        "User-Agent": "config-pic/0.5 (pin configurator)",
    })
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())
    print(f"Downloaded {filename} ({dest.stat().st_size / 1_048_576:.1f} MB)")
    return dest


if __name__ == "__main__":
    index = get_pack_index(force_refresh=True)
    print(f"Fetched {len(index.devices)} devices across {len(index.packs)} packs")
    print(f"\nPacks:")
    for name, pack in sorted(index.packs.items()):
        devices_in_pack = sum(
            1 for d in index.devices.values() if d.pack_name == name
        )
        print(f"  {name} v{pack.version} — {devices_in_pack} devices")

    dspic33_count = sum(
        1 for k in index.devices if k.startswith("DSPIC33")
    )
    pic24_count = sum(
        1 for k in index.devices if k.startswith("PIC24")
    )
    print(f"\ndsPIC33: {dspic33_count}, PIC24: {pic24_count}")
