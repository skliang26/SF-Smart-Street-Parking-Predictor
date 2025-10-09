#src/constants.py
APP_TITLE = "SF Smart Street Parking Predictor"
APP_CAPTION = "Enter coordinates, type an address, ask AI bot, or click the map to set your point. Distances shown in ft/mi (toggle in sidebar)."

FT_PER_MI = 5280.0
EARTH_RADIUS_MI = 3958.7613  # miles

HEATMAP_GRADIENT = {
    0.00: "red",
    0.25: "orange",
    0.50: "yellow",
    0.75: "lightgreen",
    1.00: "darkgreen",
}

CLUSTER_CSS = """
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

# ---- Geography (San Francisco bounding box) ----
# west, south, east, north
SF_BBOX = (-122.514, 37.708, -122.357, 37.832)

# ---- Known POIs (lowercased keys for robust matching) ----
POI_COORDS = {
    "pier 39": (37.808378, -122.409837),
    "pier39": (37.808378, -122.409837),
    "fishermans wharf": (37.808491, -122.415478),
    "fisherman's wharf": (37.808491, -122.415478),
    "golden gate park": (37.769420, -122.486214),
    "palace of fine arts": (37.802780, -122.448330),
    "salesforce park": (37.789700, -122.396600),
    "coit tower": (37.802395, -122.405822),
    "oracle park": (37.778595, -122.389270),
    "alamo square": (37.776358, -122.434871),
    "ferry building": (37.795490, -122.393700),
    "san francisco city hall": (37.779190, -122.419140),
    "sf city hall": (37.779190, -122.419140),
    "city hall": (37.779190, -122.419140),
    "golden gate bridge": (37.807750, -122.474000),
}

# Aliases to canonical SF strings for geocoders (matching keys are lowercased)
POI_ALIASES = {
    "pier 39": "Pier 39, San Francisco, CA",
    "fishermans wharf": "Fisherman's Wharf, San Francisco, CA",
    "fisherman's wharf": "Fisherman's Wharf, San Francisco, CA",
    "golden gate park": "Golden Gate Park, San Francisco, CA",
    "palace of fine arts": "Palace of Fine Arts, San Francisco, CA",
    "salesforce park": "Salesforce Park, San Francisco, CA",
    "coit tower": "Coit Tower, San Francisco, CA",
    "oracle park": "Oracle Park, San Francisco, CA",
    "alamo square": "Alamo Square, San Francisco, CA",
    "san francisco city hall": "San Francisco City Hall, San Francisco, CA",
    "city hall": "San Francisco City Hall, San Francisco, CA",
    "sf city hall": "San Francisco City Hall, San Francisco, CA",
    "ferry building": "Ferry Building, San Francisco, CA",
}

# ---- Sidebar “Presets” (pretty labels → coords; reuse POI_COORDS to avoid drift) ----
PRESETS = {
    "Golden Gate Park": POI_COORDS["golden gate park"],
    "Pier 39": POI_COORDS["pier 39"],
    "Salesforce Park": POI_COORDS["salesforce park"],
    "Palace of Fine Arts": POI_COORDS["palace of fine arts"],
    "San Francisco City Hall": POI_COORDS["san francisco city hall"],  # not in POI_COORDS; 
    "Fisherman's Wharf": POI_COORDS["fisherman's wharf"],
}

# ---- Ollama (local LLM) defaults ----
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral"