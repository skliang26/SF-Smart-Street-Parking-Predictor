# src/geocode.py
import re
import streamlit as st
from .constants import SF_BBOX, POI_COORDS, POI_ALIASES
GEOCODER = None
GEOCODER_FALLBACK = None
GEOCODER_AVAILABLE = False

try:
    from geopy.geocoders import Nominatim, ArcGIS
    try:
        GEOCODER = Nominatim(user_agent="sf_parking_streamlit", timeout=4)
    except Exception:
        GEOCODER = None
    try:
        GEOCODER_FALLBACK = ArcGIS(timeout=4)
    except Exception:
        GEOCODER_FALLBACK = None
    GEOCODER_AVAILABLE = GEOCODER is not None or GEOCODER_FALLBACK is not None
except Exception:
    pass

def in_sf_bounds(lat: float, lon: float) -> bool:
    return (SF_BBOX[1] <= float(lat) <= SF_BBOX[3]) and (SF_BBOX[0] <= float(lon) <= SF_BBOX[2])

def _normalize_key(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", (s or "").lower()).strip()

def _match_poi_coords(raw_query: str):
    """
    substring match for known POIs.
    Works for 'pier 39', 'Pier39', and variants with 'San Francisco' appended.
    """
    key = _normalize_key(raw_query)
    # Remove trailing city if present so substring checks are cleaner
    key_cityless = re.sub(r"\b(san\s*francisco|sf|s\.f\.)\b.*$", "", key).strip()

    for k, coords in POI_COORDS.items():
        if k in key or k in key_cityless:
            return coords
    # Special spacing-insensitive case
    if "pier39" in key.replace(" ", ""):
        return POI_COORDS["pier39"]
    return None

def ensure_sf(query: str) -> str:
    """Make queries SF-specific (aliases + append 'San Francisco, CA' if city missing)."""
    q = (query or "").strip()
    if not q:
        return q
    key = _normalize_key(q)
    if key in POI_ALIASES:
        return POI_ALIASES[key]
    if not re.search(r"\b(san\s*francisco|sf|s\.f\.)\b", q, flags=re.I):
        q = f"{q}, San Francisco, CA"
    return q

@st.cache_data(show_spinner=False, ttl=7*24*3600)
def geocode_cached(query: str):
    """
    Geocode with a strong SF bias:
      0) Try POI short-circuit (no network).
      1) Normalize to SF string.
      2) Nominatim with SF viewbox + bounded=True.
      3) ArcGIS fallback.
      4) Reject results outside SF bbox.
    Returns (lat, lon) or None.
    """
    raw = (query or "").strip()
    if not raw:
        return None

    # 0) Hard POI short-circuit first
    poi = _match_poi_coords(raw)
    if poi:
        return poi

    # 1) Then bias the text to SF (aliases or append ', San Francisco, CA')
    q = ensure_sf(raw)

    # 2) Nominatim with SF bounding box (lon/lat order)
    if GEOCODER:
        try:
            loc = GEOCODER.geocode(
                q,
                country_codes="us",
                viewbox=[SF_BBOX[0], SF_BBOX[1], SF_BBOX[2], SF_BBOX[3]],  # west,south,east,north
                bounded=True,
                exactly_one=True,
                addressdetails=False,
            )
            if loc and in_sf_bounds(loc.latitude, loc.longitude):
                return (float(loc.latitude), float(loc.longitude))
        except Exception:
            pass

    # 3) ArcGIS fallback (still enforce SF bounds)
    if GEOCODER_FALLBACK:
        try:
            loc = GEOCODER_FALLBACK.geocode(q)
            if loc and in_sf_bounds(loc.latitude, loc.longitude):
                return (float(loc.latitude), float(loc.longitude))
        except Exception:
            pass

    return None
