import streamlit as st
from .utils import inject_sidebar_css
from .nl_intent import parse_nl_query
from .geocode import geocode_cached, GEOCODER_AVAILABLE
from .constants import PRESETS

def render_sidebar():
    inject_sidebar_css()

    st.header("Inputs")

    # preset picker with on_change callback
    def _apply_preset():
        name = st.session_state.get("preset_choice")
        if name in PRESETS:
            p_lat, p_lon = PRESETS[name]
            # set origin + prefill coord widgets; runs before renders widgets
            st.session_state["origin_lat"] = float(p_lat)
            st.session_state["origin_lon"] = float(p_lon)
            st.session_state["lat_input"] = float(p_lat)
            st.session_state["lon_input"] = float(p_lon)
            # Streamlit automatically reruns after the callback returns
    # dropdown menu lists popular sf attractions + coords in PRESET
    st.selectbox(
        "Preset",
        ["(Select Attraction)"] + list(PRESETS.keys()),
        key="preset_choice",
        on_change=_apply_preset,
    )

    # defaults (Civic Center)
    lat_default, lon_default = 37.779190, -122.419140

    # prefer active origin if set (preset/address/coords)
    if "origin_lat" in st.session_state and "origin_lon" in st.session_state:
        lat_default = float(st.session_state["origin_lat"])
        lon_default = float(st.session_state["origin_lon"])

    st.markdown("### Find a location")
    coord_tab, addr_tab, ai_tab = st.tabs(["By Coordinates", "By Address", "AI (local)"])

    # AI tab: using Ollama natural-language to parameters
    with ai_tab:
        st.caption("Powered by a local model via Ollama (no data leaves your computer).")
        with st.form("ai_form", clear_on_submit=False):
            nl = st.text_area(
                "Describe what you want",
                placeholder="e.g., “I'll be at Pier 39; find parking within 0.5 miles and prioritize close spots.”",
                height=90,
            )
            ai_submit = st.form_submit_button("Interpret")

        if ai_submit:
            intent = parse_nl_query(nl)  # may return {} on failure
            if not intent:
                st.warning("I couldn't interpret that. Try adding a place or lat/lon.")
            else:
                # 1) Update origin from lat/lon or address
                if "lat" in intent and "lon" in intent:
                    st.session_state["origin_lat"] = float(intent["lat"])
                    st.session_state["origin_lon"] = float(intent["lon"])
                    st.session_state["lat_input"] = float(intent["lat"])
                    st.session_state["lon_input"] = float(intent["lon"])
                elif "address" in intent and GEOCODER_AVAILABLE:
                    with st.spinner("Geocoding address from AI…"):
                        res = geocode_cached(intent["address"])
                    if res:
                        lat_g, lon_g = map(float, res)
                        st.session_state["origin_lat"] = lat_g
                        st.session_state["origin_lon"] = lon_g
                        st.session_state["lat_input"] = lat_g
                        st.session_state["lon_input"] = lon_g
                        st.success(f"Address resolved to: ({lat_g:.6f}, {lon_g:.6f})")
                    else:
                        st.warning("AI gave an address I couldn't geocode. Try adding lat/lon.")

                # 2) Units
                if "units" in intent:
                    st.session_state["units_override"] = intent["units"]

                # 3) Radius (in miles)
                if "radius_mi" in intent:
                    st.session_state["radius_mi_override"] = float(intent["radius_mi"])

                # 4) Scoring knobs
                if "alpha" in intent:
                    st.session_state["alpha_override"] = float(intent["alpha"])
                if "beta" in intent:
                    st.session_state["beta_override"] = float(intent["beta"])

                # 5) Top-N
                if "top_n" in intent:
                    st.session_state["top_n_override"] = int(intent["top_n"])

                st.info(
                    "AI set: "
                    f"{'top_n='+str(intent.get('top_n'))+' ' if 'top_n' in intent else ''}"
                    f"{'radius_mi='+str(intent.get('radius_mi'))+' ' if 'radius_mi' in intent else ''}"
                    f"{'units='+intent.get('units','')+' ' if 'units' in intent else ''}"
                    f"{'alpha='+str(intent.get('alpha'))+' ' if 'alpha' in intent else ''}"
                    f"{'beta='+str(intent.get('beta'))+' ' if 'beta' in intent else ''}"
                    f"{'address='+intent.get('address','') if 'address' in intent else ''}"
                )
                st.rerun()

    # address tab first to set state before number_input exists 
    with addr_tab:
        with st.form("addr_form", clear_on_submit=False):
            addr = st.text_input("Address", placeholder="e.g., 1 Ferry Building, San Francisco")
            submitted_addr = st.form_submit_button("Search")

        if submitted_addr:
            q = (addr or "").strip()
            if not q:
                st.warning("Please enter an address.")
            elif not GEOCODER_AVAILABLE:
                st.warning("Geocoding not available. Try: `pip install geopy`")
            else:
                with st.spinner("Geocoding…"):
                    res = geocode_cached(q)
                if res:
                    lat_g, lon_g = map(float, res)
                    st.session_state["origin_lat"] = lat_g
                    st.session_state["origin_lon"] = lon_g
                    st.session_state["lat_input"] = lat_g
                    st.session_state["lon_input"] = lon_g
                    st.success(f"Geocoded: ({lat_g:.6f}, {lon_g:.6f})")
                    st.rerun()
                else:
                    st.warning("Couldn't find that address. Try something more specific.")

    # ensure input keys exist BEFORE rendering the coord widgets
    st.session_state.setdefault("lat_input", float(lat_default))
    st.session_state.setdefault("lon_input", float(lon_default))

    # coordinates tab (render after potential updates)
    with coord_tab:
        with st.form("coord_form", clear_on_submit=False):
            c1, c2 = st.columns(2)
            with c1:
                form_lat = st.number_input(
                    "Latitude",
                    value=float(st.session_state["lat_input"]),
                    format="%.6f",
                    key="lat_input",
                )
            with c2:
                form_lon = st.number_input(
                    "Longitude",
                    value=float(st.session_state["lon_input"]),
                    format="%.6f",
                    key="lon_input",
                )
            coord_submitted = st.form_submit_button("Search")

        if coord_submitted:
            st.session_state["origin_lat"] = float(form_lat)
            st.session_state["origin_lon"] = float(form_lon)
            # keys already reflect form values
            st.rerun()

    st.markdown("---")
    st.subheader("Ranking Controls")

    # respect AI overrides if present
    units = st.radio("Distance units", ["ft", "mi"], horizontal=True,
                     index=(0 if st.session_state.get("units_override","ft")=="ft" else 1))
    if units == "ft":
        # If AI provided a radius in miles, convert to ft for initial slider position
        default_ft = int(round(st.session_state.get("radius_mi_override", 1200/5280.0) * 5280.0))
        radius_input = st.slider("Search radius (ft)", 300, 5000, min(max(default_ft, 300), 5000), 50)
        max_mi = radius_input / 5280.0
    else:
        default_mi = float(st.session_state.get("radius_mi_override", 0.5))
        radius_input = st.slider("Search radius (mi)", 0.1, 3.0, min(max(default_mi, 0.1), 3.0), 0.05)
        max_mi = radius_input

    # how strongly distance hurts the score relative to supply 
    # score = PRKG_SPLY / (1 + α * (dist)^β) 
    # alpha = 
    alpha = st.slider("Distance penalty α",
                      0.2, 3.0, float(st.session_state.get("alpha_override", 0.8)), 0.1,            # α = penalty scale. Larger α → distance matters more
                      help="Scales how much distance hurts (bigger α = distance matters more)")
    beta = st.slider("Distance exponent β",                                                         # β (beta) = penalty curve. 
                     1.0, 3.0, float(st.session_state.get("beta_override", 1.6)), 0.1,
                     help="Shapes how distance hurts the score (non-linear curve): 1=linear, >1=hurts faster, <1=more tolerant.")
                    # β = 1 → linear penalty with distance. β > 1 → superlinear (distance hurts more quickly as it grows). β < 1 → sublinear (farther locations aren’t punished as harshly).

    top_n = st.slider("Show top N suggestions", 1, 10, int(st.session_state.get("top_n_override", 5)), 1)

    st.markdown("---")
    st.subheader("Map Layers")
    show_heatmap = st.toggle("Show supply heatmap", value=False)
    use_clustering = st.toggle("Cluster shaded markers", value=True)
    max_markers = st.slider("Max shaded markers", 200, 5000, 1500, 100)

    update_on_map_click = st.toggle("Update origin when I click the map", value=False)

    st.session_state.setdefault("bookmarks", [])

    # return values for the main app
    lat = float(st.session_state.get("origin_lat", lat_default))
    lon = float(st.session_state.get("origin_lon", lon_default))

    return (
        lat, lon,
        units, max_mi,
        alpha, beta, top_n,
        show_heatmap, use_clustering, max_markers,
        update_on_map_click,
    )
