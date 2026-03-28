"""
Parser for Microchip EDC (.PIC) XML files from Device Family Packs.
Extracts pin multiplexing, PPS register mappings, and peripheral data.

The data model separates pads (functional) from pinouts (physical):
- A Pad has a canonical name (e.g. "RB5") and fixed functions/RP numbers.
- A Pinout maps physical pin positions to pad names per package variant.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from typing import Optional
import json
import re

EDC_NS = "http://crownking/edc"
NS = {"edc": EDC_NS}


def _edc(attr: str) -> str:
    return f"{{{EDC_NS}}}{attr}"


@dataclass
class Pad:
    """A logical pad with all its multiplexed functions."""
    name: str                  # canonical name: "RB5", "AVDD", "MCLR"
    functions: list[str] = field(default_factory=list)
    rp_number: Optional[int] = None
    port: Optional[str] = None
    port_bit: Optional[int] = None
    analog_channels: list[str] = field(default_factory=list)
    is_power: bool = False


@dataclass
class Pinout:
    """Maps physical pin positions to pad names for one package."""
    package: str               # e.g. "SSOP-28", "UQFN-28"
    pin_count: int
    source: str                # "edc" or "overlay"
    pins: dict[int, str] = field(default_factory=dict)  # position -> pad name


@dataclass
class RemappablePeripheral:
    name: str
    direction: str  # "in" or "out"
    ppsval: Optional[int] = None


@dataclass
class PPSInputMapping:
    peripheral: str
    register: str
    register_addr: int
    field_name: str
    field_mask: int
    field_offset: int


@dataclass
class PPSOutputMapping:
    rp_number: int
    register: str
    register_addr: int
    field_name: str
    field_mask: int
    field_offset: int


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
    port_registers: dict[str, int] = field(default_factory=dict)
    ansel_bits: dict[str, list[int]] = field(default_factory=dict)  # e.g. {"A": [0,1,2,3,4], "B": [0,1,2,3,4,7,8,9]}

    def get_pinout(self, package: Optional[str] = None) -> Pinout:
        if package and package in self.pinouts:
            return self.pinouts[package]
        return self.pinouts[self.default_pinout]

    def resolve_pins(self, package: Optional[str] = None) -> list[dict]:
        """Return a list of pins with full pad data for a given package."""
        pinout = self.get_pinout(package)
        result = []
        for pos in sorted(pinout.pins.keys()):
            pad_name = pinout.pins[pos]
            pad = self.pads.get(pad_name)
            if pad:
                result.append({
                    "position": pos,
                    "pad_name": pad.name,
                    "functions": pad.functions,
                    "rp_number": pad.rp_number,
                    "port": pad.port,
                    "port_bit": pad.port_bit,
                    "analog_channels": pad.analog_channels,
                    "is_power": pad.is_power,
                })
            else:
                # Power pads with suffixes like VSS_1 -> match base name
                base = re.sub(r"_\d+$", "", pad_name)
                base_pad = self.pads.get(base)
                if base_pad:
                    result.append({
                        "position": pos,
                        "pad_name": pad_name,
                        "functions": base_pad.functions,
                        "rp_number": base_pad.rp_number,
                        "port": base_pad.port,
                        "port_bit": base_pad.port_bit,
                        "analog_channels": base_pad.analog_channels,
                        "is_power": base_pad.is_power,
                    })
                else:
                    result.append({
                        "position": pos,
                        "pad_name": pad_name,
                        "functions": [pad_name],
                        "rp_number": None,
                        "port": None,
                        "port_bit": None,
                        "analog_channels": [],
                        "is_power": True,
                    })
        return result

    def to_dict(self) -> dict:
        return {
            "part_number": self.part_number,
            "pads": {name: asdict(pad) for name, pad in self.pads.items()},
            "pinouts": {name: asdict(po) for name, po in self.pinouts.items()},
            "default_pinout": self.default_pinout,
            "remappable_inputs": [asdict(r) for r in self.remappable_inputs],
            "remappable_outputs": [asdict(r) for r in self.remappable_outputs],
            "pps_input_mappings": [asdict(m) for m in self.pps_input_mappings],
            "pps_output_mappings": [asdict(m) for m in self.pps_output_mappings],
            "port_registers": self.port_registers,
            "ansel_bits": self.ansel_bits,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, d: dict) -> "DeviceData":
        pads = {name: Pad(**p) for name, p in d["pads"].items()}
        pinouts = {}
        for name, po in d["pinouts"].items():
            po["pins"] = {int(k): v for k, v in po["pins"].items()}
            pinouts[name] = Pinout(**po)
        return cls(
            part_number=d["part_number"],
            pads=pads,
            pinouts=pinouts,
            default_pinout=d["default_pinout"],
            remappable_inputs=[RemappablePeripheral(**r) for r in d["remappable_inputs"]],
            remappable_outputs=[RemappablePeripheral(**r) for r in d["remappable_outputs"]],
            pps_input_mappings=[PPSInputMapping(**m) for m in d["pps_input_mappings"]],
            pps_output_mappings=[PPSOutputMapping(**m) for m in d["pps_output_mappings"]],
            port_registers=d.get("port_registers", {}),
            ansel_bits=d.get("ansel_bits", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "DeviceData":
        return cls.from_dict(json.loads(json_str))


def _parse_int(s: str) -> int:
    s = s.strip()
    if s.startswith("0x") or s.startswith("0X"):
        return int(s, 16)
    return int(s)


def _extract_port_info(name: str) -> tuple[Optional[str], Optional[int]]:
    m = re.match(r"R([A-Z])(\d+)", name)
    if m:
        return m.group(1), int(m.group(2))
    return None, None


def _extract_rp_number(name: str) -> Optional[int]:
    m = re.match(r"RP(\d+)", name)
    return int(m.group(1)) if m else None


def _pad_canonical_name(func_names: list[str]) -> str:
    """Derive the canonical pad name from its function list.
    Prefers GPIO port names (RA0-RE15) over RP names (RP32)."""
    # First pass: look for GPIO port names (RA-RE range, not RP)
    for name in func_names:
        if re.match(r"R[A-E]\d+$", name):
            return name
    # Power/special pins: use the first function
    return func_names[0] if func_names else "UNKNOWN"


def parse_edc_file(filepath: str) -> DeviceData:
    """Parse an EDC .PIC file and extract all pin multiplexing data."""
    tree = ET.parse(filepath)
    root = tree.getroot()

    part_number = root.get(_edc("name"), "UNKNOWN")

    # --- Parse PinList ---
    pinlist = root.find(".//edc:PinList", NS)
    package_desc = pinlist.get(_edc("desc"), "") if pinlist is not None else ""

    # Normalize package description into a short name
    if package_desc:
        pkg_name = package_desc.strip()
    else:
        pkg_name = "default"

    pads: dict[str, Pad] = {}
    pinout_map: dict[int, str] = {}
    remappable_inputs: list[RemappablePeripheral] = []
    remappable_outputs: list[RemappablePeripheral] = []

    if pinlist is not None:
        pin_position = 0
        for child in pinlist:
            tag = child.tag.replace(f"{{{EDC_NS}}}", "")

            if tag == "Pin":
                pin_position += 1
                vpins = child.findall("edc:VirtualPin", NS)
                func_names = [vp.get(_edc("name")) for vp in vpins]

                rp_num = None
                port = None
                port_bit = None
                analog = []
                is_power = False

                for name in func_names:
                    if name in ("VDD", "VSS", "AVDD", "AVSS", "MCLR"):
                        is_power = True
                    if rp_num is None:
                        rp_num = _extract_rp_number(name)
                    p, b = _extract_port_info(name)
                    if p is not None:
                        port, port_bit = p, b
                    if name.startswith("AN") and name[2:].isdigit():
                        analog.append(name)
                    elif name.startswith("ANA") and name[3:].isdigit():
                        analog.append(name)

                pad_name = _pad_canonical_name(func_names)

                # Handle duplicate pad names (multiple VDD/VSS pins)
                if pad_name in pads and is_power:
                    # Assign unique name for pinout mapping
                    count = sum(1 for k in pads if k.startswith(pad_name))
                    unique_name = f"{pad_name}_{count + 1}"
                    pinout_map[pin_position] = unique_name
                    pads[unique_name] = Pad(
                        name=unique_name,
                        functions=func_names,
                        rp_number=rp_num,
                        port=port,
                        port_bit=port_bit,
                        analog_channels=analog,
                        is_power=is_power,
                    )
                else:
                    pinout_map[pin_position] = pad_name
                    pads[pad_name] = Pad(
                        name=pad_name,
                        functions=func_names,
                        rp_number=rp_num,
                        port=port,
                        port_bit=port_bit,
                        analog_channels=analog,
                        is_power=is_power,
                    )

            elif tag == "RemappablePin":
                direction = child.get(_edc("direction"), "")
                vp = child.find("edc:VirtualPin", NS)
                if vp is not None:
                    name = vp.get(_edc("name"))
                    ppsval_str = vp.get(_edc("ppsval"))
                    ppsval = int(ppsval_str) if ppsval_str else None
                    rp = RemappablePeripheral(name=name, direction=direction, ppsval=ppsval)
                    if direction == "in":
                        remappable_inputs.append(rp)
                    else:
                        remappable_outputs.append(rp)

    # --- Parse SFR registers ---
    pps_input_mappings: list[PPSInputMapping] = []
    pps_output_mappings: list[PPSOutputMapping] = []
    port_registers: dict[str, int] = {}
    ansel_bits: dict[str, list[int]] = {}

    sfr_sector = root.find(".//edc:SFRDataSector", NS)
    if sfr_sector is not None:
        for sfr in sfr_sector.findall("edc:SFRDef", NS):
            cname = sfr.get(_edc("cname"), "")
            addr = _parse_int(sfr.get(_edc("_addr"), "0"))

            if re.match(r"(TRIS|ANSEL|LAT|PORT)[A-Z]$", cname):
                port_registers[cname] = addr

            # Extract ANSEL bit fields to know which pins have analog capability
            ansel_match = re.match(r"ANSEL([A-Z])$", cname)
            if ansel_match:
                port_letter = ansel_match.group(1)
                bits = []
                for fld in sfr.findall(".//edc:SFRFieldDef", NS):
                    fname = fld.get(_edc("cname"), "")
                    m = re.match(rf"ANSEL{port_letter}(\d+)", fname)
                    if m:
                        bits.append(int(m.group(1)))
                ansel_bits[port_letter] = sorted(bits)

            if cname.startswith("RPINR"):
                bit_offset = 0
                for mode_child in sfr.iter():
                    mode_tag = mode_child.tag.replace(f"{{{EDC_NS}}}", "")
                    if mode_tag == "AdjustPoint":
                        bit_offset += _parse_int(mode_child.get(_edc("offset"), "0"))
                    elif mode_tag == "SFRFieldDef":
                        field_name = mode_child.get(_edc("cname"), "")
                        mask = _parse_int(mode_child.get(_edc("mask"), "0"))
                        pps_input_mappings.append(PPSInputMapping(
                            peripheral=field_name,
                            register=cname,
                            register_addr=addr,
                            field_name=field_name,
                            field_mask=mask,
                            field_offset=bit_offset,
                        ))
                        bit_offset += _parse_int(mode_child.get(_edc("nzwidth"), "0"))

            elif cname.startswith("RPOR"):
                bit_offset = 0
                for mode_child in sfr.iter():
                    mode_tag = mode_child.tag.replace(f"{{{EDC_NS}}}", "")
                    if mode_tag == "AdjustPoint":
                        bit_offset += _parse_int(mode_child.get(_edc("offset"), "0"))
                    elif mode_tag == "SFRFieldDef":
                        field_name = mode_child.get(_edc("cname"), "")
                        mask = _parse_int(mode_child.get(_edc("mask"), "0"))
                        rp_match = re.match(r"RP(\d+)R", field_name)
                        rp_num = int(rp_match.group(1)) if rp_match else 0
                        pps_output_mappings.append(PPSOutputMapping(
                            rp_number=rp_num,
                            register=cname,
                            register_addr=addr,
                            field_name=field_name,
                            field_mask=mask,
                            field_offset=bit_offset,
                        ))
                        bit_offset += _parse_int(mode_child.get(_edc("nzwidth"), "0"))

    # Build the default pinout from the EDC
    default_pinout = Pinout(
        package=pkg_name,
        pin_count=len(pinout_map),
        source="edc",
        pins=pinout_map,
    )

    pinouts = {pkg_name: default_pinout}

    return DeviceData(
        part_number=part_number,
        pads=pads,
        pinouts=pinouts,
        default_pinout=pkg_name,
        remappable_inputs=remappable_inputs,
        remappable_outputs=remappable_outputs,
        pps_input_mappings=pps_input_mappings,
        pps_output_mappings=pps_output_mappings,
        port_registers=port_registers,
        ansel_bits=ansel_bits,
    )


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python edc_parser.py <path_to.PIC>")
        sys.exit(1)
    device = parse_edc_file(sys.argv[1])
    print(device.to_json())
