import streamlit as st
import gpxpy
import folium
from streamlit_folium import st_folium
import base64
import os
import glob
from datetime import datetime, timedelta
import pandas as pd
import math
import time

# --- KONFIGURATION ---
APP_VERSION = "1.63"        # Doku: Erklärung für 2. Monitor hinzugefügt
HEADER_HEIGHT_PIXELS = 450  
ROWS_PER_PAGE = 10          

# --- BENUTZERHANDBUCH INHALT (AKTUALISIERT) ---
MANUAL_MD = """
## 📘 Benutzerhandbuch

### 1. Einleitung
Der **LKW Touren Viewer Pro** visualisiert GPX-Routen, berechnet Standzeiten und ermöglicht den Datenexport.

### 2. Bedienung

#### 📂 Tour laden
* **Automatisch:** Links oben sehen Sie alle `DL*.gpx` Dateien im Ordner. Ein Klick lädt die Tour.
* **Upload:** Rechts oben ("Browse files") können Sie eigene GPX-Dateien hochladen (max. 200 MB).

#### 🗺️ Karte & 2. Monitor
* **Navigation:** Verschieben und Zoomen Sie wie gewohnt.
* **Marker:** 🟢 Start | 🏁 Ziel | 🔵 Kunde | 🔴 Ausgewählt
* **2. Monitor Nutzung:** 1. Klicken Sie auf **"🌍 Karte für 2. Monitor speichern"**.
    2. Es wird eine Datei namens `LKW_Tour.html` heruntergeladen.
    3. Öffnen Sie diese Datei per Doppelklick (sie startet in Ihrem Standard-Browser).
    4. Ziehen Sie dieses Browser-Fenster auf Ihren zweiten Bildschirm. So haben Sie die Karte groß im Blick, während Sie auf dem Hauptschirm die Liste bearbeiten.

#### 📋 Kundenliste & Analyse
* **Auswahl:** Klicken Sie auf eine Zeile in der Tabelle unten rechts, um auf den Kunden zu zoomen.
* **Export:** Der Button **"📄 Export Standzeiten"** erstellt eine Excel-kompatible CSV-Datei (Trennzeichen `;`) mit Ankunft, Abfahrt und Dauer.

#### ⚙️ Ansicht
* **Sidebar:** Mit **"Sidebar ein/aus"** können Sie die Kundenliste ausblenden, um die Karte zu vergrößern.
"""

