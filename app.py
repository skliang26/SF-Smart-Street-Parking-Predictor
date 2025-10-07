# app.py — SF Smart Street Parking Predictor
# Run: streamlit run app.py

import ast
import math
import re
import numpy as np
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster, HeatMap

# ---------- Config ----------
st.set_page_config(page_title="SF Smart Street Parking Predictor", page_icon="🅿️", layout="wide")
st.title("SF Smart Street Parking Predictor")
st.caption("Enter coordinates, click the map, or type an address to find optimal street parking. Distances shown in ft/mi (toggle in sidebar).")

FT_PER_KM = 3280.8398950131
EARTH_RADIUS_KM = 6371.0088
FT_PER_MI = 5280.0
MI_PER_KM = 0.62137119223733

# ---------- Optional deps (geocoding; graceful fallback if missing) ----------
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
except Exception:
    GEOCODER = None
    GEOCODER_FALLBACK = None

try:
    from sklearn.neighbors import KDTree
    SKLEARN_OK = True
except Exception:
    KDTree = None
    SKLEARN_OK = False


# ---------- Helpers ----------
def parse_listish(val):
    if isinstance(val, (list, tuple)):
        return list(val)
    if isinstance(val, str):
        s = val.strip()
        if (s.startswith("[") and s.endswith("]")) or (s.startswith("(") and s.endswith(")")):
            try:
                return list(ast.literal_eval(s))
            except Exception:
                return None
    return None

def haversine_km(lat1, lon1, lat2, lon2):
    R = EARTH_RADIUS_KM
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlmb/2)**2
    return 2 * R * math.asin(math.sqrt(a))

@st.cache_data(show_spinner=False, ttl=7*24*3600)
def geocode_cached(query: str):
    """Return (lat, lon) or None; cached to avoid repeated network calls."""
    q = (query or "").strip()
    if not q:
        return None
    loc = None
    if GEOCODER:
        try:
            loc = GEOCODER.geocode(q)
        except Exception:
            loc = None
    if (not loc) and GEOCODER_FALLBACK:
        try:
            loc = GEOCODER_FALLBACK.geocode(q)
        except Exception:
            loc = None
    return (float(loc.latitude), float(loc.longitude)) if loc else None


# ---------- Data ----------
@st.cache_data
def load_df(path="on_street_parking.csv"):
    df = pd.read_csv(path)

    # Preferred: existing 'center' as [lat, lon]
    if "center" in df.columns:
        c = df["center"].apply(parse_listish)
        if c.notna().any():
            df["center_lat"] = c.apply(lambda x: x[0] if isinstance(x, (list, tuple)) and len(x) >= 2 else np.nan)
            df["center_lon"] = c.apply(lambda x: x[1] if isinstance(x, (list, tuple)) and len(x) >= 2 else np.nan)

    # Fallback A: arrays in 'latitude'/'longitude' -> midpoint
    if ("center_lat" not in df.columns) or ("center_lon" not in df.columns) or df["center_lat"].isna().all():
        if "latitude" in df.columns and "longitude" in df.columns:
            lat_lists = df["latitude"].apply(parse_listish)
            lon_lists = df["longitude"].apply(parse_listish)
            if lat_lists.notna().any() and lon_lists.notna().any():
                df["center_lat"] = lat_lists.apply(lambda xs: float(np.mean(xs)) if isinstance(xs, (list, tuple)) and len(xs) else np.nan)
                df["center_lon"] = lon_lists.apply(lambda xs: float(np.mean(xs)) if isinstance(xs, (list, tuple)) and len(xs) else np.nan)

    # Fallback B: midpoint from WKT LINESTRING 'shape' (lon lat)
    if (("center_lat" not in df.columns) or df["center_lat"].isna().all()) and ("shape" in df.columns):
        def wkt_midpoint(wkt):
            if not isinstance(wkt, str):
                return np.nan, np.nan
            pairs = re.findall(r"(-?\d+\.\d+)\s+(-?\d+\.\d+)", wkt)
            if not pairs:
                return np.nan, np.nan
            lon1, lat1 = map(float, pairs[0])
            lon2, lat2 = map(float, pairs[-1])
            return (lat1 + lat2) / 2.0, (lon1 + lon2) / 2.0  # (lat, lon)
        latlon = df["shape"].apply(wkt_midpoint)
        df["center_lat"] = latlon.apply(lambda t: t[0])
        df["center_lon"] = latlon.apply(lambda t: t[1])

    # Keep rows with coords only
    df = df.dropna(subset=["center_lat", "center_lon"]).copy()

    # STREET label if needed
    if "STREET" not in df.columns:
        street_name = df.get("ST_NAME", pd.Series([""] * len(df))).fillna("")
        street_type = df.get("ST_TYPE", pd.Series([""] * len(df))).fillna("")
        df["STREET"] = (street_name + " " + street_type).str.strip()

    # Supply + simple availability proxy used by color dots
    if "PRKG_SPLY" not in df.columns:
        df["PRKG_SPLY"] = 0
    df["PRKG_SPLY"] = pd.to_numeric(df["PRKG_SPLY"], errors="coerce").fillna(0).astype(float)
    df["EST_AVAILABLE"] = (df["PRKG_SPLY"] * 0.3).astype(float)

    # KDTree (optional)
    kdt = None
    coords_rad = None
    if SKLEARN_OK:
        try:
            coords_rad = np.radians(df[["center_lat", "center_lon"]].to_numpy())
            kdt = KDTree(coords_rad, metric="haversine")
        except Exception:
            kdt, coords_rad = None, None

    return df, kdt, coords_rad

df, kdt, coords_rad = load_df("on_street_parking.csv")


# ---------- Sidebar ----------
with st.sidebar:
    st.header("Inputs")
    presets = {
        "Golden Gate Park": (37.766020, -122.465651),
        "Pier 39": (37.808378, -122.409837),
        "Mason St": (37.795808, -122.411677),
        "Salesforce Park": (37.789700, -122.396600),
        "Palace of Fine Arts": (37.802780, -122.448330),
        "San Francisco City Hall": (37.779190, -122.419140),
        "Fisherman's Wharf": (37.808491, -122.415478),
    }

    choice = st.selectbox("Preset", ["(Pick Attraction)"] + list(presets.keys()))
    if choice != "(Pick Attraction)":
        lat_default, lon_default = presets[choice]
    else:
        lat_default, lon_default = 37.779190, -122.419140

    # Use last clicked / geocoded point if present
    if "origin_lat" in st.session_state and "origin_lon" in st.session_state:
        lat_default = float(st.session_state["origin_lat"])
        lon_default = float(st.session_state["origin_lon"])

    st.subheader("Search Coordinates")
    col_lat, col_lon = st.columns(2)
    with col_lat:
        lat = st.number_input("Latitude", value=float(lat_default), format="%.6f")
    with col_lon:
        lon = st.number_input("Longitude", value=float(lon_default), format="%.6f")

    # --- Clean Address Search (button-triggered + cached + fallback) ---
    st.markdown("or")
    st.subheader("Search Street")

    with st.form("addr_form", clear_on_submit=False):
        addr = st.text_input("Address", placeholder="e.g., 1 Ferry Building, San Francisco")
        submitted = st.form_submit_button("Find")

    if submitted:
        if GEOCODER is None and GEOCODER_FALLBACK is None:
            st.warning("Geocoding library not available. Install it:\n\n`pip3 install geopy`")
        else:
            with st.spinner("Geocoding…"):
                res = geocode_cached(addr)
            if res:
                st.session_state["origin_lat"], st.session_state["origin_lon"] = res
                st.success(f"Geocoded: ({res[0]:.6f}, {res[1]:.6f})")
                st.rerun()
            else:
                st.warning("Couldn't find that address. Try something more specific.")

    st.markdown("---")
    st.subheader("Ranking Controls")

    # Units toggle
    units = st.radio("Distance units", ["ft", "mi"], horizontal=True, index=0)

    # Radius slider in selected units -> convert to km for math
    if units == "ft":
        radius_input = st.slider("Search radius (ft)", 300, 5000, 1200, 50)
        max_km = radius_input / FT_PER_KM
    else:
        radius_input = st.slider("Search radius (mi)", 0.1, 3.0, 0.5, 0.05)
        max_km = radius_input / MI_PER_KM  # miles -> km

    alpha = st.slider("Distance penalty α", 0.2, 3.0, 0.8, 0.1)
    beta = st.slider("Distance exponent β", 1.0, 3.0, 1.6, 0.1)
    top_n = st.slider("Show top N suggestions", 1, 10, 5, 1)

    st.markdown("---")
    st.subheader("Map Layers")
    show_heatmap = st.toggle("Show supply heatmap", value=False)
    use_clustering = st.toggle("Cluster shaded markers", value=True)
    max_markers = st.slider("Max shaded markers", 200, 5000, 1500, 100)

    st.markdown("---")
    st.subheader("Session")
    if "bookmarks" not in st.session_state:
        st.session_state.bookmarks = []


