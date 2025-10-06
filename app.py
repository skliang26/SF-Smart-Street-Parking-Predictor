import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium

st.title("SF Smart Parking Dashboard")

# Load the pre-saved CSV
data = pd.read_csv("on_street_parking.csv")

# Display data table
st.write("### Parking Data Preview", data.head())

# Interactive map (example)
m = folium.Map(location=[37.7749, -122.4194], zoom_start=13)
for _, row in data.iterrows():
    folium.CircleMarker(
        location=[row['latitude'], row['longitude']],
        radius=4,
        popup=f"Block: {row['block_id']}",
        color="blue"
    ).add_to(m)
st_folium(m, width=700, height=500)

# Optional: Add some charts
st.write("### Average Parking Occupancy by Block")
chart_data = data.groupby("block_id")["occupancy"].mean().reset_index()
st.bar_chart(chart_data, x="block_id", y="occupancy")
