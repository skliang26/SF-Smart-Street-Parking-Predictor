# src/map_components.py
import folium
from folium import Tooltip
from folium.plugins import MarkerCluster, HeatMap
import pandas as pd  # for quantiles
from .constants import CLUSTER_CSS, HEATMAP_GRADIENT

def build_map(
    df, lat, lon, closest, optimal, ranked, units,
    show_heatmap=False, use_clustering=True, max_markers=1500,
):
    # Create base map centered on the user's point
    m = folium.Map(location=[lat, lon], zoom_start=15)

    # ----- distances shown in the two main tooltips -----
    closest_dist_str = f"{closest['distance_ft']:.0f} ft" if units == "ft" else f"{closest['distance_mi']:.2f} mi"
    optimal_dist_str = f"{optimal['distance_ft']:.0f} ft" if units == "ft" else f"{optimal['distance_mi']:.2f} mi"

    # ----- main marker tooltips (hover) -----
    popup_html_current = f"""
    <b>Closest Street:</b> {closest['STREET']}<br>
    Spots Open: {int(closest['PRKG_SPLY'])}<br>
    Coordinates: [{closest['center'][0]:.6f}, {closest['center'][1]:.6f}]<br>
    Distance: {closest_dist_str}<br><br>
    <b>Suggested Optimal:</b> {optimal['STREET']}<br>
    Spots Open: {int(optimal['PRKG_SPLY'])}<br>
    Coordinates: [{optimal['center'][0]:.6f}, {optimal['center'][1]:.6f}]<br>
    Distance: {optimal_dist_str}
    """
    popup_html_optimal = f"""
    <b>Suggested Optimal:</b> {optimal['STREET']}<br>
    Spots Open: {int(optimal['PRKG_SPLY'])}<br>
    Distance from Coordinates: {optimal_dist_str}
    """
    # User's query point (blue).
    folium.Marker(
        location=[lat, lon],
        tooltip=Tooltip(popup_html_current, sticky=True),
        icon=folium.Icon(color="blue", icon="info-sign"),
        **{"bubblingMouseEvents": False}
    ).add_to(m)
    # "Optimal" suggestion (green).
    folium.Marker(
        location=optimal["center"],
        tooltip=Tooltip(popup_html_optimal, sticky=True),
        icon=folium.Icon(color="green", icon="ok-sign"),
        **{"bubblingMouseEvents": False}
    ).add_to(m)

    # ----- cluster bubble styling -----
    m.get_root().header.add_child(folium.Element(CLUSTER_CSS))

    def availability_color(v) -> str:
        try:
            v = float(v)
        except Exception:
            v = 0.0
        if v >= 16: return "darkgreen"
        if v >= 12: return "lightgreen"
        if v >= 8:  return "yellow"
        if v >= 4:  return "orange"
        return "red"

    # ----- shaded markers (sample for performance) -----
    subset = df.sample(min(len(df), max_markers), random_state=42)
    parent = MarkerCluster().add_to(m) if use_clustering else m

    for _, row in subset.iterrows():
        lat_c = float(row["center_lat"])
        lon_c = float(row["center_lon"])
        est_open = float(row.get("EST_AVAILABLE", 0.0))
        color = availability_color(est_open)

        # A small circle representing availability matching.
        cm = folium.CircleMarker(
            location=(lat_c, lon_c),
            radius=5, color="black", weight=0.5,
            fill=True, fill_color=color, fill_opacity=0.6,
            **{"bubblingMouseEvents": False}
        )
        cm.add_child(Tooltip(f"{row['STREET']}<br>Est Avail: {int(est_open)}", sticky=True))
        cm.add_to(parent)

    # ===== heatmap of estimated availability (red = fewer, green = more) =====
    if show_heatmap:
        supply = pd.to_numeric(df["EST_AVAILABLE"], errors="coerce").fillna(0.0).clip(lower=0)
        green_at  = 16.0   # make weight≈1.0 when EST_AVAILABLE is ~16 open spots
        sharpness = 2.0    # >1 compresses mid values, so green is rarer
        weights   = ((supply / green_at).clip(0, 1) ** sharpness).tolist()

        HeatMap(
            list(zip(df["center_lat"], df["center_lon"], weights)),
            name="Open Spots Heatmap",
            radius=10, blur=10, max_zoom=16,
            max_val=3.0,        # keeps overlapping kernels from greening too fast
            min_opacity=0.15,
            gradient=HEATMAP_GRADIENT,
        ).add_to(m)


    # ----- legend -----
    # This legend explains the quantile coloring of the street markers.
    legend_html = """
    <div style="position: fixed; bottom: 50px; left: 50px; width: 200px; height: 170px;
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
    # Layer control lets users toggle layers
    folium.LayerControl().add_to(m)

    return m
