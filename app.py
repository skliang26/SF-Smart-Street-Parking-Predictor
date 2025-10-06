# app.py — Folium + Streamlit, no notebook changes needed
# pip installs needed: streamlit, folium, streamlit-folium, pandas, numpy

import ast
import math
import re
import numpy as np
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="ST Smart Street Parking Predictor", page_icon="🅿️", layout="wide")

# -------------------------
# Data loading & preparation
# -------------------------
@st.cache_data
def load_df(path="on_street_parking.csv"):
    df = pd.read_csv(path)

    # Safely parse strings like "[x, y]" into real lists
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

    # Preferred: existing 'center' column as [lat, lon]
    if "center" in df.columns:
        c = df["center"].apply(parse_listish)
        if c.notna().any():
            df["center_lat"] = c.apply(lambda x: x[0] if isinstance(x, (list, tuple)) and len(x) >= 2 else np.nan)
            df["center_lon"] = c.apply(lambda x: x[1] if isinstance(x, (list, tuple)) and len(x) >= 2 else np.nan)

    # Fallback A: arrays in 'latitude'/'longitude' -> use midpoint
    if ("center_lat" not in df.columns) or ("center_lon" not in df.columns) or df["center_lat"].isna().all():
        if "latitude" in df.columns and "longitude" in df.columns:
            lat_lists = df["latitude"].apply(parse_listish)
            lon_lists = df["longitude"].apply(parse_listish)
            if lat_lists.notna().any() and lon_lists.notna().any():
                df["center_lat"] = lat_lists.apply(
                    lambda xs: float(np.mean(xs)) if isinstance(xs, (list, tuple)) and len(xs) else np.nan
                )
                df["center_lon"] = lon_lists.apply(
                    lambda xs: float(np.mean(xs)) if isinstance(xs, (list, tuple)) and len(xs) else np.nan
                )

    # Fallback B: compute midpoint from WKT LINESTRING in 'shape' (lon, lat)
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

    # Keep only rows with coordinates
    df = df.dropna(subset=["center_lat", "center_lon"]).copy()

    # Make a street label if needed
    if "STREET" not in df.columns:
        street_name = df.get("ST_NAME", pd.Series([""] * len(df))).fillna("")
        street_type = df.get("ST_TYPE", pd.Series([""] * len(df))).fillna("")
        df["STREET"] = (street_name + " " + street_type).str.strip()

    # Ensure supply & a simple availability proxy
    if "PRKG_SPLY" not in df.columns:
        df["PRKG_SPLY"] = 0
    df["PRKG_SPLY"] = pd.to_numeric(df["PRKG_SPLY"], errors="coerce").fillna(0).astype(float)
    df["EST_AVAILABLE"] = (df["PRKG_SPLY"] * 0.3).astype(float)  # demo heuristic

    return df

df = load_df("on_street_parking.csv")  # keep your CSV alongside this file

# -------------------------
# Helpers (distance, scoring)
# -------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlmb/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def find_closest_street(lat, lon):
    d = ((df["center_lat"] - lat)**2 + (df["center_lon"] - lon)**2).pow(0.5)
    idx = d.idxmin()
    row = df.loc[idx]
    return {
        "STREET": row["STREET"],
        "PRKG_SPLY": float(row["PRKG_SPLY"]),
        "center": [float(row["center_lat"]), float(row["center_lon"])],
        "distance_km": float(haversine_km(lat, lon, row["center_lat"], row["center_lon"]))
    }

def optimal_street(lat, lon):
    # Simple score = supply / (1 + alpha * distance_km)
    alpha = 0.8
    distances = df.apply(lambda r: haversine_km(lat, lon, r["center_lat"], r["center_lon"]), axis=1)
    score = df["PRKG_SPLY"] / (1.0 + alpha * distances)
    idx = score.idxmax()
    row = df.loc[idx]
    return {
        "STREET": row["STREET"],
        "PRKG_SPLY": float(row["PRKG_SPLY"]),
        "center": [float(row["center_lat"]), float(row["center_lon"])],
        "score": float(score.loc[idx])
    }

# -------------------------
# UI — inputs
# -------------------------
st.title("🅿️ ST Smart Street Parking Predictor (Folium)")
st.caption("Enter coordinates or click the map to get the closest & a suggested optimal street.")

