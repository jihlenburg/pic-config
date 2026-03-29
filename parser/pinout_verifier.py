"""
Pinout Verifier: cross-check parsed EDC pinout data against the device datasheet
using the Claude API.

Accepts a datasheet PDF and current device data, sends to Claude for analysis,
and returns a structured diff with proposed corrections as an overlay JSON.
"""

import base64
import io
import json
import os
import re
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
PINOUTS_DIR = BASE_DIR / "pinouts"

# Claude API configuration
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 16384


def _get_api_key() -> Optional[str]:
    """Get the Anthropic API key from environment or .env file."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


@dataclass
class PinCorrection:
    """A single proposed correction to a pin mapping."""
    pin_position: int
    current_pad: str          # what the EDC says
    datasheet_pad: str        # what the datasheet says
    current_functions: list[str]
    datasheet_functions: list[str]
    correction_type: str      # "wrong_pad", "missing_functions", "extra_functions", "missing_pin", "extra_pin"
    note: str = ""


@dataclass
class PackageResult:
    """Verification result for one package variant."""
    package_name: str
    pin_count: int
    pins: dict[int, str]                     # position -> pad name
    pin_functions: dict[str, list[str]]       # pad name -> functions
    corrections: list[PinCorrection] = field(default_factory=list)
    match_score: float = 0.0                  # 0.0–1.0, how well it matches current data


@dataclass
class VerifyResult:
    """Full verification result from Claude analysis."""
    part_number: str
    packages: dict[str, PackageResult] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    raw_response: str = ""

    def to_dict(self) -> dict:
        return {
            "part_number": self.part_number,
            "packages": {
                name: {
                    "package_name": pkg.package_name,
                    "pin_count": pkg.pin_count,
                    "pins": {str(k): v for k, v in pkg.pins.items()},
                    "pin_functions": pkg.pin_functions,
                    "corrections": [asdict(c) for c in pkg.corrections],
                    "match_score": pkg.match_score,
                }
                for name, pkg in self.packages.items()
            },
            "notes": self.notes,
        }

    def to_overlay_json(self) -> dict:
        """Convert verification result to pinout overlay format for saving."""
        overlay = {"packages": {}}
        for name, pkg in self.packages.items():
            overlay["packages"][name] = {
                "source": "overlay",
                "pin_count": pkg.pin_count,
                "pins": {str(k): v for k, v in sorted(pkg.pins.items())},
            }
        return overlay


def _build_current_data_summary(device_data: dict, package: Optional[str] = None) -> str:
    """Build a concise summary of current parsed data for the prompt."""
    lines = [f"Part: {device_data['part_number']}"]
    lines.append(f"Selected package: {device_data.get('selected_package', 'default')}")

    # List available packages
    packages = device_data.get("packages", {})
    if packages:
        lines.append(f"Known packages: {', '.join(f'{n} ({p['pin_count']}p)' for n, p in packages.items())}")

    # Current pin mapping
    pins = device_data.get("pins", [])
    lines.append(f"\nCurrent pin mapping ({len(pins)} pins):")
    for pin in pins:
        pos = pin.get("position", "?")
        pad = pin.get("pad", "?")
        funcs = pin.get("functions", [])
        is_power = pin.get("is_power", False)
        rp = pin.get("rp_number")
        func_str = ", ".join(funcs[:8])
        if len(funcs) > 8:
            func_str += f" (+{len(funcs)-8} more)"
        rp_str = f" [RP{rp}]" if rp is not None else ""
        pwr_str = " [POWER]" if is_power else ""
        lines.append(f"  Pin {pos}: {pad}{pwr_str}{rp_str} — {func_str}")

    return "\n".join(lines)


_VERIFY_PROMPT = """\
You are analyzing a Microchip dsPIC33/PIC24 datasheet PDF to extract and verify pin mapping data.

## Task

1. Find ALL package pinout tables in this datasheet (e.g., SPDIP, SOIC, SSOP, QFN, TQFP, UQFN, etc.)
2. For each package, extract the COMPLETE pin-to-pad mapping (every pin number → pad name)
3. For each pad, extract ALL listed functions/alternate names
4. Compare against the current parsed data (provided below) and identify any discrepancies

## Current Parsed Data

{current_data}

## Output Format

Return a JSON object with this exact structure (no markdown fencing, just raw JSON):

