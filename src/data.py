import re
import numpy as np
import pandas as pd
import streamlit as st
from .utils import parse_listish        # helper that turns coord strings into lists

try:
    from sklearn.neighbors import KDTree
    SKLEARN_OK = True
except Exception:
    KDTree = None
    SKLEARN_OK = False

@st.cache_data
def load_df(path="on_street_parking.csv"):
    """
    Load and normalize the on-street parking dataset, then build a KDTree
    for fast nearest-neighbor searches.

    Returns:
        df         : cleaned DataFrame with at least columns:
                     ["center_lat", "center_lon", "STREET", "PRKG_SPLY", "EST_AVAILABLE", ...]
        kdt        : sklearn.neighbors.KDTree built on (lat, lon) in radians, or None if unavailable
        coords_rad : numpy array of coordinates in radians used to build KDTree (or None)
    """
    df = pd.read_csv(path)

    # preferred: existing 'center' as [lat, lon]
    if "center" in df.columns:
        c = df["center"].apply(parse_listish)   # parse strings like "[lat, lon]" into [lat, lon]
        if c.notna().any():
            # pull out lat/lon into separate numeric columns
            df["center_lat"] = c.apply(lambda x: x[0] if isinstance(x, (list, tuple)) and len(x) >= 2 else np.nan)
            df["center_lon"] = c.apply(lambda x: x[1] if isinstance(x, (list, tuple)) and len(x) >= 2 else np.nan)

    # fallback A: if theres no usable "center" values
    # but do have "latitude" and "longitude" columns that contain arrays
    # take the midpoint (mean) of each array as the center.
    if ("center_lat" not in df.columns) or ("center_lon" not in df.columns) or df["center_lat"].isna().all():
        if "latitude" in df.columns and "longitude" in df.columns:
            lat_lists = df["latitude"].apply(parse_listish)
            lon_lists = df["longitude"].apply(parse_listish)
            if lat_lists.notna().any() and lon_lists.notna().any():
                df["center_lat"] = lat_lists.apply(lambda xs: float(np.mean(xs)) if isinstance(xs, (list, tuple)) and len(xs) else np.nan)
                df["center_lon"] = lon_lists.apply(lambda xs: float(np.mean(xs)) if isinstance(xs, (list, tuple)) and len(xs) else np.nan)

    # fallback B: if still don’t have center coords, but have a WKT LINESTRING in "shape"
    # e.g. "LINESTRING(-122.42 37.77, -122.41 37.78, ...)" (lon lat),
    # compute the midpoint as the average of first and last vertices.
    if (("center_lat" not in df.columns) or df["center_lat"].isna().all()) and ("shape" in df.columns):
        def wkt_midpoint(wkt):
            if not isinstance(wkt, str):
                return np.nan, np.nan
            # get all "lon lat" float pairs in the WKT string
            pairs = re.findall(r"(-?\d+\.\d+)\s+(-?\d+\.\d+)", wkt)
            if not pairs:
                return np.nan, np.nan
            lon1, lat1 = map(float, pairs[0])
            lon2, lat2 = map(float, pairs[-1])
            #  midpoint of endpoints (lat, lon) order for consistency elsewhere
            return (lat1 + lat2) / 2.0, (lon1 + lon2) / 2.0
        latlon = df["shape"].apply(wkt_midpoint)
        df["center_lat"] = latlon.apply(lambda t: t[0])
        df["center_lon"] = latlon.apply(lambda t: t[1])

    # drop any rows where failed to get coordinates
    df = df.dropna(subset=["center_lat", "center_lon"]).copy()

    if "STREET" not in df.columns:
        street_name = df.get("ST_NAME", pd.Series([""] * len(df))).fillna("")
        street_type = df.get("ST_TYPE", pd.Series([""] * len(df))).fillna("")
        df["STREET"] = (street_name + " " + street_type).str.strip()

    if "PRKG_SPLY" not in df.columns:
        df["PRKG_SPLY"] = 0
    df["PRKG_SPLY"] = pd.to_numeric(df["PRKG_SPLY"], errors="coerce").fillna(0).astype(float)
    df["EST_AVAILABLE"] = (df["PRKG_SPLY"] * 0.3).astype(float)     # estimate about 30% parking spots are free

    kdt = None
    coords_rad = None
    if SKLEARN_OK:
        try:
            coords_rad = np.radians(df[["center_lat", "center_lon"]].to_numpy())
            kdt = KDTree(coords_rad, metric="haversine")  # radians
        except Exception:
            kdt, coords_rad = None, None

    return df, kdt, coords_rad