# ---------- Candidate search & ranking ----------
def query_candidates(lat, lon, radius_km=0.8, fallback_k=300):
    latlon = np.radians([[lat, lon]])  # shape (1, 2)
    if kdt is not None and coords_rad is not None:
        r = radius_km / EARTH_RADIUS_KM
        idxs = kdt.query_radius(latlon, r=r, return_distance=False)
        idx = idxs[0] if len(idxs) else np.array([], dtype=int)
        if idx.size > 0:
            return df.iloc[idx].copy()
        # None within radius -> nearest K
        dists, near_idx = kdt.query(latlon, k=min(fallback_k, len(df)))
        return df.iloc[near_idx[0]].copy()
    else:
        # Vectorized fallback
        lat_r = np.radians(df["center_lat"].to_numpy())
        lon_r = np.radians(df["center_lon"].to_numpy())
        lat0, lon0 = latlon[0]
        dphi = lat_r - lat0
        dlmb = lon_r - lon0
        a = np.sin(dphi/2)**2 + np.cos(lat0)*np.cos(lat_r)*np.sin(dlmb/2)**2
        d_km = 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))
        mask = d_km <= radius_km
        cand = df.loc[mask].copy()
        if not cand.empty:
            cand["__dist_km"] = d_km[mask]
            return cand
        order = np.argsort(d_km)[:fallback_k]
        cand = df.iloc[order].copy()
        cand["__dist_km"] = d_km[order]
        return cand

def rank_candidates(lat, lon, max_km=0.8, alpha=0.8, beta=1.6, top_n=5):
    cand = query_candidates(lat, lon, radius_km=max_km, fallback_k=max(300, top_n*50))
    d_km = cand.apply(lambda r: haversine_km(lat, lon, r["center_lat"], r["center_lon"]), axis=1)
    d_ft = d_km * FT_PER_KM
    d_mi = d_km * MI_PER_KM
    score = cand["PRKG_SPLY"] / (1.0 + alpha * (d_km ** beta))
    out = cand.assign(__dist_km=d_km.values, __dist_ft=d_ft.values, __dist_mi=d_mi.values, __score=score.values) \
              .sort_values("__score", ascending=False)
    return out.head(top_n)


# ---------- Compute suggestions for the active point ----------
ranked = rank_candidates(lat, lon, max_km=max_km, alpha=alpha, beta=beta, top_n=top_n)
best = ranked.iloc[0]
closest_idx = df.apply(lambda r: ((r["center_lat"] - lat)**2 + (r["center_lon"] - lon)**2), axis=1).idxmin()
closest_row = df.loc[closest_idx]
closest_dist_km = haversine_km(lat, lon, closest_row["center_lat"], closest_row["center_lon"])
closest_dist_ft = closest_dist_km * FT_PER_KM
closest_dist_mi = closest_dist_km * MI_PER_KM

closest = {
    "STREET": closest_row["STREET"],
    "PRKG_SPLY": float(closest_row["PRKG_SPLY"]),
    "center": [float(closest_row["center_lat"]), float(closest_row["center_lon"])],
    "distance_ft": float(closest_dist_ft),
    "distance_mi": float(closest_dist_mi),
}
optimal = {
    "STREET": best["STREET"],
    "PRKG_SPLY": float(best["PRKG_SPLY"]),
    "center": [float(best["center_lat"]), float(best["center_lon"])],
    "score": float(best["__score"]),
    "distance_ft": float(best["__dist_ft"]),
    "distance_mi": float(best["__dist_mi"]),
}

