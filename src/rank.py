# src/rank.py
import numpy as np
import pandas as pd
from .constants import FT_PER_MI, EARTH_RADIUS_MI

# haversine dist:  angular distance between two points on the surface of a sphere
def _haversine_mi_vectorized(lat, lon, lat_arr, lon_arr):
    """
    Compute great-circle distance (in miles) from one point (lat, lon)
    to many points (lat_arr, lon_arr) using the haversine formula.

    Vectorized: lat_arr / lon_arr are numpy arrays; this returns a
    numpy array of distances of the same length.
    """
    lat1 = np.radians(lat)
    lon1 = np.radians(lon)
    lat2 = np.radians(lat_arr)
    lon2 = np.radians(lon_arr)
    dphi = lat2 - lat1          #Δφ, the north–south angular difference
    dlmb = lon2 - lon1          #Δλ, the east–west angular difference
    # Haversine formula
    a = np.sin(dphi / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlmb / 2.0) ** 2
    # Arc length in radians × Earth radius (miles)
    return 2.0 * EARTH_RADIUS_MI * np.arcsin(np.sqrt(a))

def _query_candidates(df, kdt, coords_rad, lat, lon, radius_mi=0.5, fallback_k=300):
    """
    Find candidate rows (street segments) near the query point (lat, lon).
    Strategy:
      1) If a KDTree (in radians, metric='haversine') is available, prefer it:
         - Return all rows within 'radius_mi'
         - If none are within the radius, return the nearest K rows
      2) If no KDTree, compute vectorized haversine to all rows:
         - Return all within 'radius_mi'
         - Otherwise return the K closest by distance

    Returns a *copy* of the candidate slice of df.
    """
    if kdt is not None and coords_rad is not None and len(df) > 0:
        # KDTree expects radians; convert radius from miles to radians
        r_rad = float(radius_mi) / EARTH_RADIUS_MI
        q = np.radians([[lat, lon]])
        idxs = kdt.query_radius(q, r=r_rad, return_distance=False)
        idx = idxs[0] if len(idxs) else np.array([], dtype=int)             #idx is the array of row indices in df that lie within 0.5 mi of O.
        if idx.size > 0:
            return df.iloc[idx].copy()

        # ff none in radius: ask KDTree for the nearest K items
        k = min(fallback_k, len(df))
        d_rad, near_idx = kdt.query(q, k=k)
        return df.iloc[near_idx[0]].copy()

    # Fallback (no KDTree): compute all distances and filter
    lat_arr = df["center_lat"].to_numpy()
    lon_arr = df["center_lon"].to_numpy()
    d_mi = _haversine_mi_vectorized(lat, lon, lat_arr, lon_arr)
    mask = d_mi <= radius_mi
    cand = df.loc[mask].copy()
    if not cand.empty:
        return cand

    # nearest K if none inside radius
    order = np.argsort(d_mi)[: min(fallback_k, len(df))]
    return df.iloc[order].copy()

def rank_candidates(df, kdt, coords_rad, lat, lon, max_mi=0.5, alpha=0.8, beta=1.6, top_n=5):
    """
    Score and rank nearby street segments around (lat, lon).

    score = PRKG_SPLY / (1 + alpha * (distance_mi ^ beta))

    Returns a DataFrame with columns:
      - STREET, PRKG_SPLY, center_lat, center_lon
      - __dist_mi, __dist_ft, __score
    sorted by __score desc, truncated to top_n.
    """
    # Gather candidates (within radius or nearest K)
    cand = _query_candidates(df, kdt, coords_rad, lat, lon, radius_mi=max_mi, fallback_k=max(300, top_n * 50))

    #distances from the query point to each candidate
    d_mi = _haversine_mi_vectorized(lat, lon, cand["center_lat"].to_numpy(), cand["center_lon"].to_numpy())
    d_ft = d_mi * FT_PER_MI

    # Score increases with supply, decreases with distance
    # F-beta score, a metric for evaluating classification models that measures the balance between precision and recall. 
    supply = pd.to_numeric(cand["PRKG_SPLY"], errors="coerce").fillna(0.0).astype(float)
    score = supply / (1.0 + float(alpha) * (d_mi ** float(beta)))
    # attach computed fields and sort by score
    out = cand.assign(__dist_mi=d_mi, __dist_ft=d_ft, __score=score).sort_values("__score", ascending=False)
    return out.head(int(top_n))

def nearest_street(df, lat, lon, kdt=None, coords_rad=None):
    """
    Return (row, dist_mi) for the absolutely nearest street segment to (lat, lon).
    Uses KDTree (haversine) if available; falls back to vectorized haversine acress the entire DataFrame.
    """
    if kdt is not None and coords_rad is not None and len(df) > 0:
        q = np.radians([[lat, lon]])
        dist_rad, idx = kdt.query(q, k=1)   # radians on the sphere
        dist_mi = float(dist_rad[0][0] * EARTH_RADIUS_MI)
        row = df.iloc[int(idx[0][0])]
        return row, dist_mi

    # Vectorized fallback nearest
    lat_arr = df["center_lat"].to_numpy()
    lon_arr = df["center_lon"].to_numpy()
    d_mi = _haversine_mi_vectorized(lat, lon, lat_arr, lon_arr)
    i = int(np.argmin(d_mi))
    return df.iloc[i], float(d_mi[i])

def snap_origin_to_dataset(df, lat, lon, kdt=None, coords_rad=None, max_snap_mi=2.0):
    """
    If (lat,lon) is outside SF bounds OR farther than max_snap_mi from any street,
    snap to nearest street segment center. Otherwise return as-is.
    """
    from .geocode import in_sf_bounds  # reuse same bbox rule

    if not in_sf_bounds(lat, lon):
        row, _ = nearest_street(df, lat, lon, kdt=kdt, coords_rad=coords_rad)
        return float(row["center_lat"]), float(row["center_lon"])

    row, d_mi = nearest_street(df, lat, lon, kdt=kdt, coords_rad=coords_rad)
    if d_mi > max_snap_mi:
        return float(row["center_lat"]), float(row["center_lon"])

    return float(lat), float(lon)