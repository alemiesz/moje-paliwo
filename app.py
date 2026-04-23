import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, date, timedelta
import calendar

# --- KONFIGURACJA ---
MAX_STORAGE = 150 
LOW_FUEL_ALERT = 35 
st.set_page_config(page_title="FarmFuel Cloud PRO", layout="wide")

# Połączenie z Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNKCJE DANYCH (GOOGLE SHEETS) ---
def load_data():
    fleet = conn.read(worksheet="fleet")
    inv = conn.read(worksheet="inv")
    logs = conn.read(worksheet="logs")
    # Konwersja dat
    if not inv.empty: inv['Data'] = pd.to_datetime(inv['Data']).dt.date
    if not logs.empty: logs['Data'] = pd.to_datetime(logs['Data']).dt.date
    return fleet, inv, logs

df_fleet, df_inv, df_logs = load_data()

def save_data(df, worksheet_name):
    conn.update(worksheet=worksheet_name, data=df)
    st.cache_data.clear() # Czyścimy cache, żeby od razu widzieć zmiany

# --- LOGIKA SYSTEMOWA ---
total_purchased = df_inv['Litry'].sum() if not df_inv.empty else 0
total_used = df_logs['Dolano'].sum() if not df_logs.empty else 0
current_stock = max(0, total_purchased - total_used)
avg_price = (df_inv['Kwota'].sum() / total_purchased) if total_purchased > 0 else 0

# --- INTERFEJS (Skrócony dla czytelności, zachowuje funkcje Ultimate) ---
st.title("🚜 FarmFuel Cloud Command Center")

menu = st.sidebar.radio("MENU", ["Pulpit", "Raporty", "Garaż"])
target_date = st.sidebar.date_input("📅 Data operacji", date.today())

if menu == "Pulpit":
    c1, c2, c3 = st.columns(3)
    c1.metric("W zbiorniku", f"{current_stock:.1f} L")
    c2.metric("Średnia cena", f"{avg_price:.2f} zł")
    c3.metric("Spalone (suma)", f"{df_logs['Spalone'].sum() if not df_logs.empty else 0:.0f} L")

    st.divider()
    
    st.subheader("Twoja Flota")
    cols = st.columns(len(df_fleet))
    
    for i, (idx, row) in enumerate(df_fleet.iterrows()):
        with cols[i]:
            t_logs = df_logs[df_logs['ID'] == row['ID']]
            last_mth = t_logs['MTH'].max() if not t_logs.empty else row['MTH_Start']
            fuel_in_t = t_logs['Dolano'].sum() - t_logs['Spalone'].sum()
            
            st.markdown(f"### {row['Nazwa']}")
            st.write(f"📟 {last_mth:.1f} MTH")
            st.write(f"⛽ {fuel_in_t:.1f} L")
            st.progress(min(max(fuel_in_t/row['Bak'], 0.0), 1.0))

            with st.expander("Zapisz pracę"):
                with st.form(f"form_{row['ID']}", clear_on_submit=True):
                    new_m = st.number_input("Stan MTH", value=float(last_mth))
                    add_f = st.number_input("Dolano (L)", value=0.0)
                    if st.form_submit_button("ZAPISZ"):
                        burned = (new_m - last_mth) * row['Norma']
                        new_row = pd.DataFrame([[target_date, row['ID'], new_m, add_f, burned]], columns=df_logs.columns)
                        df_logs = pd.concat([df_logs, new_row], ignore_index=True)
                        save_data(df_logs, "logs")
                        st.success("Zapisano w chmurze!")
                        st.rerun()

elif menu == "Garaż":
    st.subheader("Zarządzaj Fakturami")
    with st.form("inv_add"):
        l = st.number_input("Litry")
        k = st.number_input("Kwota")
        if st.form_submit_button("Dodaj Fakturę"):
            new_inv = pd.DataFrame([[target_date, l, k]], columns=df_inv.columns)
            df_inv = pd.concat([df_inv, new_inv], ignore_index=True)
            save_data(df_inv, "inv")
            st.rerun()
    
    st.divider()
    st.write("Twoje ciągniki (dane z Google Sheets):")
    st.dataframe(df_fleet)