import streamlit as st
import streamlit.components.v1 as components
import gpxpy
import folium
import base64
import os
import glob
from datetime import datetime, timedelta
import pandas as pd
import math
import time

# --- KONFIGURATION ---
APP_VERSION = "1.85"        # Fix: Beschriftung für "Sidebar ein/aus" wiederhergestellt
HEADER_HEIGHT_PIXELS = 340  
ROWS_PER_PAGE = 10          

# --- SPRACH-WÖRTERBUCH ---
TRANSLATIONS = {
    "Deutsch": {
        "page_title": "LKW Touren Viewer Pro",
        "tours_found": "📂 Aktuell gefundene Touren: <b>{count}</b> (Auto-Update: 60s)",
        "no_files": "Keine GPX Dateien.",
        "upload_text": "GPX Datei hier ablegen (max. 200 MB)",
        "manual_btn_help": "Handbuch",
        "manual_title": "Benutzerhandbuch",
        "stats_start": "⏱️ Start",
        "stats_end": "🏁 Ende",
        "stats_dist": "📏 Distanz",
        "stats_speed": "Ø Geschw.",
        "btn_save_map": "🌍 Karte für 2. Monitor speichern",
        "btn_sidebar": "Sidebar ein/aus",  # WIEDER EINGEFÜGT
        "btn_export": "📄 Export Standzeiten",
        "header_customers": "📋 Kundenliste",
        "col_tour_nr": "Tournummer",
        "col_filename": "Dateiname",
        "col_date": "Datum",
        "col_cust_nr": "Kunden Nr.",
        "col_name": "Name",
        "col_arr": "Ankunft",
        "col_dep": "Abfahrt",
        "col_dur": "Dauer",
        "nav_back": "⬅️",
        "nav_next": "➡️",
        "page_info": "S. {current}/{total}",
        "time_suffix": " Uhr",
        "date_format": "%d.%m.%Y",
        "file_date_format": "%d.%m.%Y %H:%M",
        "manual_md": """
## 📘 Benutzerhandbuch

### 1. Layout
* **Alignment:** Die Spalte "Upload" ist nun pixelgenau mit der Kachel "Ø Geschw." ausgerichtet.

### 2. Bedienung
#### 📂 Tour laden
* Klicken Sie oben links auf eine Tour in der Liste.

#### 🗺️ Karte & 2. Monitor
* Nutzen Sie den Button **"🌍 Karte für 2. Monitor speichern"** unter der Karte.

#### 📋 Liste
* Klicken Sie auf eine Zeile links, um den Kunden in der Karte zu zentrieren.
"""
    },
    "English": {
        "page_title": "Truck Tour Viewer Pro",
        "tours_found": "📂 Found tours currently: <b>{count}</b> (Auto-Update: 60s)",
        "no_files": "No GPX files.",
        "upload_text": "Drop GPX file here (max. 200 MB)",
        "manual_btn_help": "Manual",
        "manual_title": "User Manual",
        "stats_start": "⏱️ Start",
        "stats_end": "🏁 End",
        "stats_dist": "📏 Distance",
        "stats_speed": "Ø Speed",
        "btn_save_map": "🌍 Save Map for 2nd Monitor",
        "btn_sidebar": "Sidebar on/off",  # RESTORED
        "btn_export": "📄 Export Standstills",
        "header_customers": "📋 Customer List",
        "col_tour_nr": "Tour No.",
        "col_filename": "Filename",
        "col_date": "Date",
        "col_cust_nr": "Customer No.",
        "col_name": "Name",
        "col_arr": "Arrival",
        "col_dep": "Departure",
        "col_dur": "Duration",
        "nav_back": "⬅️",
        "nav_next": "➡️",
        "page_info": "P. {current}/{total}",
        "time_suffix": "",
        "date_format": "%Y-%m-%d",
        "file_date_format": "%Y-%m-%d %H:%M",
        "manual_md": """
## 📘 User Manual

### 1. Layout
* **Alignment:** The Upload box is now pixel-perfect aligned with the Speed tile.

### 2. Operation
#### 📂 Load Tour
* Click a tour in the top left list.

#### 🗺️ Map & 2nd Monitor
* Use the **"🌍 Save Map..."** button below the map.

#### 📋 List
* Click a row on the left to center the customer on the map.
"""
    }
}

def get_text(key):
    lang = st.session_state.get('language', 'Deutsch')
    return TRANSLATIONS[lang].get(key, key)

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
    
    lang = st.session_state.get('language', 'Deutsch')
    time_suffix = TRANSLATIONS[lang]["time_suffix"]
    date_fmt = TRANSLATIONS[lang]["date_format"]
    
    try:
        bounds = gpx.get_time_bounds()
        if bounds.start_time and bounds.end_time:
            t_start = bounds.start_time + timedelta(hours=2)
            t_end = bounds.end_time + timedelta(hours=2)
            start_time_str = t_start.strftime("%H:%M") + time_suffix
            end_time_str = t_end.strftime("%H:%M") + time_suffix
            date_str = t_start.strftime(date_fmt)

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
                
                col_nr = TRANSLATIONS[lang]["col_cust_nr"]
                col_name = TRANSLATIONS[lang]["col_name"]
                col_arr = TRANSLATIONS[lang]["col_arr"]
                col_dep = TRANSLATIONS[lang]["col_dep"]
                col_dur = TRANSLATIONS[lang]["col_dur"]
                
                stop_data = {
                    col_nr: customer_id,
                    col_arr: arrival_time,
                    col_dep: departure_time,
                    col_dur: duration,
                    "Lat": point.latitude,
                    "Lon": point.longitude
                }
                if customer_db:
                    stop_data[col_name] = customer_name
                
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
    lang = st.session_state.get('language', 'Deutsch')
    col_tour = TRANSLATIONS[lang]["col_tour_nr"]
    col_fname = TRANSLATIONS[lang]["col_filename"]
    col_fdate = TRANSLATIONS[lang]["col_date"]
    
    for f in os.listdir('.'):
        if os.path.isfile(f) and f.upper().startswith('DL') and f.upper().endswith('.GPX'):
            mod_time = os.path.getmtime(f)
            dt_obj = datetime.fromtimestamp(mod_time)
            fmt = TRANSLATIONS[lang]["file_date_format"]
            date_str = dt_obj.strftime(fmt)
            tour_nr = f.upper().replace("DL", "").replace(".GPX", "")
            
            file_list.append({
                col_tour: tour_nr,
                col_fname: f, 
                col_fdate: date_str, 
                "timestamp": mod_time
            })
    file_list.sort(key=lambda x: x["timestamp"], reverse=True)
    return file_list

@st.fragment(run_every=60)
def file_selector_fragment():
    files_info = get_local_gpx_files_info()
    lang = st.session_state.get('language', 'Deutsch')
    col_tour = TRANSLATIONS[lang]["col_tour_nr"]
    col_fname = TRANSLATIONS[lang]["col_filename"]
    col_fdate = TRANSLATIONS[lang]["col_date"]
    
    if files_info:
        count = len(files_info)
        info_text = TRANSLATIONS[lang]["tours_found"].format(count=count)
        st.markdown(f"<div style='color:white; font-size:0.9em; margin-bottom:3px;'>{info_text}</div>", unsafe_allow_html=True)
        
        df_files = pd.DataFrame(files_info)[[col_tour, col_fname, col_fdate]]
        styled_df_files = df_files.style.set_properties(**{'background-color': 'rgba(255,255,255,0.1)', 'color': 'white', 'border-color': 'rgba(255,255,255,0.1)', 'cursor': 'pointer'})
        
        selection = st.dataframe(
            styled_df_files, 
            width="stretch", 
            hide_index=True, 
            column_order=[col_tour, col_fname, col_fdate], 
            selection_mode="single-row", 
            on_select="rerun", 
            key="file_selection_table", 
            height=180
        )
        
        if len(selection.selection.rows) > 0:
            index = selection.selection.rows[0]
            selected_file = df_files.iloc[index][col_fname]
            if st.session_state.get('selected_local_file') != selected_file:
                st.session_state.selected_local_file = selected_file
                st.session_state.last_selection_ts = time.time()
                st.rerun()
    else:
        st.markdown(f"<div style='color:white; font-size:0.9em;'>{TRANSLATIONS[lang]['no_files']}</div>", unsafe_allow_html=True)

@st.dialog("Manual")
def show_help_dialog():
    lang = st.session_state.get('language', 'Deutsch')
    st.markdown(TRANSLATIONS[lang]["manual_md"])
    if st.button("Close"):
        st.rerun()

def main():
    st.set_page_config(page_title="LKW Touren Viewer Pro", page_icon="🚚", layout="wide")
    
    # --- INIT STATE ---
    if 'language' not in st.session_state: st.session_state.language = 'Deutsch'
    if 'show_right_sidebar' not in st.session_state: st.session_state.show_right_sidebar = True
    if 'page_number' not in st.session_state: st.session_state.page_number = 0
    if 'selected_customer_id' not in st.session_state: st.session_state.selected_customer_id = None
    if 'selected_local_file' not in st.session_state: st.session_state.selected_local_file = None
    if 'last_upload_ts' not in st.session_state: st.session_state.last_upload_ts = 0.0
    if 'last_selection_ts' not in st.session_state: st.session_state.last_selection_ts = 0.0
    if 'tour_data' not in st.session_state: st.session_state.tour_data = None
    if 'loaded_file_name' not in st.session_state: st.session_state.loaded_file_name = None
    if 'last_lang' not in st.session_state: st.session_state.last_lang = st.session_state.language

    # --- RESET BEI SPRACHWECHSEL ---
    if st.session_state.language != st.session_state.last_lang:
        st.session_state.loaded_file_name = None 
        st.session_state.last_lang = st.session_state.language
        st.rerun()

    customer_db = load_customer_db()
    has_customer_names = customer_db is not None

    logo_filename = "movisl.jpg"
    logo_base64 = ""
    if os.path.exists(logo_filename):
        logo_base64 = get_base64_of_bin_file(logo_filename)

    # --- CSS DESIGN ---
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
            .version {{ margin-left: auto; color: #047761; font-weight: bold; font-family: sans-serif; margin-right: 20px; }}

            div[data-testid="stVerticalBlock"] > div:has(div#fixed-controls-anchor) {{
                position: fixed; top: 60px; left: 0; width: 100%;
                background-color: #047761; z-index: 99999;
                padding-left: 2rem; padding-right: 2rem; padding-bottom: 5px;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }}
            .block-container {{ padding-top: {HEADER_HEIGHT_PIXELS}px !important; padding-bottom: 0px !important; }}
            
            [data-testid="stMarkdownContainer"] h3 a {{ display: none !important; pointer-events: none; }}
            
            h1, h2, h3, h4, p, div, label, .stMarkdown, .stMetricValue, .stMetricLabel {{ color: white !important; }}
            .custom-header * {{ color: #047761 !important; }}
            div[data-testid="stButton"] button p, div[data-testid="stDownloadButton"] button p {{ color: #047761 !important; }}
            
            [data-testid='stFileUploader'] section > div > div > span {{ display: none !important; }}
            [data-testid='stFileUploader'] section > div > div > small {{ display: none !important; }}
            [data-testid='stFileUploader'] section > div > div::after {{
                content: "{get_text('upload_text')}";
                white-space: pre; color: white; text-align: center; display: block; font-weight: bold; font-size: 14px;
            }}

            div[data-testid="stButton"] button, div[data-testid="stDownloadButton"] button {{
                background-color: white !important; color: #047761 !important; border-radius: 6px !important; font-weight: bold !important;
            }}
            
            [data-testid="stDataFrame"] thead tr th, [data-testid="stDataFrame"] thead tr {{
                background-color: rgba(255,255,255,0.1) !important; color: white !important;
            }}
            
            div[data-testid="stDialog"] {{
                background-color: #047761 !important;
                color: white !important;
            }}
        </style>
    """, unsafe_allow_html=True)

    # --- HEADER & CONTROLS ---
    version_html = f'<div class="version">v{APP_VERSION}</div>'
    if logo_base64:
        st.markdown(f'<div class="custom-header"><img src="data:image/jpeg;base64,{logo_base64}">{version_html}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="custom-header"><h2 style="color:#047761!important; margin:0; font-size:24px;">movis</h2>{version_html}</div>', unsafe_allow_html=True)

    with st.container():
        st.markdown('<div id="fixed-controls-anchor"></div>', unsafe_allow_html=True)
        
        # TITEL
        tit_col1, tit_col2, tit_col3 = st.columns([6, 0.5, 0.5], gap="small")
        with tit_col1:
             st.markdown(f"<h3 style='text-align: center; color: white; margin-top: 5px; margin-bottom: 5px;'>🚚 {get_text('page_title')}</h3>", unsafe_allow_html=True)
        with tit_col2:
            curr_lang = st.session_state.language
            btn_label = "DE" if curr_lang == 'Deutsch' else "GB"
            if st.button(btn_label, key="lang_toggle"):
                st.session_state.language = 'English' if curr_lang == 'Deutsch' else 'Deutsch'
                st.rerun()
        with tit_col3:
            if st.button("❓", help=get_text("manual_btn_help")): show_help_dialog()
        
        # UNTERE ZEILE: DATEILISTE & UPLOAD (3:1 Verhältnis mit gap="small")
        head_col1, head_col2 = st.columns([3, 1], gap="small")
        
        with head_col1:
            file_selector_fragment()
            
        with head_col2:
            st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True) 
            def on_upload_change(): st.session_state.last_upload_ts = time.time()
            uploaded_file = st.file_uploader("Upload", type=['gpx'], label_visibility="collapsed", on_change=on_upload_change)

        file_to_process = None
        file_name_display = ""
        is_upload_newer = st.session_state.last_upload_ts > st.session_state.last_selection_ts
        
        if uploaded_file is not None and is_upload_newer:
            file_to_process, file_name_display = uploaded_file, uploaded_file.name
        elif st.session_state.selected_local_file:
            try:
                if os.path.exists(st.session_state.selected_local_file):
                    file_to_process, file_name_display = open(st.session_state.selected_local_file, 'rb'), st.session_state.selected_local_file
            except: pass
        
        if file_to_process:
            if st.session_state.loaded_file_name != file_name_display:
                st.session_state.tour_data = process_gpx_data(file_to_process, customer_db)
                st.session_state.loaded_file_name = file_name_display
        
    # --- HAUPTBEREICH ---
    if st.session_state.tour_data and st.session_state.tour_data["points"]:
        data = st.session_state.tour_data
        points = data["points"]
        customer_stops = data["customer_stops"]

        tour_nr = ""
        if st.session_state.loaded_file_name:
            fname = os.path.splitext(st.session_state.loaded_file_name)[0]
            tour_nr = fname.upper().replace("DL", "")

        # --- STATISTIK ZEILE (MIT NESTED COLUMNS FÜR PERFEKTES ALIGNMENT) ---
        stat_row_left, stat_row_right = st.columns([3, 1], gap="small")
        
        box_style = "color: white; text-align: center; background: rgba(255,255,255,0.1); padding: 4px; border-radius: 8px;"
        
        with stat_row_left:
            # 3 Unterspalten
            s1, s2, s3 = st.columns(3, gap="small")
            with s1: st.markdown(f"<div style='{box_style}'><div style='font-size:0.9em; opacity:0.8'>{get_text('stats_start')}</div><div style='font-size:1.1em; font-weight:bold'>{data['start_time']}</div></div>", unsafe_allow_html=True)
            with s2: st.markdown(f"<div style='{box_style}'><div style='font-size:0.9em; opacity:0.8'>{get_text('stats_end')}</div><div style='font-size:1.1em; font-weight:bold'>{data['end_time']}</div></div>", unsafe_allow_html=True)
            with s3: st.markdown(f"<div style='{box_style}'><div style='font-size:0.9em; opacity:0.8'>{get_text('stats_dist')}</div><div style='font-size:1.1em; font-weight:bold'>{data['dist_km']:.2f} km</div></div>", unsafe_allow_html=True)
            
        with stat_row_right:
            # 4. Spalte
            st.markdown(f"<div style='{box_style}'><div style='font-size:0.9em; opacity:0.8'>{get_text('stats_speed')}</div><div style='font-size:1.1em; font-weight:bold'>{data['avg_speed']:.1f} km/h</div></div>", unsafe_allow_html=True)
        
        st.markdown("<div style='height: 10px'></div>", unsafe_allow_html=True)
        
        mid_p = points[len(points)//2]
        zoom_val = 12
        if st.session_state.selected_customer_id:
            for stop in customer_stops:
                if stop[get_text("col_cust_nr")] == st.session_state.selected_customer_id:
                    mid_p = [stop['Lat'], stop['Lon']]
                    zoom_val = 16 
                    break
        
        bcol_left, bcol_right = st.columns([1, 1])
        with bcol_left:
            m = folium.Map(location=mid_p, zoom_start=zoom_val, double_click_zoom=False)
            folium.PolyLine(points, color="red", weight=5, opacity=0.8).add_to(m)
            
            c_nr, c_name = get_text("col_cust_nr"), get_text("col_name")
            c_dur, c_arr, c_dep = get_text("col_dur"), get_text("col_arr"), get_text("col_dep")

            for stop in customer_stops:
                is_sel = (stop[c_nr] == st.session_state.selected_customer_id)
                icon_color, icon_type = ("red", "star") if is_sel else ("blue", "user")
                
                name_disp = stop.get(c_name, '')
                popup_text = f"<b>{c_nr}: {stop[c_nr]}</b>{f'<br>({name_disp})' if name_disp else ''}<br>{c_dur}: {stop[c_dur]} min<br>{c_arr}: {stop[c_arr]}<br>{c_dep}: {stop[c_dep]}"
                tooltip_text = f"{c_nr}: {stop[c_nr]}{f' ({name_disp})' if name_disp else ''}"
                
                folium.Marker(
                    [stop['Lat'], stop['Lon']], 
                    popup=folium.Popup(popup_text, max_width=300, auto_pan=False), 
                    tooltip=tooltip_text, 
                    icon=folium.Icon(color=icon_color, icon=icon_type, prefix="fa")
                ).add_to(m)
                
            map_html = m.get_root().render()
            st.download_button(get_text("btn_save_map"), map_html, "LKW_Tour.html", "text/html")
        
        with bcol_right:
            sub_c1, sub_c2 = st.columns([1, 1])
            with sub_c1:
                if customer_stops and st.button(get_text("btn_sidebar")): 
                    st.session_state.show_right_sidebar = not st.session_state.show_right_sidebar
                    st.rerun()
            with sub_c2:
                if customer_stops:
                    df_export = pd.DataFrame(customer_stops)
                    df_export.insert(0, "TourNr", tour_nr)
                    df_export.insert(1, "Datum", data['date_str'])
                    df_export = df_export.drop(columns=['Lat', 'Lon'], errors='ignore')
                    csv = df_export.to_csv(index=False, sep=';', encoding='utf-16').encode('utf-16')
                    st.download_button(label=get_text("btn_export"), data=csv, file_name=f"Standzeiten_{data['date_str']}.csv", mime="text/csv")

        if st.session_state.show_right_sidebar and customer_stops:
            c_map, c_list = st.columns([1, 1])
            with c_map: 
                st.markdown("<div style='margin-top: -15px;'></div>", unsafe_allow_html=True)
                components.html(map_html, height=800)
            
            with c_list:
                st.markdown(f'<div style="position: sticky; top: {HEADER_HEIGHT_PIXELS + 20}px; z-index: 100;">', unsafe_allow_html=True)
                
                header_text = get_text('header_customers')
                if tour_nr:
                    header_text += f" Tour {tour_nr}"
                
                st.markdown(f"<div style='text-align: center; color: white; margin-bottom: 5px; font-weight: bold; font-size: 1.1em;'>{header_text}</div>", unsafe_allow_html=True)

                total_stops = len(customer_stops)
                num_pages = math.ceil(total_stops / ROWS_PER_PAGE)
                start_idx = st.session_state.page_number * ROWS_PER_PAGE
                current_batch = customer_stops[start_idx : start_idx + ROWS_PER_PAGE]
                df_stops = pd.DataFrame(current_batch)
                
                cols = [get_text("col_cust_nr"), get_text("col_arr"), get_text("col_dep"), get_text("col_dur")]
                if has_customer_names: cols.insert(1, get_text("col_name"))
                
                sel = st.dataframe(
                    df_stops.style.set_properties(**{'background-color': '#047761', 'color': 'white'}), 
                    width="stretch", 
                    hide_index=True, 
                    column_order=cols, 
                    selection_mode="single-row", 
                    on_select="rerun", 
                    key=f"tbl_{st.session_state.page_number}"
                )
                if sel.selection.rows:
                    sel_cust = current_batch[sel.selection.rows[0]][get_text("col_cust_nr")]
                    if st.session_state.selected_customer_id != sel_cust:
                        st.session_state.selected_customer_id = sel_cust
                        st.rerun()

                n1, n2, n3 = st.columns([1, 2, 1])
                with n1: 
                    if st.session_state.page_number > 0 and st.button(get_text("nav_back")): st.session_state.page_number -= 1; st.rerun()
                with n2: 
                    page_txt = get_text("page_info").format(current=st.session_state.page_number+1, total=num_pages)
                    st.markdown(f"<div style='text-align:center;'>{page_txt}</div>", unsafe_allow_html=True)
                with n3:
                    if st.session_state.page_number < num_pages-1 and st.button(get_text("nav_next")): st.session_state.page_number += 1; st.rerun()
                
                st.markdown('</div>', unsafe_allow_html=True)

        else: 
            components.html(map_html, height=800)

if __name__ == "__main__": main()
