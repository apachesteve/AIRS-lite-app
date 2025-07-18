
# AIRS Lite App – v1.2.1 with Dynamic RAWS + Fuel Moisture + Owens Valley Support

import streamlit as st
import pandas as pd
import requests
import datetime
import os

MESOWEST_TOKEN = "a8aecb222ab940439f4260cc6abc83ed"
snapshot_file = "airs_snapshot_log.csv"

# Zones with lat/lon for dynamic RAWS pulls
zone_centers = {
    "Lower Cajon Pass": {"lat": 34.18214, "lon": -117.38511},
    "East Foothills": {"lat": 34.07984, "lon": -117.04676},
    "Owens Valley": {"lat": 37.3639, "lon": -118.3950}
}

# Pull RAWS data including 10-hr fuel moisture
def get_raws_data_with_fm(lat, lon):
    try:
        url = f"https://api.synopticdata.com/v2/stations/nearesttime?within=30&lat={lat}&lon={lon}&vars=air_temp,relative_humidity,wind_speed,fuel_moisture_10hr_value&token={MESOWEST_TOKEN}"
        response = requests.get(url)
        data = response.json()
        obs = data['STATION'][0]['OBSERVATIONS']
        return {
            "RH": obs.get('relative_humidity_set_1'),
            "Temp": obs.get('air_temp_set_1'),
            "Wind": obs.get('wind_speed_set_1'),
            "FuelMoisture": obs.get('fuel_moisture_10hr_value', 9),
            "Source": "RAWS (MesoWest)"
        }
    except:
        return None

# Tier logic using plume precursor logic + FM integration
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
        confidence = 3

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

# Snapshot logging
def log_snapshot(zone, tier, confidence, hold, notes):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    snapshot = pd.DataFrame([[now, zone, tier, confidence, hold, notes]],
                            columns=["Timestamp", "Zone", "Tier", "Confidence", "Hold", "Notes"])
    if os.path.exists(snapshot_file):
        snapshot.to_csv(snapshot_file, mode='a', header=False, index=False)
    else:
        snapshot.to_csv(snapshot_file, index=False)

# Streamlit UI
current_date = datetime.datetime.now().strftime("%B %d, %Y")
st.title(f"AIRS Lite – Operational Tier Forecaster")
st.markdown("_Version 1.2.1 • RAWS-integrated • Fuel Moisture Aware • Owens Valley Ready_")
st.markdown(f"**Build Date:** {current_date}")

offline_mode = st.checkbox("🛠️ Offline Mode (Manual Entry)", value=False)
zone = st.selectbox("Select Zone", list(zone_centers.keys()))
plume_detected = st.checkbox("Plume Confirmed (Observed Fire Only)", value=False)

if offline_mode:
    st.subheader("Manual Entry")
    rh = st.number_input("Relative Humidity (%)", min_value=0, max_value=100, value=20)
    temp = st.number_input("Temperature (°F)", min_value=30, max_value=130, value=95)
    wind = st.number_input("Wind Speed (mph)", min_value=0, max_value=100, value=10)
    fm = st.number_input("10-hr Fuel Moisture (%)", min_value=0, max_value=30, value=9)
    data = {
        "RH": rh,
        "Temp": temp,
        "Wind": wind,
        "FuelMoisture": fm,
        "Source": "Manual Entry"
    }
else:
    coords = zone_centers[zone]
    data = get_raws_data_with_fm(coords["lat"], coords["lon"])
    if not data:
        data = {"RH": 0, "Temp": 0, "Wind": 0, "FuelMoisture": 0, "Source": "No data"}

st.subheader("Weather Conditions")
st.write(f"**RH:** {data['RH']}%")
st.write(f"**Temp:** {data['Temp']}°F")
st.write(f"**Wind:** {data['Wind']} mph")
st.write(f"**10-hr Fuel Moisture:** {data['FuelMoisture']}%")
st.info(f"**Source:** {data['Source']}")

tier, confidence, hold, notes = run_tier_logic(data, plume_detected)

st.subheader("AIRS Tier Output")
st.write(f"**Tier:** {tier}")
st.write(f"**Confidence:** {confidence}/5")
st.write(f"**Suppression Hold:** {'✅ Active' if hold else '❌ Not Active'}")
st.write(f"**Notes:** {notes}")

if st.button("📤 Export Snapshot"):
    log_snapshot(zone, tier, confidence, hold, notes)
    st.success("Snapshot exported!")

if st.button("🔍 Analyze Snapshot"):
    st.subheader("AIRS Snapshot Analysis")
    st.write(f"Zone: {zone}")
    st.write(f"Tier: {tier}")
    st.write(f"Confidence: {confidence}/5")
    st.write(f"Notes: {notes}")
