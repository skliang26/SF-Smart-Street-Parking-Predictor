# src/nl_intent.py
import json
import re
from typing import Dict, Any
import requests

from .geocode import ensure_sf, in_sf_bounds  # reuse the same SF helpers
from .constants import OLLAMA_URL, OLLAMA_MODEL, SF_BBOX

SYSTEM_INSTRUCTIONS = """
You convert natural-language parking intents into a compact JSON with optional keys:
- lat (float)
- lon (float)
- address (string)
- radius_mi (float)
- units ("mi" or "ft")
- alpha (float)
- beta (float)
- top_n (int)

IMPORTANT RULES:
- Assume the city is San Francisco, CA by default unless another city is EXPLICITLY stated.
- If the user gives only a place name (e.g., 'pier 39'), set address to "<place>, San Francisco, CA".
- Be case-insensitive. 'pier 39' and 'Pier 39' are the same.
- If you output lat/lon, they must be within the SF city bounding box:
  west=-122.514, south=37.708, east=-122.357, north=37.832.
- If the user says something like "top 4", "4 top suggestions", "show 4", or "4 suggestions",
  set top_n to that number.

Return ONLY JSON (no extra words).
Examples:
User: "pier 39, half a mile, keep it close"
JSON: {"address":"Pier 39, San Francisco, CA","radius_mi":0.5,"units":"mi","alpha":1.5}
User: "coords 37.8084, -122.4098 show top 3"
JSON: {"lat":37.8084,"lon":-122.4098,"top_n":3}
User: "4 top suggestions near the Ferry Building"
JSON: {"address":"Ferry Building, San Francisco, CA","top_n":4}
"""

def _call_ollama(prompt: str) -> Dict[str, Any]:
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": SYSTEM_INSTRUCTIONS.strip() + "\nUser: " + prompt.strip() + "\nJSON:",
                "stream": False,
            },
            timeout=20,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not m:
            return {}
        parsed = json.loads(m.group(0))

        # Post-normalize to SF rules
        if "address" in parsed:
            parsed["address"] = ensure_sf(parsed["address"])

        if "lat" in parsed and "lon" in parsed:
            try:
                la = float(parsed["lat"]); lo = float(parsed["lon"])
                if not in_sf_bounds(la, lo):
                    # drop invalid coords; we'll rely on address if present
                    parsed.pop("lat", None)
                    parsed.pop("lon", None)
            except Exception:
                parsed.pop("lat", None)
                parsed.pop("lon", None)

        return parsed
    except Exception:
        return {}

# Simple regex fallback if Ollama fails (left as is, or keep your existing version)
def _regex_fallback(nl: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    txt = nl or ""

    # coords
    m = re.search(r"(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)", txt)
    if m:
        out["lat"] = float(m.group(1)); out["lon"] = float(m.group(2))
        if not in_sf_bounds(out["lat"], out["lon"]):
            out.pop("lat", None); out.pop("lon", None)

    # radius in miles
    m = re.search(r"(\d+(\.\d+)?)\s*(mi|mile|miles)\b", txt, flags=re.I)
    if m:
        out["radius_mi"] = float(m.group(1))

    # units
    if re.search(r"\bfeet|ft\b", txt, flags=re.I):
        out["units"] = "ft"
    elif re.search(r"\bmi|mile|miles\b", txt, flags=re.I):
        out["units"] = "mi"

    # ---- robust top_n extraction ----
    # capture: "top 4", "top4", "show 4", "4 top", "4 top suggestions", "4 suggestions", "4 results"
    patterns = [
        r"\btop\s*(\d{1,2})\b",                               # top 4 / top4
        r"\bshow\s+(\d{1,2})\b",                              # show 4
        r"\b(\d{1,2})\s*top\b",                               # 4 top
        r"\b(\d{1,2})\s*(?:results?|suggestions?|spots?)\b",  # 4 suggestions / 4 results
        r"\b(?:results?|suggestions?|spots?)\s*(?:=|:)?\s*(\d{1,2})\b", # suggestions: 4
    ]
    for pat in patterns:
        m = re.search(pat, txt, flags=re.I)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 15:   # keep it reasonable
                out["top_n"] = n
                break

    # If no coords, try to treat the text as an SF place/address
    if "lat" not in out and "lon" not in out:
        m = re.search(r"[A-Za-z].+", txt)   # any textual content
        if m:
            out["address"] = ensure_sf(m.group(0).strip())

    return out


def parse_nl_query(nl: str) -> Dict[str, Any]:
    nl = (nl or "").strip()
    if not nl:
        return {}
    # normalize early
    _nl = nl.lower()

    parsed = _call_ollama(nl)
    if parsed:
        return parsed
    return _regex_fallback(_nl)
