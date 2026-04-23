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
st.set_page_config(page_title="FarmFuel Cloud ULTIMATE", layout="wide")

# Połączenie
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNKCJA ODCZYTU (METODA PANCERNA) ---
def load_data():
    try:
        # Pobieramy link z Secrets i czyścimy go
        raw_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
        base_url = raw_url.split("/edit")[0]
        
        # Pobieranie przez bezpśredni eksport CSV (najbardziej stabilne)
        fleet = pd.read_csv(f"{base_url}/gviz/tq?tqx=out:csv&sheet=fleet")
        inv = pd.read_csv(f"{base_url}/gviz/tq?tqx=out:csv&sheet=inv")
        logs = pd.read_csv(f"{base_url}/gviz/tq?tqx=out:csv&sheet=logs")
        
        # Czyszczenie danych
        fleet = fleet.dropna(how="all")
        inv = inv.dropna(how="all")
        logs = logs.dropna(how="all")
        
        # Konwersja dat
        if not inv.empty: inv['Data'] = pd.to_datetime(inv['Data']).dt.date
        if not logs.empty: logs['Data'] = pd.to_datetime(logs['Data']).dt.date
            
        return fleet, inv, logs
    except Exception as e:
        st.error(f"❌ Błąd połączenia: {e}")
        st.info("Sprawdź czy link w Secrets jest poprawny i czy zakładki nazywają się: fleet, inv, logs")
        st.stop()

# Wczytanie danych
df_fleet, df_inv, df_logs = load_data()

# --- LOGIKA SYSTEMOWA ---
total_purchased = df_inv['Litry'].sum() if not df_inv.empty else 0
total_used = df_logs['Dolano'].sum() if not df_logs.empty else 0
current_stock = max(0, total_purchased - total_used)
avg_price = (df_inv['Kwota'].sum() / total_purchased) if total_purchased > 0 else 0

# --- STYLIZACJA ---
st.markdown("""
    <style>
    .tractor-card { background: rgba(30, 41, 59, 0.4); padding: 20px; border-radius: 15px; border: 1px solid #334155; margin-bottom: 10px; }
    .stMetric { background: rgba(30, 41, 59, 0.4); padding: 10px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- MENU BOCZNE ---
st.sidebar.title("🚜 FarmFuel Cloud")
menu = st.sidebar.selectbox("NAWIGACJA", ["Pulpit Sterowniczy", "Raporty Miesięczne", "Historia i Garaż"])
target_date = st.sidebar.date_input("📅 Data wpisu", date.today())

# --- MODUŁ 1: PULPIT ---
if menu == "Pulpit Sterowniczy":
    c1, c2, c3 = st.columns(3)
    c1.metric("⛽ W zbiorniku", f"{current_stock:.1f} L")
    c2.metric("💰 Średnia cena", f"{avg_price:.2f} zł/L")
    c3.metric("📈 Razem spalone", f"{df_logs['Spalone'].sum() if not df_logs.empty else 0:.0f} L")

    st.divider()
    
    col_main, col_inv = st.columns([2, 1])
    
    with col_main:
        st.subheader("Monitoring Ciągników")
        if df_fleet.empty:
            st.warning("Baza ciągników jest pusta. Dodaj je w Garażu.")
        else:
            for _, t in df_fleet.iterrows():
                t_logs = df_logs[df_logs['ID'] == t['ID']]
                last_mth = t_logs['MTH'].max() if not t_logs.empty else t['MTH_Start']
                fuel_in_t = t_logs['Dolano'].sum() - t_logs['Spalone'].sum()
                
                # Serwis
                mth_done = last_mth - t['MTH_Start']
                to_service = t['Serwis_Co'] - (mth_done % t['Serwis_Co'])
                
                with st.container():
                    st.markdown(f'<div class="tractor-card">', unsafe_allow_html=True)
                    ca, cb, cc = st.columns([1, 1, 1])
                    ca.markdown(f"### {t['Nazwa']}")
                    ca.write(f"📟 Licznik: **{last_mth:.1f} MTH**")
                    
                    cb.write(f"⛽ Paliwo: **{fuel_in_t:.1f} L**")
                    cb.progress(min(max(fuel_in_t/t['Bak'], 0.0), 1.0))
                    
                    cc.write(f"🔧 Serwis za: **{to_service:.1f} MTH**")
                    
                    with st.expander("➕ Loguj pracę / tankowanie"):
                        with st.form(f"form_{t['ID']}", clear_on_submit=True):
                            new_m = st.number_input("Bieżące MTH", value=float(last_mth))
                            add_f = st.number_input("Dolałeś paliwa? (L)", value=0.0)
                            if st.form_submit_button("ZAPISZ"):
                                b_liters = (new_m - last_mth) * t['Norma']
                                new_row = pd.DataFrame([[target_date, t['ID'], new_m, add_f, b_liters]], columns=df_logs.columns)
                                updated_logs = pd.concat([df_logs, new_row], ignore_index=True)
                                conn.update(worksheet="logs", data=updated_logs)
                                st.success("Zapisano!")
                                st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)

    with col_inv:
        st.subheader("Główny Bak")
        fig = go.Figure(go.Indicator(
            mode = "gauge+number", value = current_stock,
            gauge = {'axis': {'range': [0, MAX_STORAGE]}, 'bar': {'color': "#3b82f6"}},
            domain = {'x': [0, 1], 'y': [0, 1]}
        ))
        fig.update_layout(height=250, margin=dict(t=30, b=0), paper_bgcolor='rgba(0,0,0,0)', font_color="white")
        st.plotly_chart(fig, use_container_width=True)
        
        with st.expander("📥 Dodaj Fakturę (Dostawa)"):
            with st.form("new_inv"):
                l = st.number_input("Ilość (L)", value=100.0)
                k = st.number_input("Kwota (zł)", value=600.0)
                if st.form_submit_button("Zapisz zakup"):
                    new_i = pd.DataFrame([[target_date, l, k]], columns=df_inv.columns)
                    updated_inv = pd.concat([df_inv, new_i], ignore_index=True)
                    conn.update(worksheet="inv", data=updated_inv)
                    st.success("Faktura dodana!")
                    st.rerun()

# --- MODUŁ 2: RAPORTY ---
elif menu == "Raporty Miesięczne":
    st.title("📊 Rozliczenie Miesięczne")
    cur_y = datetime.now().year
    y = st.selectbox("Rok", range(2024, cur_y + 5), index=range(2024, cur_y+5).index(cur_y))
    m = st.selectbox("Miesiąc", list(calendar.month_name)[1:], index=datetime.now().month-1)
    
    m_idx = list(calendar.month_name).index(m)
    mask = (pd.to_datetime(df_logs['Data']).dt.year == y) & (pd.to_datetime(df_logs['Data']).dt.month == m_idx)
    m_data = df_logs[mask]
    
    if not m_data.empty:
        st.write(f"Suma zużycia w {m} {y}: **{m_data['Spalone'].sum():.1f} L**")
        res = m_data.merge(df_fleet, on='ID').groupby('Nazwa')['Spalone'].sum().reset_index()
        st.plotly_chart(px.bar(res, x='Nazwa', y='Spalone', color='Nazwa'), use_container_width=True)
    else:
        st.info("Brak danych za ten miesiąc.")

# --- MODUŁ 3: GARAŻ ---
elif menu == "Historia i Garaż":
    st.title("⚙️ Garaż i Dane")
    with st.expander("Dodaj nowy ciągnik"):
        with st.form("add_t"):
            n = st.text_input("Nazwa")
            no = st.number_input("Norma L/MTH")
            ba = st.number_input("Bak L")
            ms = st.number_input("MTH Start")
            sc = st.number_input("Serwis co (MTH)", value=250.0)
            if st.form_submit_button("Dodaj"):
                new_id = df_fleet['ID'].max() + 1 if not df_fleet.empty else 1
                new_t = pd.DataFrame([[new_id, n, no, ba, ms, sc]], columns=df_fleet.columns)
                updated_fleet = pd.concat([df_fleet, new_t], ignore_index=True)
                conn.update(worksheet="fleet", data=updated_fleet)
                st.rerun()
    
    st.write("Twoja flota:")
    st.dataframe(df_fleet, use_container_width=True)
    st.write("Historia wpisów (10 ostatnich):")
    st.dataframe(df_logs.tail(10), use_container_width=True)