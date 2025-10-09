# app.py — SF Smart Street Parking Predictor
# Run: streamlit run app.py

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

# local modules (all under src/)
from src.constants import APP_TITLE, APP_CAPTION
from src.sidebar import render_sidebar                                          # builds the sidebar UI and returns inputs
from src.data import load_df                                                    # loads & prepares parking dataset (cached)
from src.rank import rank_candidates, nearest_street, snap_origin_to_dataset    # scoring + nearest-street helpers
from src.map_components import build_map                                        # constructs map
from src.utils import fmt_dist                                                  # formats a distance

st.set_page_config(page_title=APP_TITLE, page_icon="🅿️", layout="wide")
st.title(APP_TITLE)
st.caption(APP_CAPTION)

# --- Sidebar (inputs & options) ---
with st.sidebar:
    (
        lat, lon,
        units, max_mi,
        alpha, beta, top_n,
        show_heatmap, use_clustering, max_markers,
        update_on_map_click,
    ) = render_sidebar()


# --- Data ---
df, kdt, coords_rad = load_df("on_street_parking.csv")     # cached

lat, lon = snap_origin_to_dataset(df, lat, lon, kdt=kdt, coords_rad=coords_rad, max_snap_mi=2.0)
# --- Ranking ---
# top-N candidates by score = supply / (1 + alpha * distance^beta)
ranked = rank_candidates(df, kdt, coords_rad, lat, lon, max_mi=max_mi, alpha=alpha, beta=beta, top_n=top_n)
best = ranked.iloc[0]           # "best" is the first sorted row
closest_row, closest_dist_mi = nearest_street(df, lat, lon)

closest = {
    "STREET": closest_row["STREET"],
    "PRKG_SPLY": float(closest_row["PRKG_SPLY"]),
    "center": [float(closest_row["center_lat"]), float(closest_row["center_lon"])],
    "distance_mi": float(closest_dist_mi),
    "distance_ft": float(closest_dist_mi * 5280.0),
}
optimal = {
    "STREET": best["STREET"],
    "PRKG_SPLY": float(best["PRKG_SPLY"]),
    "center": [float(best["center_lat"]), float(best["center_lon"])],
    "score": float(best["__score"]),
    "distance_mi": float(best["__dist_mi"]),
    "distance_ft": float(best["__dist_ft"]),
}

gmap_origin = f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lon:.6f}"
origin_str = f"[{lat:.6f}, {lon:.6f}]"
closest_dist_str = fmt_dist(closest["distance_ft"], closest["distance_mi"], units)
optimal_dist_str = fmt_dist(optimal["distance_ft"], optimal["distance_mi"], units)

gmap_opt = f"https://www.google.com/maps/search/?api=1&query={optimal['center'][0]},{optimal['center'][1]}"
gmap_closest = f"https://www.google.com/maps/search/?api=1&query={closest['center'][0]},{closest['center'][1]}"

# summary info above the map + google map links
st.markdown(f"""
    **Search coordinates:** {origin_str}  
    **Closest:** {closest['STREET']} — Spots Open: {int(closest['PRKG_SPLY'])}, Distance from Coordinate: **{closest_dist_str}**  
    **Optimal:** {optimal['STREET']} — Spots Open: {int(optimal['PRKG_SPLY'])}, Distance from Coordinate: **{optimal_dist_str}**  
    [Open coordinates in Google Maps]({gmap_origin}) • [Open optimal in Google Maps]({gmap_opt}) • [Open closest in Google Maps]({gmap_closest})
""")


# --- Map ---
# build the Folium map (centered at origin; with cluster markers, colored-coded street dots,  heatmap)
# set new origin and refreshes
m = build_map(
    df=df,
    lat=lat, lon=lon,
    closest=closest, optimal=optimal,
    ranked=ranked,
    units=units,
    show_heatmap=show_heatmap,
    use_clustering=use_clustering,
    max_markers=max_markers,
)
map_state = st_folium(m, height=600, width=None)        # render the map inside streamlit
if update_on_map_click and map_state and map_state.get("last_clicked"):
    st.session_state["origin_lat"] = float(map_state["last_clicked"]["lat"])
    st.session_state["origin_lon"] = float(map_state["last_clicked"]["lng"])
    st.rerun()

# --- Table & downloads ---
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

cols = st.columns(3)
with cols[0]:
    if st.button("Bookmark Optimal"):
        st.session_state.setdefault("bookmarks", [])
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
    st.download_button("Download Top-N CSV", data=csv_df.to_csv(index=False).encode("utf-8"),
                       file_name="top_suggestions.csv", mime="text/csv")
with cols[2]:
    if st.button("Clear bookmarks"):
        st.session_state["bookmarks"] = []

# show bookmarks if added
if st.session_state.get("bookmarks"):
    st.markdown("#### Bookmarks")
    st.table(pd.DataFrame(st.session_state.bookmarks))
