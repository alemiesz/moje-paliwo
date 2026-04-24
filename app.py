import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, date
import calendar

st.set_page_config(page_title="FarmFuel Cloud ULTIMATE", layout="wide")

# Połączenie z autoryzacją Service Account (z Secrets)
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    # Teraz czytamy bezpiecznie z autoryzacją
    f = conn.read(worksheet="fleet", ttl="0")
    i = conn.read(worksheet="inv", ttl="0")
    l = conn.read(worksheet="logs", ttl="0")
    return f.dropna(how="all"), i.dropna(how="all"), l.dropna(how="all")

df_fleet, df_inv, df_logs = load_data()

# --- KONWERSJA DAT (Pamiętaj o tym!) ---
if not df_inv.empty: df_inv['Data'] = pd.to_datetime(df_inv['Data']).dt.date
if not df_logs.empty: df_logs['Data'] = pd.to_datetime(df_logs['Data']).dt.date

# --- LOGIKA OBLICZEŃ ---
total_purchased = df_inv['Litry'].sum() if not df_inv.empty else 0
total_used = df_logs['Dolano'].sum() if not df_logs.empty else 0
current_stock = max(0, total_purchased - total_used)
avg_price = (df_inv['Kwota'].sum() / total_purchased) if total_purchased > 0 else 0

# --- INTERFEJS ---
st.title("🚜 FarmFuel Command Center")
menu = st.sidebar.radio("MENU", ["Pulpit", "Raporty", "Garaż"])
target_date = st.sidebar.date_input("📅 Data", date.today())

if menu == "Pulpit":
    c1, c2, c3 = st.columns(3)
    c1.metric("⛽ W zbiorniku", f"{current_stock:.1f} L")
    c2.metric("💰 Średnia cena", f"{avg_price:.2f} zł")
    c3.metric("📉 Spalone", f"{df_logs['Spalone'].sum():.0f} L")

    st.divider()
    
    for _, t in df_fleet.iterrows():
        t_logs = df_logs[df_logs['ID'] == t['ID']]
        last_mth = t_logs['MTH'].max() if not t_logs.empty else t['MTH_Start']
        fuel_in_t = t_logs['Dolano'].sum() - t_logs['Spalone'].sum()
        
        with st.container():
            col_a, col_b = st.columns([2, 1])
            with col_a:
                st.subheader(f"{t['Nazwa']}")
                st.write(f"📟 Licznik: {last_mth:.1f} MTH | ⛽ Paliwo: {fuel_in_t:.1f} L")
            
            with col_b:
                with st.expander("➕ Loguj"):
                    with st.form(f"f_{t['ID']}", clear_on_submit=True):
                        new_m = st.number_input("Stan MTH", value=float(last_mth))
                        add_f = st.number_input("Dolano (L)", value=0.0)
                        if st.form_submit_button("Zapisz"):
                            burned = (new_m - last_mth) * t['Norma']
                            # Tworzymy nowy wiersz
                            new_row = pd.DataFrame([[str(target_date), t['ID'], new_m, add_f, burned]], columns=df_logs.columns)
                            updated_logs = pd.concat([df_logs, new_row], ignore_index=True)
                            # ZAPIS DO GOOGLE SHEETS
                            conn.update(worksheet="logs", data=updated_logs)
                            st.success("Zapisano!")
                            st.rerun()
        st.divider()

elif menu == "Garaż":
    with st.expander("Dodaj zakup paliwa"):
        with st.form("new_inv"):
            l_qty = st.number_input("Litry")
            l_cash = st.number_input("Kwota")
            if st.form_submit_button("Zapisz fakturę"):
                new_row_inv = pd.DataFrame([[str(target_date), l_qty, l_cash]], columns=df_inv.columns)
                updated_inv = pd.concat([df_inv, new_row_inv], ignore_index=True)
                conn.update(worksheet="inv", data=updated_inv)
                st.rerun()