{{
  "packages": {{
    "<PackageName>": {{
      "pin_count": <int>,
      "pins": {{
        "<pin_number>": "<pad_name>",
        ...
      }},
      "pin_functions": {{
        "<pad_name>": ["func1", "func2", ...],
        ...
      }}
    }}
  }},
  "corrections": [
    {{
      "pin_position": <int>,
      "package": "<PackageName>",
      "current_pad": "<what EDC says>",
      "datasheet_pad": "<what datasheet says>",
      "type": "<wrong_pad|missing_functions|extra_functions|missing_pin>",
      "note": "<explanation>"
    }}
  ],
  "notes": ["<any general observations about data quality>"]
}}

## Important Guidelines

- Use UPPERCASE for pad names (e.g., "RA0", "RB5", "MCLR", "VDD", "VSS", "AVDD")
- Pin numbers must be integers (as strings in JSON keys)
- Include ALL pins including power (VDD, VSS, AVDD, AVSS, VCAP) and special (MCLR)
- For pads with numbered duplicates (multiple VDD pins), use suffixes: VDD, VDD_2, VDD_3, etc.
- Functions should include the primary I/O name (e.g., "RA0"), analog channel (e.g., "AN0"), and any fixed peripheral functions
- If the datasheet shows a package not in the current data, include it as a new entry
- If pin data matches perfectly, say so in notes — don't invent corrections
- Be precise: only flag actual discrepancies, not formatting differences
"""


def _call_claude_api(pdf_bytes: bytes, prompt: str, api_key: str) -> str:
    """Call the Claude API with a PDF document and text prompt."""
    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    payload = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    }

    body = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        raise RuntimeError(
            f"Claude API error {e.code}: {error_body}"
        )

    # Extract text content from response
    text_parts = []
    for block in result.get("content", []):
        if block.get("type") == "text":
            text_parts.append(block["text"])

    return "\n".join(text_parts)


def _parse_claude_response(raw: str, device_data: dict) -> VerifyResult:
    """Parse Claude's JSON response into a VerifyResult."""
    part = device_data.get("part_number", "UNKNOWN")
    result = VerifyResult(part_number=part, raw_response=raw)

    # Extract JSON from the response (handle markdown fencing if present)
    json_str = raw.strip()
    if json_str.startswith("```"):
        lines = json_str.splitlines()
        start = next((i for i, l in enumerate(lines) if l.strip().startswith("{")), 1)
        end = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].strip().startswith("}")), len(lines) - 1)
        json_str = "\n".join(lines[start:end + 1])

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        result.notes.append(f"Failed to parse Claude response as JSON: {e}")
        result.notes.append(f"Raw response (first 500 chars): {raw[:500]}")
        return result

    # Parse packages
    current_pins = {
        p["position"]: p for p in device_data.get("pins", [])
    }

    for pkg_name, pkg_data in data.get("packages", {}).items():
        pins = {}
        for pos_str, pad in pkg_data.get("pins", {}).items():
            try:
                pins[int(pos_str)] = pad
            except (ValueError, TypeError):
                continue

        pkg_result = PackageResult(
            package_name=pkg_name,
            pin_count=pkg_data.get("pin_count", len(pins)),
            pins=pins,
            pin_functions=pkg_data.get("pin_functions", {}),
        )

        # Calculate match score against current data
        if current_pins:
            matches = 0
            total = 0
            for pos, pad in pins.items():
                if pos in current_pins:
                    total += 1
                    current_pad = current_pins[pos].get("pad_name", "") or current_pins[pos].get("pad", "")
                    if _normalize_pad(pad) == _normalize_pad(current_pad):
                        matches += 1
            pkg_result.match_score = matches / total if total > 0 else 0.0

        result.packages[pkg_name] = pkg_result

    # Parse corrections
    for corr in data.get("corrections", []):
        pkg_name = corr.get("package", "")
        if pkg_name in result.packages:
            result.packages[pkg_name].corrections.append(PinCorrection(
                pin_position=corr.get("pin_position", 0),
                current_pad=corr.get("current_pad", ""),
                datasheet_pad=corr.get("datasheet_pad", ""),
                current_functions=corr.get("current_functions", []),
                datasheet_functions=corr.get("datasheet_functions", []),
                correction_type=corr.get("type", "unknown"),
                note=corr.get("note", ""),
            ))

    result.notes = data.get("notes", [])
    return result