# Helpers to format distance based on units toggle
def fmt_dist_ft_mi(ft_val: float, mi_val: float, units: str) -> str:
    return (f"{ft_val:.0f} ft") if units == "ft" else (f"{mi_val:.2f} mi")

# ---------- Summary (above map) ----------
gmap_opt = f"https://www.google.com/maps/search/?api=1&query={optimal['center'][0]},{optimal['center'][1]}"
gmap_closest = f"https://www.google.com/maps/search/?api=1&query={closest['center'][0]},{closest['center'][1]}"

closest_dist_str = fmt_dist_ft_mi(closest["distance_ft"], closest["distance_mi"], units)
optimal_dist_str = fmt_dist_ft_mi(optimal["distance_ft"], optimal["distance_mi"], units)

st.markdown(
    f"**Closest:** {closest['STREET']} — Supply of Spots: {int(closest['PRKG_SPLY'])}, "
    f"Distance from Coordinate: **{closest_dist_str}**  \n"
    f"**Optimal:** {optimal['STREET']} — Supply of Spots: {int(optimal['PRKG_SPLY'])}, "
    f"Distance from Coordinate: **{optimal_dist_str}**  \n"
    f"[Open optimal in Google Maps]({gmap_opt}) • [Open closest in Google Maps]({gmap_closest})"
)


# ---------- Map ----------
def availability_color(avail):
    if avail >= 30:   return "darkgreen"
    if avail >= 20:   return "lightgreen"
    if avail >= 10:   return "yellow"
    if avail >= 5:    return "orange"
    return "red"

m = folium.Map(location=[lat, lon], zoom_start=15)

# Markers (popup distances respect units toggle)
popup_html_current = f"""
<b>Closest Street:</b> {closest['STREET']}<br>
Supply: {int(closest['PRKG_SPLY'])}<br>
Coordinates: [{closest['center'][0]:.6f}, {closest['center'][1]:.6f}]<br>
Distance: {closest_dist_str}<br><br>
<b>Suggested Optimal:</b> {optimal['STREET']}<br>
Supply: {int(optimal['PRKG_SPLY'])}<br>
Coordinates: [{optimal['center'][0]:.6f}, {optimal['center'][1]:.6f}]<br>
Distance: {optimal_dist_str}
"""
popup_html_optimal = f"""
<b>Suggested Optimal:</b> {optimal['STREET']}<br>
Supply: {int(optimal['PRKG_SPLY'])}<br>
Distance: {optimal_dist_str}
"""

folium.Marker(
    location=[lat, lon],
    popup=folium.Popup(popup_html_current, max_width=320),
    icon=folium.Icon(color="blue", icon="info-sign")
).add_to(m)

folium.Marker(
    location=optimal["center"],
    popup=folium.Popup(popup_html_optimal, max_width=300),
    icon=folium.Icon(color="green", icon="ok-sign")
).add_to(m)

# Invert MarkerCluster colors: small=red, medium=orange, large=green
cluster_css = """
<style>
.marker-cluster-small { background-color: rgba(250, 81, 81, 0.75) !important; }
.marker-cluster-small div { background-color: rgba(250, 81, 81, 0.75) !important; }
.marker-cluster-medium { background-color: rgba(255, 165, 0, 0.75) !important; }
.marker-cluster-medium div { background-color: rgba(255, 165, 0, 0.75) !important; }
.marker-cluster-large { background-color: rgba(0, 128, 0, 0.75) !important; }
.marker-cluster-large div { background-color: rgba(0, 128, 0, 0.75) !important; }
.marker-cluster span { color: #fff !important; font-weight: 700; }
</style>
"""
m.get_root().header.add_child(folium.Element(cluster_css))

# Shaded availability markers
subset = df.sample(min(len(df), max_markers), random_state=42)
if use_clustering:
    cluster = MarkerCluster().add_to(m)
    parent = cluster
else:
    parent = m

for _, row in subset.iterrows():
    lat_c, lon_c = float(row["center_lat"]), float(row["center_lon"])
    est = float(row["EST_AVAILABLE"])
    color = availability_color(est)
    folium.CircleMarker(
        location=(lat_c, lon_c), radius=5, color="black", weight=0.5,
        fill=True, fill_color=color, fill_opacity=0.6,
        popup=f"{row['STREET']}<br>Est Avail: {int(est)}"
    ).add_to(parent)