with st.sidebar:
    st.subheader("Coordinates of interest")
    presets = {
        "Golden Gate Park": (37.766020, -122.465651),
        "Pier 39": (37.808378, -122.409837),
        "Mason St": (37.795808, -122.411677),
    }
    choice = st.selectbox("Preset", ["(custom)"] + list(presets.keys()))
    if choice != "(custom)":
        lat_default, lon_default = presets[choice]
    else:
        lat_default, lon_default = 37.808378, -122.409837

    lat = st.number_input("Latitude", value=float(lat_default), format="%.6f")
    lon = st.number_input("Longitude", value=float(lon_default), format="%.6f")
    st.caption("Tip: click on the map to update these automatically.")

# Compute suggestions
closest = find_closest_street(lat, lon)
optimal = optimal_street(lat, lon)

# -------------------------
# Map: Folium + shading
# -------------------------
popup_html_current = f"""
<b>Closest Street:</b> {closest['STREET']}<br>
Supply: {int(closest['PRKG_SPLY'])}<br>
Coordinates: [{closest['center'][0]:.6f}, {closest['center'][1]:.6f}]<br>
Distance: {closest['distance_km']:.3f} km<br><br>
<b>Suggested Optimal:</b> {optimal['STREET']}<br>
Supply: {int(optimal['PRKG_SPLY'])}<br>
Coordinates: [{optimal['center'][0]:.6f}, {optimal['center'][1]:.6f}]
"""

popup_html_optimal = f"""
<b>Suggested Optimal:</b> {optimal['STREET']}<br>
Supply: {int(optimal['PRKG_SPLY'])}
"""

def availability_color(avail):
    if avail >= 30:
        return "darkgreen"
    elif avail >= 20:
        return "lightgreen"
    elif avail >= 10:
        return "yellow"
    elif avail >= 5:
        return "orange"
    else:
        return "red"

m = folium.Map(location=[lat, lon], zoom_start=15)

# Marker: user-selected coordinate
folium.Marker(
    location=[lat, lon],
    popup=folium.Popup(popup_html_current, max_width=300),
    icon=folium.Icon(color="blue", icon="info-sign")
).add_to(m)

# Marker: optimal street
folium.Marker(
    location=optimal["center"],
    popup=folium.Popup(popup_html_optimal, max_width=300),
    icon=folium.Icon(color="green", icon="ok-sign")
).add_to(m)

# Availability shading (sample for performance)
subset = df.sample(min(len(df), 2000), random_state=42)
for _, row in subset.iterrows():
    lat_c, lon_c = float(row["center_lat"]), float(row["center_lon"])
    est = float(row["EST_AVAILABLE"])
    color = availability_color(est)

    folium.CircleMarker(
        location=(lat_c, lon_c),
        radius=6,
        color="black",
        fill=True,
        fill_color=color,
        fill_opacity=0.6,
        weight=0.5,
        popup=f"{row['STREET']}<br>Estimated Available: {int(est)}"
    ).add_to(m)

# Legend
legend_html = """
<div style="position: fixed; bottom: 50px; left: 50px; width: 220px; height: 160px;
     background-color: white; border:2px solid grey; z-index:9999; font-size:14px;
     padding: 10px;">
     <b>Parking Availability</b><br>
     <i style="background:red; width:10px; height:10px; float:left; margin-right:6px;"></i> Very Low (0–4)<br>
     <i style="background:orange; width:10px; height:10px; float:left; margin-right:6px;"></i> Low (5–9)<br>
     <i style="background:yellow; width:10px; height:10px; float:left; margin-right:6px;"></i> Medium (10–19)<br>
     <i style="background:lightgreen; width:10px; height:10px; float:left; margin-right:6px;"></i> High (20–29)<br>
     <i style="background:darkgreen; width:10px; height:10px; float:left; margin-right:6px;"></i> Very High (30+)
</div>
"""
m.get_root().html.add_child(folium.Element(legend_html))

# Render map + capture clicks
map_state = st_folium(m, height=600, width=None)

# If user clicks on the map, recompute for that point
if map_state and map_state.get("last_clicked"):
    lat_click = map_state["last_clicked"]["lat"]
    lon_click = map_state["last_clicked"]["lng"]
    st.success(f"Clicked: ({lat_click:.6f}, {lon_click:.6f})")
    closest2 = find_closest_street(lat_click, lon_click)
    optimal2 = optimal_street(lat_click, lon_click)
    st.markdown(
        f"**Closest:** {closest2['STREET']} — supply {int(closest2['PRKG_SPLY'])}, "
        f"distance {closest2['distance_km']:.3f} km  \n"
        f"**Optimal:** {optimal2['STREET']} — supply {int(optimal2['PRKG_SPLY'])}"
    )