def _normalize_pad(name: str) -> str:
    """Normalize pad name for comparison."""
    return re.sub(r"_\d+$", "", name.upper().strip())


def _extract_pinout_pages(pdf_bytes: bytes, max_pages: int = 40) -> bytes:
    """
    Extract the pinout-relevant pages from a large datasheet PDF.

    Scans page text for pinout-related keywords and extracts those pages
    plus surrounding context. Falls back to the first max_pages if no
    pinout section is detected.
    """
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        # If pypdf not available, just truncate by returning as-is
        # and hope the PDF is small enough
        return pdf_bytes

    reader = PdfReader(io.BytesIO(pdf_bytes))
    total_pages = len(reader.pages)

    if total_pages <= max_pages:
        return pdf_bytes  # small enough already

    # Scan for pinout-related pages
    pinout_keywords = [
        "pinout", "pin diagram", "pin table", "pin description",
        "pin function", "package pinout", "pin allocation",
        "SPDIP", "SOIC", "SSOP", "QFN", "TQFP", "UQFN", "VQFN",
        "pin name", "pin number", "pin#",
    ]

    scored_pages: list[tuple[int, int]] = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
            text_lower = text.lower()
            score = sum(1 for kw in pinout_keywords if kw.lower() in text_lower)
            if score > 0:
                scored_pages.append((i, score))
        except Exception:
            continue

    if scored_pages:
        # Sort by score descending, take the top-scoring cluster
        scored_pages.sort(key=lambda x: x[1], reverse=True)
        selected = set()
        for page_idx, _ in scored_pages:
            # Add the page and surrounding context
            for offset in range(-2, 3):
                p = page_idx + offset
                if 0 <= p < total_pages:
                    selected.add(p)
            if len(selected) >= max_pages:
                break
        page_indices = sorted(selected)[:max_pages]
    else:
        # Fallback: first max_pages (pinout is usually near the front)
        page_indices = list(range(min(max_pages, total_pages)))

    writer = PdfWriter()
    for i in page_indices:
        writer.add_page(reader.pages[i])

    buf = io.BytesIO()
    writer.write(buf)
    extracted = buf.getvalue()
    print(f"Extracted {len(page_indices)} of {total_pages} pages "
          f"({len(extracted) / 1_048_576:.1f} MB)")
    return extracted


def verify_pinout(
    pdf_bytes: bytes,
    device_data: dict,
    api_key: Optional[str] = None,
) -> VerifyResult:
    """
    Verify device pinout data against a datasheet PDF using Claude.

    Args:
        pdf_bytes: Raw bytes of the datasheet PDF.
        device_data: Current device data dict (from /api/device/{part} response).
        api_key: Anthropic API key. If None, reads from .env.

    Returns:
        VerifyResult with package data, corrections, and match scores.
    """
    if api_key is None:
        api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("No Anthropic API key configured. Set ANTHROPIC_API_KEY in .env or provide via settings.")

    # Extract only relevant pages to stay within token limits
    pdf_bytes = _extract_pinout_pages(pdf_bytes)

    current_summary = _build_current_data_summary(device_data)
    prompt = _VERIFY_PROMPT.format(current_data=current_summary)

    raw_response = _call_claude_api(pdf_bytes, prompt, api_key)
    return _parse_claude_response(raw_response, device_data)


def save_overlay(part_number: str, verify_result: VerifyResult, selected_packages: Optional[list[str]] = None) -> Path:
    """
    Save verified pinout data as an overlay JSON file.

    Args:
        part_number: Device part number.
        verify_result: The verification result to save.
        selected_packages: If provided, only save these packages. Otherwise save all.

    Returns:
        Path to the saved overlay file.
    """
    PINOUTS_DIR.mkdir(parents=True, exist_ok=True)
    overlay_path = PINOUTS_DIR / f"{part_number.upper()}.json"

    # Load existing overlay if any
    existing = {}
    if overlay_path.exists():
        try:
            existing = json.loads(overlay_path.read_text())
        except (json.JSONDecodeError, KeyError):
            pass

    # Merge new packages
    if "packages" not in existing:
        existing["packages"] = {}

    overlay_data = verify_result.to_overlay_json()
    for pkg_name, pkg_data in overlay_data["packages"].items():
        if selected_packages and pkg_name not in selected_packages:
            continue
        existing["packages"][pkg_name] = pkg_data

    overlay_path.write_text(json.dumps(existing, indent=2))
    return overlay_path