# Heatmap (5 colors; low→high = red→…→darkgreen)
if show_heatmap:
    supply = df["PRKG_SPLY"].clip(lower=0)
    weights = (supply / supply.max()).tolist() if supply.max() > 0 else (supply * 0).tolist()
    heat_pts = list(zip(df["center_lat"].tolist(), df["center_lon"].tolist(), weights))
    gradient = {
        "0.00": "red",
        "0.25": "orange",
        "0.50": "yellow",
        "0.75": "lightgreen",
        "1.00": "darkgreen",
    }
    HeatMap(
        heat_pts, name="Supply Heatmap", radius=14, blur=18, max_zoom=16, gradient=gradient
    ).add_to(m)

# Legend
legend_html = """
<div style="position: fixed; bottom: 50px; left: 50px; width: 180px; height: 170px;
     background-color: white; border:2px solid grey; z-index:9999; font-size:14px;
     padding: 10px;">
     <b>Estimated Availability</b><br>
     <i style="background:red; width:10px; height:10px; float:left; margin-right:6px;"></i> Very Low<br>
     <i style="background:orange; width:10px; height:10px; float:left; margin-right:6px;"></i> Low<br>
     <i style="background:yellow; width:10px; height:10px; float:left; margin-right:6px;"></i> Medium <br>
     <i style="background:lightgreen; width:10px; height:10px; float:left; margin-right:6px;"></i> High<br>
     <i style="background:darkgreen; width:10px; height:10px; float:left; margin-right:6px;"></i> Very High
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))

folium.LayerControl().add_to(m)

# Render & handle clicks — save point then rerun so header/table/map update together
map_state = st_folium(m, height=600, width=None)
if map_state and map_state.get("last_clicked"):
    st.session_state["origin_lat"] = float(map_state["last_clicked"]["lat"])
    st.session_state["origin_lon"] = float(map_state["last_clicked"]["lng"])
    st.rerun()

# ---------- Top suggestions (units-aware) ----------
st.markdown(f"### Top suggestions — Distance ({'ft' if units=='ft' else 'mi'})")
if units == "ft":
    display_df = ranked[["STREET", "PRKG_SPLY", "__dist_ft", "__score"]].rename(
        columns={"PRKG_SPLY": "Supply", "__dist_ft": "Distance (ft)", "__score": "Score"}
    )
else:
    display_df = ranked[["STREET", "PRKG_SPLY", "__dist_mi", "__score"]].rename(
        columns={"PRKG_SPLY": "Supply", "__dist_mi": "Distance (mi)", "__score": "Score"}
    )
st.dataframe(display_df, use_container_width=True)

# ---------- Bookmarks & downloads ----------
cols = st.columns(3)
with cols[0]:
    if st.button("Bookmark optimal"):
        st.session_state.bookmarks.append({
            "street": optimal["STREET"],
            "lat": optimal["center"][0],
            "lon": optimal["center"][1],
            "supply": int(optimal["PRKG_SPLY"]),
            "score": float(optimal["score"]),
            "distance_mi": float(optimal["distance_mi"]),
            "distance_ft": float(optimal["distance_ft"]),
        })

with cols[1]:
    if units == "ft":
        csv_df = ranked.rename(
            columns={"PRKG_SPLY": "Supply", "__dist_ft": "DistanceFt", "__score": "Score"}
        )[["STREET", "Supply", "DistanceFt", "Score", "center_lat", "center_lon"]]
    else:
        csv_df = ranked.rename(
            columns={"PRKG_SPLY": "Supply", "__dist_mi": "DistanceMi", "__score": "Score"}
        )[["STREET", "Supply", "DistanceMi", "Score", "center_lat", "center_lon"]]
    csv_bytes = csv_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download Top-N CSV", data=csv_bytes, file_name="top_suggestions.csv", mime="text/csv")

with cols[2]:
    if st.button("Clear bookmarks"):
        st.session_state.bookmarks = []

if st.session_state.bookmarks:
    st.markdown("#### Bookmarks")
    st.table(pd.DataFrame(st.session_state.bookmarks))
