
import streamlit as st
import pandas as pd
import datetime
import requests
import os

station_ids = {
    "East Foothills": "MILL1",
    "Lower Cajon Pass": "DEVC1",
    "Yucaipa Area": "OGVC1"
}

fallback_coords = {
    "East Foothills": (34.07984, -117.04676),
    "Lower Cajon Pass": (34.18214, -117.38511),
    "Yucaipa Area": (34.03049, -117.04311)
}

MESOWEST_TOKEN = "KuNpavINSZKrX063INKci9wUQtzHT89tidQThcANGH"
snapshot_file = "airs_snapshot_log.csv"

def get_raws_data(station_id):
    try:
        url = f"https://api.synopticdata.com/v2/stations/nearesttime?stid={station_id}&vars=air_temp,relative_humidity,wind_speed&token={MESOWEST_TOKEN}"
        response = requests.get(url)
        data = response.json()
        obs = data['STATION'][0]['OBSERVATIONS']
        return {
            "RH": obs['relative_humidity_set_1'],
            "Temp": obs['air_temp_set_1'],
            "Wind": obs['wind_speed_set_1'],
            "FuelMoisture": 7,
            "Source": "RAWS (MesoWest)"
        }
    except:
        return None

def get_open_meteo_data(lat, lon):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,relative_humidity_2m,windspeed_10m&forecast_days=1"
        response = requests.get(url)
        data = response.json()
        rh = data['hourly']['relative_humidity_2m'][13]
        temp = data['hourly']['temperature_2m'][13]
        wind = data['hourly']['windspeed_10m'][13]
        return {
            "RH": rh,
            "Temp": temp,
            "Wind": wind,
            "FuelMoisture": 9,
            "Source": "Fallback: Open-Meteo"
        }
    except:
        return None

def run_tier_logic(zone_data, plume_detected):
    rh = zone_data["RH"]
    temp = zone_data["Temp"]
    wind = zone_data["Wind"]
    fm = zone_data["FuelMoisture"]
    source = zone_data.get("Source", "Unknown")

    tier = "Tier 2"
    confidence = 3
    notes = []

    if rh < 25 and temp > 90 and fm < 10:
        tier = "Tier 3"
        confidence = 3
        notes.append("Base Tier 3 met")

    if rh < 20 and temp > 95 and fm < 9 and wind >= 10:
        tier = "Tier 4"
        confidence = 4
        notes.append("Tier 4: dry, hot, terrain-wind aligned")

    if rh < 15 and temp > 100 and fm < 8:
        tier = "Tier 5"
        confidence = 5
        notes.append("Tier 5: extreme fire weather")

    if tier == "Tier 3" and wind >= 15:
        tier = "Tier 4"
        confidence = min(confidence + 1, 5)
        notes.append("Wind-aligned slope escalation")

    if plume_detected and tier in ["Tier 3", "Tier 4"]:
        tier = "Tier 5"
        confidence = 5
        notes.append("Plume-confirmed override")

    if "Fallback" in source:
        confidence = min(confidence, 4)
        notes.append("Using fallback data source")

    return tier, confidence, ", ".join(notes)

def log_snapshot(zone, rh, temp, wind, fm, tier, confidence, source, plume, camera_url, notes):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    snapshot = pd.DataFrame([[now, zone, rh, temp, wind, fm, tier, confidence, source, plume, camera_url, notes]],
                            columns=["Timestamp", "Zone", "RH", "Temp", "Wind", "FM", "Tier", "Confidence", "Source", "PlumeFlag", "CameraURL", "Notes"])
    if os.path.exists(snapshot_file):
        snapshot.to_csv(snapshot_file, mode='a', header=False, index=False)
    else:
        snapshot.to_csv(snapshot_file, index=False)

# Streamlit UI
st.title("AIRS Lite – Tier Calculator with Fallback")
zone = st.selectbox("Select Zone", list(station_ids.keys()))
plume = st.checkbox("Plume Confirmed?")
manual_entry = st.checkbox("Manual Weather Entry")
camera_url = st.text_input("Camera URL (optional):", "")

if manual_entry:
    rh = st.number_input("RH (%)", 0, 100, 20)
    temp = st.number_input("Temperature (°F)", 30, 130, 95)
    wind = st.number_input("Wind Speed (mph)", 0, 60, 10)
    fm = st.number_input("10-hr Fuel Moisture (%)", 0, 20, 8)
    source = "Manual Entry"
    data = {"RH": rh, "Temp": temp, "Wind": wind, "FuelMoisture": fm, "Source": source}
else:
    data = get_raws_data(station_ids[zone])
    if data is None:
        st.warning("RAWS unavailable, using Open-Meteo fallback")
        lat, lon = fallback_coords[zone]
        data = get_open_meteo_data(lat, lon)
        if data is None:
            st.error("All sources unavailable. Switch to manual entry.")
            st.stop()

st.markdown("### Weather Snapshot")
st.write(f"RH: {data['RH']}% | Temp: {data['Temp']}°F | Wind: {data['Wind']} mph | FM: ~{data['FuelMoisture']}%")
st.caption(f"Source: {data['Source']}")

tier, confidence, notes = run_tier_logic(data, plume)

st.markdown("### AIRS Output")
st.write(f"**Tier:** {tier}")
st.write(f"**Confidence:** {confidence}/5")
st.write(f"**Notes:** {notes}")

if st.button("Export Snapshot"):
    log_snapshot(zone, data["RH"], data["Temp"], data["Wind"], data["FuelMoisture"], tier, confidence, data["Source"], plume, camera_url, notes)
    st.success("Snapshot saved.")
