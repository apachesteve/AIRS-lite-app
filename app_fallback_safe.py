
# AIRS Lite App – Tier Forecaster with Full Weather Fallback (v1.2.1)

import streamlit as st
import pandas as pd
import requests
import datetime
import os

MESOWEST_TOKEN = "a8aecb222ab940439f4260cc6abc83ed"
snapshot_file = "airs_snapshot_log.csv"

zone_centers = {
    "Lower Cajon Pass": {"lat": 34.18214, "lon": -117.38511},
    "East Foothills": {"lat": 34.07984, "lon": -117.04676},
    "Owens Valley": {"lat": 37.3639, "lon": -118.3950}
}

# RAWS fetch with 10-hr fuel moisture
def get_raws_data(lat, lon):
    try:
        url = f"https://api.synopticdata.com/v2/stations/nearesttime?within=30&lat={lat}&lon={lon}&vars=air_temp,relative_humidity,wind_speed,fuel_moisture_10hr_value&token={MESOWEST_TOKEN}"
        r = requests.get(url).json()
        if "STATION" not in r or len(r["STATION"]) == 0:
            return None
        o = r["STATION"][0]["OBSERVATIONS"]
        return {
            "RH": o.get("relative_humidity_set_1"),
            "Temp": o.get("air_temp_set_1"),
            "Wind": o.get("wind_speed_set_1"),
            "FuelMoisture": o.get("fuel_moisture_10hr_value", 9),
            "Source": "RAWS (MesoWest)"
        }
    except:
        return None

# Open-Meteo fallback
def get_open_meteo_data(lat, lon):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,relative_humidity_2m,windspeed_10m&forecast_days=1"
        r = requests.get(url).json()
        rh = r['hourly']['relative_humidity_2m'][13]
        temp = r['hourly']['temperature_2m'][13]
        wind = r['hourly']['windspeed_10m'][13]
        return {
            "RH": rh,
            "Temp": temp,
            "Wind": wind,
            "FuelMoisture": 9,
            "Source": "Fallback: Open-Meteo"
        }
    except:
        return None

# Tier logic with plume precursor and FM input
def run_tier_logic(data, plume_detected):
    rh = data["RH"]
    temp = data["Temp"]
    wind = data["Wind"]
    fm = data["FuelMoisture"]
    source = data["Source"]

    tier = "Tier 2"
    confidence = 3
    precursors = 0
    notes = []

    if rh < 25 and temp > 90 and fm < 10:
        tier = "Tier 3"

    if rh < 20 and temp > 95 and fm < 9 and wind >= 10:
        tier = "Tier 4"
        confidence = 4
        notes.append("Tier 4 threshold exceeded")

    if rh < 15 and temp > 100 and fm < 8:
        precursors += 1
    if rh < 20:
        precursors += 1
    if temp > 95:
        precursors += 1
    if wind >= 15:
        precursors += 1
    if fm < 8:
        precursors += 1

    if precursors >= 5:
        tier = "Tier 5"
        confidence = 5
        notes.append("Plume precursors active (5+ conditions met)")

    if plume_detected:
        tier = "Tier 5"
        confidence = 5
        notes.append("Tier 5 override from confirmed plume")

    if "Fallback" in source:
        confidence = min(confidence, 4)
        notes.append("Confidence capped due to fallback source")

    return tier, confidence, False, "; ".join(notes)

# Logging
def log_snapshot(zone, tier, confidence, hold, notes):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    snapshot = pd.DataFrame([[now, zone, tier, confidence, hold, notes]],
                            columns=["Timestamp", "Zone", "Tier", "Confidence", "Hold", "Notes"])
    if os.path.exists(snapshot_file):
        snapshot.to_csv(snapshot_file, mode='a', header=False, index=False)
    else:
        snapshot.to_csv(snapshot_file, index=False)

# UI
st.title("AIRS Lite – v1.2.1")
offline_mode = st.checkbox("Offline Mode (Manual Entry)", value=False)
zone = st.selectbox("Select Zone", list(zone_centers.keys()))
plume_detected = st.checkbox("Plume Confirmed (Observed Fire Only)", value=False)

if offline_mode:
    st.subheader("Manual Entry")
    rh = st.number_input("RH (%)", 0, 100, 20)
    temp = st.number_input("Temperature (°F)", 30, 130, 95)
    wind = st.number_input("Wind (mph)", 0, 100, 10)
    fm = st.number_input("Fuel Moisture (%)", 0, 30, 9)
    data = {"RH": rh, "Temp": temp, "Wind": wind, "FuelMoisture": fm, "Source": "Manual Entry"}
else:
    lat, lon = zone_centers[zone]["lat"], zone_centers[zone]["lon"]
    data = get_raws_data(lat, lon)
    if not data:
        data = get_open_meteo_data(lat, lon)
    if not data:
        data = {"RH": 0, "Temp": 0, "Wind": 0, "FuelMoisture": 0, "Source": "No data"}

st.subheader("Inputs")
st.write(f"RH: {data['RH']}% | Temp: {data['Temp']}°F | Wind: {data['Wind']} mph | FM: {data['FuelMoisture']}%")
st.info(f"Data Source: {data['Source']}")

tier, confidence, hold, notes = run_tier_logic(data, plume_detected)

st.subheader("AIRS Output")
st.write(f"**Tier:** {tier}")
st.write(f"**Confidence:** {confidence}/5")
st.write(f"**Suppression Hold:** {'✅ Active' if hold else '❌ Not Active'}")
st.write(f"**Notes:** {notes}")

if st.button("📤 Export Snapshot"):
    log_snapshot(zone, tier, confidence, hold, notes)
    st.success("Snapshot exported!")

if st.button("🔍 Analyze Snapshot"):
    st.subheader("Snapshot Analysis")
    st.write(f"Tier: {tier}, Confidence: {confidence}/5")
    st.write(notes)
