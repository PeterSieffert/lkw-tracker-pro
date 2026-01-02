import streamlit as st
import gpxpy
import folium
from streamlit_folium import st_folium
import base64
import os
from datetime import timedelta
import pandas as pd
import math

# --- KONFIGURATION ---
APP_VERSION = "1.42"        # Korrektur: Spaltenname in KND.STM ist "NUMBER" (nicht NUMBRT)
HEADER_HEIGHT_PIXELS = 450  
ROWS_PER_PAGE = 10          

def get_base64_of_bin_file(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

def load_customer_db():
    """Lädt die Kundennamen aus der KND.STM Datei."""
    filename = "KND.STM"
    if not os.path.exists(filename):
        return None
    
    try:
        # CSV lesen (Trenner automatisch erkennen, Encoding für Sonderzeichen)
        df = pd.read_csv(filename, sep=None, engine='python', dtype=str, encoding='latin1')
        
        # Spaltennamen bereinigen (Leerzeichen entfernen)
        df.columns = df.columns.str.strip()
        
        # --- HIER IST DIE KORREKTUR: NUMBER statt NUMBRT ---
        if 'NUMBER' in df.columns and 'NAME' in df.columns:
            # Dictionary erstellen: { "12345": "Musterfirma GmbH", ... }
            return dict(zip(df['NUMBER'].str.strip(), df['NAME'].str.strip()))
        else:
            # Falls Spalten anders heißen, geben wir zur Diagnose die gefundenen aus
            print(f"KND.STM gefunden, aber Spalten fehlen. Gefunden: {list(df.columns)}")
            return None
    except Exception as e:
        print(f"Fehler beim Laden der KND.STM: {e}")
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
    
    if moving_time_seconds > 0:
        avg_speed = dist_km / (moving_time_seconds / 3600.0)
    else:
        avg_speed = 0.0

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
                
                duration = end_ts - start_ts
                duration_minutes = int(duration.total_seconds() / 60)
                
                arrival_time = (start_ts + timedelta(hours=2)).strftime("%H:%M:%S")
                departure_time = (end_ts + timedelta(hours=2)).strftime("%H:%M:%S")
                
                # --- NAME ZUORDNEN ---
                customer_name = ""
                if customer_db is not None:
                    # Suche nach ID in der Datenbank
                    customer_name = customer_db.get(customer_id, "Unbekannt")
                
                stop_data = {
                    "Kunden Nr.": customer_id,
                    "Ankunft": arrival_time,
                    "Abfahrt": departure_time,
                    "Dauer (Min)": duration_minutes,
                    "Lat": point.latitude,
                    "Lon": point.longitude
                }
                
                if customer_db is not None:
                    stop_data["Name"] = customer_name
                
                customer_stops.append(stop_data)

    except Exception as e:
        print(f"Fehler: {e}")
        pass

    return points, dist_km, avg_speed, start_time_str, end_time_str, date_str, customer_stops

def main():
    st.set_page_config(page_title="LKW Touren Viewer Pro", page_icon="🚚", layout="wide")
    
    # Session States
    if 'show_right_sidebar' not in st.session_state:
        st.session_state.show_right_sidebar = True
    if 'page_number' not in st.session_state:
        st.session_state.page_number = 0
    if 'selected_customer_id' not in st.session_state:
        st.session_state.selected_customer_id = None

    # --- DATENBANK LADEN ---
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
            
            h1 > a, h2 > a, h3 > a, h4 > a, h5 > a, h6 > a {{ display: none !important; }}
            .anchor-link, [data-testid="stMarkdownContainer"] a {{ text-decoration: none !important; display: none !important; }}

            /* Scrollbars */
            ::-webkit-scrollbar {{ width: 22px !important; height: 22px !important; }}
            ::-webkit-scrollbar-track {{ background: #02382e !important; }}
            ::-webkit-scrollbar-thumb {{ background: #ffffff !important; border: 3px solid #02382e !important; border-radius: 10px !important; }}
            ::-webkit-scrollbar-thumb:hover {{ background: #ffcc00 !important; }}

            /* Header (Weiß) */
            .header {{
                position: fixed; top: 0; left: 0; width: 100%; height: 60px;
                background-color: white; padding: 5px 30px;
                z-index: 10000; box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                display: flex; align-items: center;
            }}
            .header img {{ height: 45px; width: auto; }}
            .version {{ margin-left: auto; color: #047761; font-weight: bold; font-family: sans-serif; }}

            /* Fixierter Bereich (Grün) */
            div[data-testid="stVerticalBlock"] > div:has(div#fixed-controls-anchor) {{
                position: fixed; top: 60px; left: 0; width: 100%;
                background-color: #047761; z-index: 9999;
                padding-left: 2rem; padding-right: 2rem; padding-bottom: 15px;
                border-bottom: 1px solid rgba(255,255,255,0.1);
            }}
            .block-container {{ padding-top: {HEADER_HEIGHT_PIXELS}px !important; }}
            
            h1, h2, h3, h4, p, div, label, .stMarkdown, .stMetricValue, .stMetricLabel {{ color: white !important; }}
            .header * {{ color: #047761 !important; }} 
            .stException, .stException div, .stError, .stError div {{ color: black !important; }}
            .stAppDeployButton, header, #MainMenu, footer {{ visibility: hidden; }}

            /* Upload */
            [data-testid='stFileUploader'] {{ margin-bottom: 5px; }}
            [data-testid='stFileUploader'] section {{ padding: 10px !important; }}
            [data-testid='stFileUploader'] section > div > div > span,
            [data-testid='stFileUploader'] section > div > div > small {{ display: none; }}
            [data-testid='stFileUploader'] section > div > div::after {{
                content: "GPX Datei hier ablegen";
                white-space: pre; color: white; text-align: center;
                display: block; font-weight: bold; font-size: 14px;
            }}
            
            /* Buttons */
            div[data-testid="stButton"] button, div[data-testid="stDownloadButton"] button {{
                background-color: white !important;
                color: #047761 !important;
                border: 2px solid white !important;
                font-weight: bold !important;
                border-radius: 6px !important;
                transition: all 0.3s;
                margin-top: 0px !important;
                margin-bottom: 0px !important;
                height: auto !important;
                padding: 5px 15px !important;
            }}
            div[data-testid="stButton"] button:hover, div[data-testid="stDownloadButton"] button:hover {{
                background-color: #f0f0f0 !important;
                transform: translateY(-2px);
                color: #047761 !important;
            }}
            div[data-testid="stButton"] button p, div[data-testid="stDownloadButton"] button p {{
                color: #047761 !important;
            }}

            /* Alignment */
            [data-testid="column"] {{
                display: flex;
                flex-direction: column;
                justify-content: center;
            }}
            div[data-testid="stDownloadButton"] {{
                align-self: flex-end; 
                text-align: right !important;
            }}
            div[data-testid="stDownloadButton"] > button {{
                width: 300px !important; 
                min-width: 300px !important;
            }}
            div[data-testid="stButton"] {{
                align-self: flex-end;
                display: flex;
            }}
            
            /* --- DATAFRAME STYLING (Standard Glas-Look) --- */
            [data-testid="stDataFrame"] {{
                background-color: transparent !important;
            }}
            
            /* Header Zeile und Checkbox-Header: Glas-Optik (0.1 Alpha) */
            [data-testid="stDataFrame"] thead tr th,
            [data-testid="stDataFrame"] thead tr,
            [data-testid="stDataFrame"] thead th:first-child {{
                background-color: rgba(255,255,255,0.1) !important; 
                color: white !important;
                border-bottom: 1px solid rgba(255,255,255,0.2) !important;
            }}
            
            /* Checkboxen WEISS */
            [data-testid="stDataFrame"] input[type="checkbox"] {{
                filter: brightness(0) invert(1) !important;
                cursor: pointer;
            }}

        </style>
    """, unsafe_allow_html=True)

    # --- HEADER ---
    version_html = f'<div class="version">v{APP_VERSION}</div>'
    if logo_base64:
        st.markdown(f'<div class="header"><img src="data:image/jpeg;base64,{logo_base64}">{version_html}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="header"><h2 style="color:#047761!important; margin:0; font-size:24px;">movis</h2>{version_html}</div>', unsafe_allow_html=True)

    # --- FIXIERTER BEREICH ---
    with st.container():
        st.markdown('<div id="fixed-controls-anchor"></div>', unsafe_allow_html=True)
        st.markdown("<h3 style='text-align: center; color: white; margin-top: 10px; margin-bottom: 10px;'>🚚 LKW Touren Viewer Pro</h3>", unsafe_allow_html=True)
        
        uploaded_file = st.file_uploader("Wähle eine GPX Datei", type=['gpx'])

        points = []
        dist_km = 0
        avg_speed = 0
        start_time = "-"
        end_time = "-"
        date_str = ""
        m = None 
        tour_info_line = ""
        customer_stops = []
        
        if uploaded_file is not None:
            try:
                # DB übergeben
                points, dist_km, avg_speed, start_time, end_time, date_str, customer_stops = process_gpx_data(uploaded_file, customer_db)
                if not points:
                    st.error("Keine Wegpunkte gefunden.")
            except Exception as e:
                st.error(f"Fehler: {e}")

            filename = uploaded_file.name
            parts = []
            if filename.startswith("DL") and filename.lower().endswith(".gpx"):
                parts.append(f"Tour: {filename[2:-4]}")
            if date_str:
                parts.append(f"Datum: {date_str}")
            if parts:
                tour_info_line = " &nbsp;•&nbsp; ".join(parts)

        # Info-Zeile
        if tour_info_line:
            st.markdown(f"<div style='text-align: center; color: white; margin-bottom: 10px; font-weight:bold; font-size: 1.1em;'>{tour_info_line}</div>", unsafe_allow_html=True)
        elif uploaded_file is not None:
            st.markdown("<div style='height: 5px'></div>", unsafe_allow_html=True)

        if points:
            # Stats
            col1, col2, col3, col4 = st.columns(4)
            box_style = "color: white; text-align: center; background: rgba(255,255,255,0.1); padding: 4px; border-radius: 8px;"
            with col1: st.markdown(f"<div style='{box_style}'><div style='font-size:0.9em; opacity:0.8'>⏱️ Start</div><div style='font-size:1.1em; font-weight:bold'>{start_time}</div></div>", unsafe_allow_html=True)
            with col2: st.markdown(f"<div style='{box_style}'><div style='font-size:0.9em; opacity:0.8'>🏁 Ende</div><div style='font-size:1.1em; font-weight:bold'>{end_time}</div></div>", unsafe_allow_html=True)
            with col3: st.markdown(f"<div style='{box_style}'><div style='font-size:0.9em; opacity:0.8'>📏 Distanz</div><div style='font-size:1.1em; font-weight:bold'>{dist_km:.2f} km</div></div>", unsafe_allow_html=True)
            with col4: 
                speed_text = f"{avg_speed:.1f} km/h" if avg_speed > 0 else "-"
                st.markdown(f"<div style='{box_style}'><div style='font-size:0.9em; opacity:0.8'>Ø Geschw.</div><div style='font-size:1.1em; font-weight:bold'>{speed_text}</div></div>", unsafe_allow_html=True)
            
            st.markdown("<div style='height: 10px'></div>", unsafe_allow_html=True)

            # --- MAP & MARKER ---
            mid_index = len(points) // 2
            map_center = points[mid_index]
            zoom_lvl = 12

            if st.session_state.selected_customer_id:
                for stop in customer_stops:
                    if stop['Kunden Nr.'] == st.session_state.selected_customer_id:
                        map_center = [stop['Lat'], stop['Lon']]
                        zoom_lvl = 14
                        break

            m = folium.Map(location=map_center, zoom_start=zoom_lvl)
            folium.PolyLine(points, color="red", weight=5, opacity=0.8).add_to(m)
            folium.Marker(points[0], popup="Start", icon=folium.Icon(color="green", icon="play")).add_to(m)
            folium.Marker(points[-1], popup="Ziel", icon=folium.Icon(color="black", icon="flag")).add_to(m)
            
            for stop in customer_stops:
                is_selected = (stop['Kunden Nr.'] == st.session_state.selected_customer_id)
                icon_color = "red" if is_selected else "blue"
                icon_type = "star" if is_selected else "user"
                z_index = 1000 if is_selected else 0
                
                # Popup mit Name
                customer_name_display = stop.get('Name', '')
                if customer_name_display:
                    popup_header = f"<b>Kunde: {stop['Kunden Nr.']}</b><br>({customer_name_display})"
                else:
                    popup_header = f"<b>Kunde: {stop['Kunden Nr.']}</b>"
                
                popup_text = f"{popup_header}<br>Dauer: {stop['Dauer (Min)']} min<br>An: {stop['Ankunft']}<br>Ab: {stop['Abfahrt']}"
                
                # Tooltip mit Name
                tooltip_text = f"Kunde: {stop['Kunden Nr.']}"
                if customer_name_display:
                    tooltip_text += f" ({customer_name_display})"

                folium.Marker(
                    location=[stop['Lat'], stop['Lon']], 
                    popup=folium.Popup(popup_text, max_width=300), 
                    tooltip=tooltip_text, 
                    icon=folium.Icon(color=icon_color, icon=icon_type, prefix="fa"),
                    z_index_offset=z_index
                ).add_to(m)
            
            map_html = m.get_root().render()

            # --- BUTTONS ---
            if st.session_state.show_right_sidebar and customer_stops:
                btn_col1, btn_col2 = st.columns([1, 1], gap="small")
            else:
                btn_col1, btn_col2 = st.columns([3, 1], gap="small")

            with btn_col1:
                st.download_button(
                    label="🌍 Karte für 2. Monitor speichern", 
                    data=map_html, 
                    file_name="LKW_Tour.html", 
                    mime="text/html",
                    help="Hinweis: Die Karte wird im Download-Ordner gespeichert. Bitte manuell öffnen."
                )

            with btn_col2:
                if customer_stops:
                    if st.button("Sidebar ein/aus"):
                        st.session_state.show_right_sidebar = not st.session_state.show_right_sidebar

    # --- HAUPTBEREICH ---
    if points and m:
        if st.session_state.show_right_sidebar and customer_stops:
            col_map, col_list = st.columns([1, 1])
            with col_map:
                st_folium(m, height=800, use_container_width=True) 

            with col_list:
                st.markdown("<div style='text-align: center; color: white; margin-top: 0; margin-bottom: 5px; font-weight: bold; font-size: 1.1em;'>📋 Kundenliste</div>", unsafe_allow_html=True)
                
                total_stops = len(customer_stops)
                num_pages = math.ceil(total_stops / ROWS_PER_PAGE)
                
                if st.session_state.page_number >= num_pages:
                    st.session_state.page_number = 0
                
                start_idx = st.session_state.page_number * ROWS_PER_PAGE
                end_idx = start_idx + ROWS_PER_PAGE
                current_batch = customer_stops[start_idx:end_idx]
                
                df_stops = pd.DataFrame(current_batch)
                
                # Style
                styled_df = df_stops.style.set_properties(**{
                    'background-color': '#047761', 
                    'color': 'white',
                    'border-color': 'rgba(255,255,255,0.1)'
                })
                
                # Spaltenwahl dynamisch
                cols_to_show = ["Kunden Nr.", "Ankunft", "Abfahrt", "Dauer (Min)"]
                if has_customer_names:
                    cols_to_show.insert(1, "Name")

                selection = st.dataframe(
                    styled_df,
                    width="stretch",
                    hide_index=True,
                    column_order=cols_to_show,
                    selection_mode="single-row",
                    on_select="rerun",
                    key=f"customer_table_{st.session_state.page_number}"
                )
                
                if len(selection.selection.rows) > 0:
                    relative_index = selection.selection.rows[0]
                    selected_customer = current_batch[relative_index]["Kunden Nr."]
                    
                    if st.session_state.selected_customer_id != selected_customer:
                        st.session_state.selected_customer_id = selected_customer
                        st.rerun()

                st.markdown("<br>", unsafe_allow_html=True)
                nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])
                
                with nav_col1:
                    if st.session_state.page_number > 0:
                        if st.button("⬅️ Zurück", key="prev_page"):
                            st.session_state.page_number -= 1
                            st.rerun()
                
                with nav_col2:
                    st.markdown(f"<div style='text-align: center; padding-top: 5px; color: white;'>Seite {st.session_state.page_number + 1} von {num_pages}</div>", unsafe_allow_html=True)
                
                with nav_col3:
                    if st.session_state.page_number < num_pages - 1:
                        if st.button("Weiter ➡️", key="next_page"):
                            st.session_state.page_number += 1
                            st.rerun()

        else:
            st_folium(m, height=800, use_container_width=True)

if __name__ == "__main__":
    main()