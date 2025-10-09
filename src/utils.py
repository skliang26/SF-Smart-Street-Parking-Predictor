import ast
import math
import streamlit as st
from .constants import EARTH_RADIUS_MI

def parse_listish(val):
    if isinstance(val, (list, tuple)): return list(val)
    if isinstance(val, str):
        s = val.strip()
        if (s.startswith("[") and s.endswith("]")) or (s.startswith("(") and s.endswith(")")):
            try:
                return list(ast.literal_eval(s))
            except Exception:
                return None
    return None

def haversine_mi(lat1, lon1, lat2, lon2):
    R = EARTH_RADIUS_MI
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlmb/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def fmt_dist(ft_val: float, mi_val: float, units: str) -> str:
    return f"{ft_val:.0f} ft" if units == "ft" else f"{mi_val:.2f} mi"

# UI cleanup (used by sidebar)
def inject_sidebar_css():
    st.markdown(
        """
        <style>
          section[data-testid="stSidebar"] .block-container { padding-top: 0.75rem; }
          section[data-testid="stSidebar"] form { border: 0 !important; background: transparent !important; padding: 0 !important; }
          section[data-testid="stSidebar"] .stTabs [data-baseweb="tab-list"] { gap: 6px; }
          section[data-testid="stSidebar"] .stTabs [data-baseweb="tab"] { padding: 4px 10px; }
          .vspace { height: 8px; }
        </style>
        """,
        unsafe_allow_html=True,
    )
