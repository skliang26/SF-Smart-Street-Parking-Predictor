SF Smart Street Parking Predictor 🅿️

Streamlit app that helps you find promising on-street parking near a point in San Francisco.
Set your origin by coordinates, address, AI text, or map click. The app ranks nearby street segments by a simple supply-vs-distance score, shows them on a Folium map (with hover popups, clusters, optional heatmap), and lets you download the top-N.

Distances shown in ft/mi (toggle in the sidebar).
Geocoding is SF-biased and recognizes common POIs like “Pier 39”, “Golden Gate Park”, etc.

Highlights
    Multiple ways to set origin: Presets • Coordinates • Address • AI (local via Ollama) • Map click
    Hover popups on pins (no misclicks that move the origin)
    Ranking balances spots available vs distance (you can tune α & β)
    Heatmap and clustered markers for visual supply
    Bookmarks & CSV export
    SF-only geocoding with bounding box + hardcoded POI coordinates for robust results
    Optional local LLM (Mistral via Ollama) to parse natural-language requests 

How it works 
    Data loading (src/data.py)
        Reads on_street_parking.csv.
        Derives a segment center from center (preferred), or the midpoint of latitude/longitude arrays, or WKT shape (LINESTRING lon lat).
        Builds a KDTree (if scikit-learn installed) for fast geospatial queries.
        Computes a simple availability proxy EST_AVAILABLE = 0.3 * PRKG_SPLY for map color dots.
    Scoring (src/rank.py)
        Distance (miles) by haversine.
        Score per segment:
        score = PRKG_SPLY / (1 + α * (distance_mi ** β))
            α (alpha) — “distance importance”
            β (beta) — shape of the distance penalty (1 = linear, >1 = steeper)
        Higher score wins; show top-N.
    Geocoding (src/geocode.py)
        Normalizes inputs to San Francisco, recognizes POI aliases, and has canonical POI coordinates to avoid “in the water” locations.
        Uses Nominatim (OpenStreetMap) with an SF bounding box; falls back to ArcGIS.
        Rejects any geocode outside the SF bbox. Results are cached (7 days).
    Map (src/map_components.py)
        Folium map with hover popups for pins.
        Optional heatmap of supply and marker clusters (custom colors).
        Toggle to update origin on map click (off by default).  
    Sidebar (src/sidebar.py)
        Tabs for Coordinates, Address, and AI (local).
        The AI tab calls src/nl_intent.py which talks to Ollama (Mistral) at http://localhost:11434.
        AI can set: origin (lat/lon or address), units, radius, α/β, top-N; sidebar widgets reflect overrides.

Setup
    Requirements (recommended):
        Python 3.10+
        macOS / Linux / Windows
        (Optional) Ollama for local AI: https://ollama.com

    Install Python deps
        # from project root
        python3 -m venv .venv
        source .venv/bin/activate     # Windows: .venv\Scripts\activate
        pip install -U pip
        # core
        pip install streamlit pandas numpy folium streamlit-folium requests
        # geocoding (recommended)
        pip install geopy
        # fast nearest-neighbor (optional)
        pip install scikit-learn

    (Optional) Local AI via Ollama
        # install Ollama (see website for installer)
        # then pull a model:
        ollama pull mistral
        # Ollama listens on http://localhost:11434 by default

    Run
        streamlit run app.py
        Then the printed local URL (usually http://localhost:8501) opens.

Data format
    Your on_street_parking.csv should include any of these (the loader is flexible):
        Coordinates (preferred):
            center — stringified list [lat, lon]
        Or arrays to average:
            latitude, longitude — stringified lists, we take the midpoint
        Or WKT (fallback):
            shape — LINESTRING lon lat, lon lat, ... (we take the endpoints’ midpoint)
        Street label (any of):
            STREET (preferred) or ST_NAME + ST_TYPE
        Supply:
            PRKG_SPLY (numeric, will be coerced; missing → 0)
    Anything missing is derived if possible; rows without usable coordinates are dropped.

Using the app
    Sidebar
        Preset: jump to a known landmark
        By Coordinates: type lat/lon, click Search
        By Address: type an address/POI, click Search
        AI (local): free-form text like
        “I’ll be at pier 39, half a mile, keep it close, top 4”

        Ranking Controls: choose ft/mi, set radius, tune α/β, choose top-N
        Map Layers: toggle heatmap, cluster, and max shaded markers
        Update origin on map click: when enabled, clicking the map moves the origin

        Map
            Hover pins to see details (closest + optimal are highlighted)
            Optional heatmap/clusters

        Top suggestions
            Units are your ft/mi choice
            Download CSV of the top-N

        Bookmarks
            Save the current optimal and view them below

Example AI prompts

“pier 39, half a mile, keep it close, top 4”

“coords 37.8084, -122.4098 show top 3”

“oracle park within 0.3 mi prioritize distance”

“find 10 suggestions around ferry building; miles; alpha 1.0 beta 1.4”
