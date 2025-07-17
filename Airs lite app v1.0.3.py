
import streamlit as st
import pandas as pd
import datetime
import requests
import os

station_ids = {
    "East Foothills": "MILL1",
    "Lower Cajon Pass": "DVOC1",
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
        notes.append("Tier 4: wind-aligned and elevated")

    if rh < 15 and temp > 100 and fm < 8:
        tier = "Tier 5"
        confidence = 5
        notes.append("Tier 5: extreme RH/Temp/Fuel")

    if tier == "Tier 3" and wind >= 15:
        tier = "Tier 4"
        confidence = min(confidence + 1, 5)
        notes.append("Wind-aligned slope boost")

    if plume and tier in ["Tier 3", "Tier 4"]:
        tier = "Tier 5"
        confidence = 5
        notes.append("Plume-confirmed override")

    if suppression:
        confidence = max(confidence - 1, 2)
        notes.append("Suppression noted")

    if wui:
        confidence += 1
        notes.append("WUI exposure increases confidence")

    if "Fallback" in source:
        confidence = min(confidence, 4)
        notes.append("Fallback data used")

    return tier, min(confidence, 5), ", ".join(notes)

def analyze_snapshot(zone, rh, temp, wind, fm, plume, suppression, wui):
    tier, confidence, _ = run_tier_logic({"RH": rh, "Temp": temp, "Wind": wind, "FuelMoisture": fm}, plume, suppression, wui)
    rationale = []
    learning_tag = False

    if rh < 25 and temp > 90 and fm < 10:
        rationale.append("Base Tier 3: RH < 25%, Temp > 90°F, FM < 10%")
    if rh < 20 and temp > 95 and fm < 9 and wind >= 10:
        rationale.append("Tier 4: wind ≥10 mph supports elevated spread")
    if rh < 15 and temp > 100 and fm < 8:
        rationale.append("Tier 5: extreme RH/Temp/Fuel combination")
    if tier == "Tier 4" and wind >= 15:
        rationale.append("Wind-aligned slope: escalates Tier 3 to Tier 4")
    if plume and tier in ["Tier 3", "Tier 4"]:
        rationale.append("Plume-confirmed override triggered")
    if suppression:
        rationale.append("Suppression present: confidence reduced")
    if wui:
        rationale.append("WUI exposure: confidence increased")
    if tier == "Tier 5" and plume and not suppression:
        learning_tag = True
        rationale.append("Learning Tag: Tier 5 + plume + no suppression")

    output = f"**Zone:** {zone}\n**Conditions:** RH {rh}%, Temp {temp}°F, Wind {wind} mph, FM {fm}%\n"
    output += f"**Tier:** {tier} | **Confidence:** {confidence}/5\n"
    output += "**Rationale:**\n" + "\n".join(f"- {r}" for r in rationale)
    if learning_tag:
        output += "\n\n🧠 This case is flagged for learning review."
    return output

# UI Layout
st.title("AIRS Lite – GPT-Integrated Tier App")
zone = st.selectbox("Select Zone", list(station_ids.keys()))
plume = st.checkbox("Plume Confirmed?")
suppression = st.checkbox("Suppression Present?")
wui = st.checkbox("High WUI Threat?")
learning = st.checkbox("Mark as Learning Case")
manual_entry = st.checkbox("Manual Weather Entry")
camera_url = st.text_input("Camera URL (optional):", "")

if manual_entry:
    rh = st.number_input("RH (%)", 0, 100, 21)
    temp = st.number_input("Temperature (°F)", 50, 130, 93)
    wind = st.number_input("Wind Speed (mph)", 0, 50, 10)
    fm = st.number_input("10-hr Fuel Moisture (%)", 0, 30, 9)
    data = {"RH": rh, "Temp": temp, "Wind": wind, "FuelMoisture": fm, "Source": "Manual Entry"}
else:
    data = get_raws_data(station_ids[zone])
    if data is None:
        lat, lon = fallback_coords[zone]
        data = get_open_meteo_data(lat, lon)
        if data is None:
            st.error("No weather data available. Use manual mode.")
            st.stop()

st.subheader("Forecast Snapshot")
st.write(f"RH: {data['RH']}%, Temp: {data['Temp']}°F, Wind: {data['Wind']} mph, FM: {data['FuelMoisture']}%")
st.caption(f"Source: {data['Source']}")

tier, confidence, notes = run_tier_logic(data, plume, suppression, wui)

st.subheader("AIRS Output")
st.write(f"**Tier:** {tier}")
st.write(f"**Confidence:** {confidence}/5")
st.write(f"**Notes:** {notes}")

if st.button("Analyze Snapshot"):
    st.markdown(analyze_snapshot(zone, data["RH"], data["Temp"], data["Wind"], data["FuelMoisture"], plume, suppression, wui))

if st.checkbox("View Tier Timeline Log"):
    if os.path.exists(snapshot_file):
        df = pd.read_csv(snapshot_file)
        st.dataframe(df.tail(20))
    else:
        st.info("No snapshot history available yet.")
