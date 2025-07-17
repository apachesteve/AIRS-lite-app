
import streamlit as st
import pandas as pd
import datetime
import requests
import os

station_ids = {
    "East Foothills": "MILL1",
    "Lower Cajon Pass": "SCAC1",
    "Yucaipa Area": "OGVC1"
}

fallback_coords = {
    "East Foothills": (34.07984, -117.04676),
    "Lower Cajon Pass": (34.18214, -117.38511),
    "Yucaipa Area": (34.03049, -117.04311)
}

MESOWEST_TOKEN = "a8aecb222ab940439f4260cc6abc83ed"
snapshot_file = "airs_snapshot_log.csv"


def get_raws_data(station_id):
    try:
        url = f"https://api.synopticdata.com/v2/stations/nearesttime?stid={station_id}&vars=air_temp,relative_humidity,wind_speed&token={MESOWEST_TOKEN}"
        response = requests.get(url)
        data = response.json()
        obs = data['STATION'][0]['OBSERVATIONS']

        # Corrected value extraction and unit conversions
        temp_c = obs['air_temp_value_1']['value']
        rh = obs['relative_humidity_value_1']['value']
        wind_ms = obs['wind_speed_value_1']['value']

        temp_f = round(temp_c * 9 / 5 + 32, 1)
        wind_mph = round(wind_ms * 2.23694, 1)

        return {
            "RH": rh,
            "Temp": temp_f,
            "Wind": wind_mph,
            "FuelMoisture": 7,
            "Source": "RAWS (MesoWest)"
        }
    except Exception as e:
        print("RAWS error:", e)
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

def run_tier_logic(data, plume, suppression, wui):
    rh = data["RH"]
    temp = data["Temp"]
    wind = data["Wind"]
    fm = data["FuelMoisture"]
    source = data.get("Source", "Unknown")

    tier = "Tier 2"
    confidence = 3
    notes = []

    if rh < 25 and temp > 90 and fm < 10:
        tier = "Tier 3"
        confidence = 3
        notes.append("Base Tier 3: RH < 25, Temp > 90, FM < 10")

    if rh < 20 and temp > 95 and fm < 9 and wind >= 10:
        tier = "Tier 4"
        confidence = 4
        notes.append("Tier 4: adds wind alignment")

    if rh < 15 and temp > 100 and fm < 8:
        tier = "Tier 5"
        confidence = 5
        notes.append("Tier 5: critical fire weather")

    if tier == "Tier 3" and wind >= 15:
        tier = "Tier 4"
        confidence = min(confidence + 1, 5)
        notes.append("Wind-aligned slope boost")

    if plume and tier in ["Tier 3", "Tier 4"]:
        tier = "Tier 5"
        confidence = 5
        notes.append("Plume-confirmed override")

    if suppression:
        notes.append("Suppression presence noted")
        confidence = max(confidence - 1, 2)

    if wui:
        confidence += 1
        notes.append("WUI exposure +1 confidence")

    if "Fallback" in source:
        confidence = min(confidence, 4)
        notes.append("Fallback data used")

    return tier, min(confidence, 5), ", ".join(notes)

def log_snapshot(zone, rh, temp, wind, fm, tier, confidence, source, plume, suppression, wui, learning, camera_url, notes):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    snapshot = pd.DataFrame([[now, zone, rh, temp, wind, fm, tier, confidence, source, plume, suppression, wui, learning, camera_url, notes]],
                            columns=["Timestamp", "Zone", "RH", "Temp", "Wind", "FM", "Tier", "Confidence", "Source", "PlumeFlag", "Suppression", "WUI", "LearningTag", "CameraURL", "Notes"])
    if os.path.exists(snapshot_file):
        snapshot.to_csv(snapshot_file, mode='a', header=False, index=False)
    else:
        snapshot.to_csv(snapshot_file, index=False)

# Streamlit UI
st.title("AIRS Lite – Mobile Tier Forecaster")
zone = st.selectbox("Select Zone", list(station_ids.keys()))
plume = st.checkbox("Plume Confirmed?")
suppression = st.checkbox("Suppression Present?")
wui = st.checkbox("High WUI Threat?")
learning = st.checkbox("Mark as Learning Case")
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
        lat, lon = fallback_coords[zone]
        data = get_open_meteo_data(lat, lon)
        if data is None:
            st.error("No weather data available. Use manual mode.")
            st.stop()

st.subheader("Forecast Snapshot")
st.write(f"RH: {data['RH']}% | Temp: {data['Temp']}°F | Wind: {data['Wind']} mph | FM: ~{data['FuelMoisture']}%")
st.caption(f"Source: {data['Source']}")

tier, confidence, notes = run_tier_logic(data, plume, suppression, wui)

st.subheader("AIRS Tier Output")
st.write(f"**Tier:** {tier}")
st.write(f"**Confidence:** {confidence}/5")
st.write(f"**Notes:** {notes}")

if st.button("Export Snapshot"):
    log_snapshot(zone, data["RH"], data["Temp"], data["Wind"], data["FuelMoisture"], tier, confidence, data["Source"], plume, suppression, wui, learning, camera_url, notes)
    st.success("Snapshot exported.")

if st.checkbox("View Tier Timeline Log"):
    if os.path.exists(snapshot_file):
        df = pd.read_csv(snapshot_file)
        st.dataframe(df.tail(20))
    else:
        st.info("No snapshot history available yet.")
