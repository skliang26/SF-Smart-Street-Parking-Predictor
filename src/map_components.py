import folium
from folium import Tooltip
from folium.plugins import MarkerCluster, HeatMap
from .constants import CLUSTER_CSS, HEATMAP_GRADIENT

def availability_color(avail):
    if avail >= 30:   return "darkgreen"
    if avail >= 20:   return "lightgreen"
    if avail >= 10:   return "yellow"
    if avail >= 5:    return "orange"
    return "red"

def build_map(
    df, lat, lon, closest, optimal, ranked, units,
    show_heatmap=False, use_clustering=True, max_markers=1500,
):
    m = folium.Map(location=[lat, lon], zoom_start=15)

    closest_dist_str = f"{closest['distance_ft']:.0f} ft" if units == "ft" else f"{closest['distance_mi']:.2f} mi"
    optimal_dist_str = f"{optimal['distance_ft']:.0f} ft" if units == "ft" else f"{optimal['distance_mi']:.2f} mi"

    # pins have popup displaying information of "closest" and "optimal"
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

    folium.Marker(
        location=[lat, lon],
        tooltip=Tooltip(popup_html_current, sticky=True),
        icon=folium.Icon(color="blue", icon="info-sign"),
        **{"bubblingMouseEvents": False}
    ).add_to(m)

    folium.Marker(
        location=optimal["center"],
        tooltip=Tooltip(popup_html_optimal, sticky=True),
        icon=folium.Icon(color="green", icon="ok-sign"),
        **{"bubblingMouseEvents": False}
    ).add_to(m)

    m.get_root().header.add_child(folium.Element(CLUSTER_CSS))

    subset = df.sample(min(len(df), max_markers), random_state=42)
    parent = MarkerCluster().add_to(m) if use_clustering else m

    for _, row in subset.iterrows():
        lat_c, lon_c = float(row["center_lat"]), float(row["center_lon"])
        est = int(float(row["EST_AVAILABLE"]))
        color = availability_color(est)
        cm = folium.CircleMarker(
            location=(lat_c, lon_c), radius=5, color="black", weight=0.5,
            fill=True, fill_color=color, fill_opacity=0.6,
            **{"bubblingMouseEvents": False}
        )
        cm.add_child(Tooltip(f"{row['STREET']}<br>Est Avail: {est}", sticky=True))
        cm.add_to(parent)

    if show_heatmap:
        supply = df["PRKG_SPLY"].clip(lower=0)
        weights = (supply / supply.max()).tolist() if supply.max() > 0 else (supply * 0).tolist()
        heat_pts = list(zip(df["center_lat"].tolist(), df["center_lon"].tolist(), weights))
        HeatMap(heat_pts, name="Supply Heatmap", radius=14, blur=18, max_zoom=16, gradient=HEATMAP_GRADIENT).add_to(m)

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
    return m