def get_base64_of_bin_file(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

def load_customer_db():
    filename = "KND.STM"
    if not os.path.exists(filename):
        return None
    try:
        df = pd.read_csv(filename, sep=None, engine='python', dtype=str, encoding='latin1')
        df.columns = df.columns.str.strip()
        if 'NUMBER' in df.columns and 'NAME' in df.columns:
            return dict(zip(df['NUMBER'].str.strip(), df['NAME'].str.strip()))
        return None
    except:
        return None

def process_gpx_data(file, customer_db=None):
    file.seek(0) 
    gpx = gpxpy.parse(file)
    points = []
    all_gpx_points = [] 
    
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                points.append((point.latitude, point.longitude))
                all_gpx_points.append(point)
    
    if not points:
        for route in gpx.routes:
            for point in route.points:
                points.append((point.latitude, point.longitude))
                all_gpx_points.append(point)

    moving_data = gpx.get_moving_data()
    dist_km = moving_data.moving_distance / 1000.0
    moving_time_seconds = moving_data.moving_time
    
    avg_speed = dist_km / (moving_time_seconds / 3600.0) if moving_time_seconds > 0 else 0.0

    start_time_str = "-"
    end_time_str = "-"
    date_str = ""
    customer_stops = []
    
    try:
        bounds = gpx.get_time_bounds()
        if bounds.start_time and bounds.end_time:
            t_start = bounds.start_time + timedelta(hours=2)
            t_end = bounds.end_time + timedelta(hours=2)
            start_time_str = t_start.strftime("%H:%M Uhr")
            end_time_str = t_end.strftime("%H:%M Uhr")
            date_str = t_start.strftime("%d.%m.%Y")

        for i, point in enumerate(all_gpx_points):
            if point.name and point.name.startswith("Customer:"):
                customer_id = point.name.replace("Customer:", "").strip()
                end_ts = point.time
                start_ts = end_ts 
                j = i - 1
                while j >= 0:
                    prev_point = all_gpx_points[j]
                    if prev_point.latitude == point.latitude and prev_point.longitude == point.longitude:
                        start_ts = prev_point.time 
                        j -= 1
                    else:
                        break
                
                duration = int((end_ts - start_ts).total_seconds() / 60)
                arrival_time = (start_ts + timedelta(hours=2)).strftime("%H:%M:%S")
                departure_time = (end_ts + timedelta(hours=2)).strftime("%H:%M:%S")
                
                customer_name = customer_db.get(customer_id, "Unbekannt") if customer_db else ""
                
                stop_data = {
                    "Kunden Nr.": customer_id,
                    "Ankunft": arrival_time,
                    "Abfahrt": departure_time,
                    "Dauer (Min)": duration,
                    "Lat": point.latitude,
                    "Lon": point.longitude
                }
                if customer_db:
                    stop_data["Name"] = customer_name
                
                customer_stops.append(stop_data)

    except Exception as e:
        print(f"Fehler: {e}")
        pass

    return {
        "points": points,
        "dist_km": dist_km,
        "avg_speed": avg_speed,
        "start_time": start_time_str,
        "end_time": end_time_str,
        "date_str": date_str,
        "customer_stops": customer_stops
    }

def get_local_gpx_files_info():
    file_list = []
    for f in os.listdir('.'):
        if os.path.isfile(f) and f.upper().startswith('DL') and f.upper().endswith('.GPX'):
            mod_time = os.path.getmtime(f)
            dt_obj = datetime.fromtimestamp(mod_time)
            date_str = dt_obj.strftime("%d.%m.%Y %H:%M")
            file_list.append({"Dateiname": f, "Datum": date_str, "timestamp": mod_time})
    file_list.sort(key=lambda x: x["timestamp"], reverse=True)
    return file_list

@st.fragment(run_every=60)
def file_selector_fragment():
    files_info = get_local_gpx_files_info()
    if files_info:
        count = len(files_info)
        st.markdown(f"<div style='color:white; font-size:0.9em; margin-bottom:3px;'>📂 <b>{count}</b> Touren gefunden (Auto-Update: 60s)</div>", unsafe_allow_html=True)
        df_files = pd.DataFrame(files_info)[["Dateiname", "Datum"]]
        styled_df_files = df_files.style.set_properties(**{'background-color': 'rgba(255,255,255,0.1)', 'color': 'white', 'border-color': 'rgba(255,255,255,0.1)', 'cursor': 'pointer'})
        
        selection = st.dataframe(
            styled_df_files, 
            width="stretch", 
            hide_index=True, 
            column_order=["Dateiname", "Datum"], 
            selection_mode="single-row", 
            on_select="rerun", 
            key="file_selection_table", 
            height=180
        )
        
        if len(selection.selection.rows) > 0:
            index = selection.selection.rows[0]
            selected_file = df_files.iloc[index]["Dateiname"]
            if st.session_state.get('selected_local_file') != selected_file:
                st.session_state.selected_local_file = selected_file
                st.session_state.last_selection_ts = time.time()
                st.rerun()
    else:
        st.markdown("<div style='color:white; font-size:0.9em;'>Keine DL*.GPX Dateien gefunden.</div>", unsafe_allow_html=True)

# --- DIALOG FUNKTION (HILFE) ---
@st.dialog("Benutzerhandbuch")
def show_help_dialog():
    st.markdown(MANUAL_MD)
    if st.button("Schließen"):
        st.rerun()

def main():
    st.set_page_config(page_title="LKW Touren Viewer Pro", page_icon="🚚", layout="wide")
    
    if 'show_right_sidebar' not in st.session_state: st.session_state.show_right_sidebar = True
    if 'page_number' not in st.session_state: st.session_state.page_number = 0
    if 'selected_customer_id' not in st.session_state: st.session_state.selected_customer_id = None
    if 'selected_local_file' not in st.session_state: st.session_state.selected_local_file = None
    if 'last_upload_ts' not in st.session_state: st.session_state.last_upload_ts = 0.0
    if 'last_selection_ts' not in st.session_state: st.session_state.last_selection_ts = 0.0
    if 'tour_data' not in st.session_state: st.session_state.tour_data = None
    if 'loaded_file_name' not in st.session_state: st.session_state.loaded_file_name = None

    customer_db = load_customer_db()
    has_customer_names = customer_db is not None

    logo_filename = "movisl.jpg"
    logo_base64 = ""
    if os.path.exists(logo_filename):
        logo_base64 = get_base64_of_bin_file(logo_filename)

    st.markdown(f"""
        <style>
            .stApp {{ background-color: #047761; }}
            header[data-testid="stHeader"], [data-testid="stElementToolbar"] {{ display: none !important; }}
            
            .custom-header {{
                position: fixed; top: 0; left: 0; width: 100%; height: 60px;
                background-color: white; padding: 5px 30px;
                z-index: 1000000; box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                display: flex; align-items: center;
            }}
            .custom-header img {{ height: 45px; width: auto; }}
            .version {{ margin-left: auto; color: #047761; font-weight: bold; font-family: sans-serif; }}

            div[data-testid="stVerticalBlock"] > div:has(div#fixed-controls-anchor) {{
                position: fixed; top: 60px; left: 0; width: 100%;
                background-color: #047761; z-index: 99999;
                padding-left: 2rem; padding-right: 2rem; padding-bottom: 5px;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }}
            .block-container {{ padding-top: {HEADER_HEIGHT_PIXELS}px !important; padding-bottom: 0px !important; }}
            
            h1, h2, h3, h4, p, div, label, .stMarkdown, .stMetricValue, .stMetricLabel {{ color: white !important; }}
            .custom-header * {{ color: #047761 !important; }}
            div[data-testid="stButton"] button p, div[data-testid="stDownloadButton"] button p {{ color: #047761 !important; }}
            
            [data-testid='stFileUploader'] section > div > div > span {{ display: none !important; }}
            [data-testid='stFileUploader'] section > div > div > small {{ display: none !important; }}
            
            [data-testid='stFileUploader'] section > div > div::after {{
                content: "GPX Datei hier ablegen ( oder links auswählen max. 200 MB )";
                white-space: pre; color: white; text-align: center; display: block; font-weight: bold; font-size: 14px;
            }}

            div[data-testid="stButton"] button, div[data-testid="stDownloadButton"] button {{
                background-color: white !important; color: #047761 !important; border-radius: 6px !important; font-weight: bold !important;
            }}
            
            [data-testid="stDataFrame"] thead tr th, [data-testid="stDataFrame"] thead tr {{
                background-color: rgba(255,255,255,0.1) !important; color: white !important;
            }}
            
            /* Style für das Modal-Fenster (Dialog) */
            div[data-testid="stDialog"] {{
                background-color: #047761 !important;
                color: white !important;
            }}
        </style>
    """, unsafe_allow_html=True)

    # --- HEADER ---
    version_html = f'<div class="version">v{APP_VERSION}</div>'
    if logo_base64:
        st.markdown(f'<div class="custom-header"><img src="data:image/jpeg;base64,{logo_base64}">{version_html}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="custom-header"><h2 style="color:#047761!important; margin:0; font-size:24px;">movis</h2>{version_html}</div>', unsafe_allow_html=True)

    with st.container():
        st.markdown('<div id="fixed-controls-anchor"></div>', unsafe_allow_html=True)
        st.markdown("<h3 style='text-align: center; color: white; margin-top: 5px; margin-bottom: 5px;'>🚚 LKW Touren Viewer Pro</h3>", unsafe_allow_html=True)
        
        # LAYOUT
        head_col1, head_col2, head_col3 = st.columns([5, 4, 1], gap="small")
        
        with head_col1:
            file_selector_fragment()
            
        with head_col2:
            st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True) 
            def on_upload_change(): st.session_state.last_upload_ts = time.time()
            uploaded_file = st.file_uploader("Upload", type=['gpx'], label_visibility="collapsed", on_change=on_upload_change)
            
        with head_col3:
            st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
            if st.button("❓", help="Benutzerhandbuch öffnen"):
                show_help_dialog()

        # --- LOGIK: DATEI LADEN ---
        file_to_process = None
        file_name_display = ""
        is_upload_newer = st.session_state.last_upload_ts > st.session_state.last_selection_ts
        
        if uploaded_file is not None and is_upload_newer:
            file_to_process = uploaded_file
            file_name_display = uploaded_file.name
        elif st.session_state.selected_local_file:
            try:
                if os.path.exists(st.session_state.selected_local_file):
                    file_to_process = open(st.session_state.selected_local_file, 'rb')
                    file_name_display = st.session_state.selected_local_file
            except: pass
        
        if file_to_process:
            if st.session_state.loaded_file_name != file_name_display:
                data = process_gpx_data(file_to_process, customer_db)
                st.session_state.tour_data = data
                st.session_state.loaded_file_name = file_name_display
        
    # --- ANZEIGE ---
    if st.session_state.tour_data and st.session_state.tour_data["points"]:
        data = st.session_state.tour_data
        points = data["points"]
        customer_stops = data["customer_stops"]

        # STATISTIK
        col1, col2, col3, col4 = st.columns(4)
        box_style = "color: white; text-align: center; background: rgba(255,255,255,0.1); padding: 4px; border-radius: 8px;"
        with col1: st.markdown(f"<div style='{box_style}'><div style='font-size:0.9em; opacity:0.8'>⏱️ Start</div><div style='font-size:1.1em; font-weight:bold'>{data['start_time']}</div></div>", unsafe_allow_html=True)
        with col2: st.markdown(f"<div style='{box_style}'><div style='font-size:0.9em; opacity:0.8'>🏁 Ende</div><div style='font-size:1.1em; font-weight:bold'>{data['end_time']}</div></div>", unsafe_allow_html=True)
        with col3: st.markdown(f"<div style='{box_style}'><div style='font-size:0.9em; opacity:0.8'>📏 Distanz</div><div style='font-size:1.1em; font-weight:bold'>{data['dist_km']:.2f} km</div></div>", unsafe_allow_html=True)
        with col4: st.markdown(f"<div style='{box_style}'><div style='font-size:0.9em; opacity:0.8'>Ø Geschw.</div><div style='font-size:1.1em; font-weight:bold'>{data['avg_speed']:.1f} km/h</div></div>", unsafe_allow_html=True)
        
        st.markdown("<div style='height: 10px'></div>", unsafe_allow_html=True)
        
        # --- KARTE KONFIGURIEREN ---
        mid_p = points[len(points)//2]
        zoom_val = 12
        
        if st.session_state.selected_customer_id:
            for stop in customer_stops:
                if stop['Kunden Nr.'] == st.session_state.selected_customer_id:
                    mid_p = [stop['Lat'], stop['Lon']]
                    zoom_val = 16 
                    break
        
        # LINKS: Buttons
        bcol_left, bcol_right = st.columns([1, 1])
        with bcol_left:
            m = folium.Map(location=mid_p, zoom_start=zoom_val)
            folium.PolyLine(points, color="red", weight=5, opacity=0.8).add_to(m)
            for stop in customer_stops:
                is_sel = (stop['Kunden Nr.'] == st.session_state.selected_customer_id)
                folium.Marker([stop['Lat'], stop['Lon']], tooltip=stop['Kunden Nr.'], icon=folium.Icon(color="red" if is_sel else "blue", icon="star" if is_sel else "user", prefix="fa")).add_to(m)
            map_html = m.get_root().render()
            st.download_button("🌍 Karte für 2. Monitor speichern", map_html, "LKW_Tour.html", "text/html")
        
        # RECHTS: Buttons
        with bcol_right:
            sub_c1, sub_c2 = st.columns([1, 1])
            with sub_c1:
                if customer_stops:
                    if st.button("Sidebar ein/aus"): 
                        st.session_state.show_right_sidebar = not st.session_state.show_right_sidebar
                        st.rerun()
            with sub_c2:
                if customer_stops:
                    df_export = pd.DataFrame(customer_stops).drop(columns=['Lat', 'Lon'], errors='ignore')
                    csv = df_export.to_csv(index=False, sep=';', encoding='utf-16').encode('utf-16')
                    st.download_button(label="📄 Export Standzeiten", data=csv, file_name=f"Standzeiten_{data['date_str']}.csv", mime="text/csv")

        # INHALT
        if st.session_state.show_right_sidebar and customer_stops:
            c_map, c_list = st.columns([1, 1])
            with c_map: 
                st.markdown("<div style='margin-top: -15px;'></div>", unsafe_allow_html=True)
                st_folium(m, height=800, use_container_width=True) 
            with c_list:
                st.markdown("<div style='margin-top: -10px;'></div>", unsafe_allow_html=True)
                st.markdown("<div style='text-align: center; color: white; margin-top: 0; margin-bottom: 5px; font-weight: bold; font-size: 1.1em;'>📋 Kundenliste</div>", unsafe_allow_html=True)

                total_stops = len(customer_stops)
                num_pages = math.ceil(total_stops / ROWS_PER_PAGE)
                start_idx = st.session_state.page_number * ROWS_PER_PAGE
                current_batch = customer_stops[start_idx : start_idx + ROWS_PER_PAGE]
                df_stops = pd.DataFrame(current_batch)
                cols = ["Kunden Nr.", "Ankunft", "Abfahrt", "Dauer (Min)"]
                if has_customer_names: cols.insert(1, "Name")
                
                sel = st.dataframe(df_stops.style.set_properties(**{'background-color': '#047761', 'color': 'white'}), width="stretch", hide_index=True, column_order=cols, selection_mode="single-row", on_select="rerun", key=f"tbl_{st.session_state.page_number}")
                if sel.selection.rows:
                    sel_cust = current_batch[sel.selection.rows[0]]["Kunden Nr."]
                    if st.session_state.selected_customer_id != sel_cust:
                        st.session_state.selected_customer_id = sel_cust
                        st.rerun()

                n1, n2, n3 = st.columns([1, 2, 1])
                with n1: 
                    if st.session_state.page_number > 0 and st.button("⬅️"): st.session_state.page_number -= 1; st.rerun()
                with n2: st.markdown(f"<div style='text-align:center;'>Seite {st.session_state.page_number+1}/{num_pages}</div>", unsafe_allow_html=True)
                with n3:
                    if st.session_state.page_number < num_pages-1 and st.button("➡️"): st.session_state.page_number += 1; st.rerun()
        else: st_folium(m, height=800, use_container_width=True)

if __name__ == "__main__": main()