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
st.set_page_config(page_title="FarmFuel Cloud Ultimate", layout="wide")

# Połączenie
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNKCJA ODCZYTU ---
def load_data():
    try:
        f = conn.read(worksheet="fleet", ttl=0)
        i = conn.read(worksheet="inv", ttl=0)
        l = conn.read(worksheet="logs", ttl=0)
        
        f = f.dropna(how="all")
        i = i.dropna(how="all")
        l = l.dropna(how="all")
        
        if not i.empty: i['Data'] = pd.to_datetime(i['Data']).dt.date
        if not l.empty: l['Data'] = pd.to_datetime(l['Data']).dt.date
        return f, i, l
    except Exception as e:
        st.error(f"Błąd danych: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_fleet, df_inv, df_logs = load_data()

# --- LOGIKA SYSTEMOWA ---
total_purchased = df_inv['Litry'].sum() if not df_inv.empty else 0
total_used = df_logs['Dolano'].sum() if not df_logs.empty else 0
current_stock = max(0, total_purchased - total_used)
avg_price = (df_inv['Kwota'].sum() / total_purchased) if total_purchased > 0 else 0

# Prognoza paliwa (na podstawie ostatnich 7 dni)
if not df_logs.empty:
    last_week = df_logs[df_logs['Data'] > (date.today() - timedelta(days=7))]['Spalone'].sum()
    daily_avg = last_week / 7
    days_left = current_stock / daily_avg if daily_avg > 0 else 0
else:
    days_left = 0

# --- STYLIZACJA CSS ---
st.markdown("""
    <style>
    .tractor-card { background: rgba(30, 41, 59, 0.4); padding: 20px; border-radius: 15px; border: 1px solid #334155; margin-bottom: 15px; }
    .metric-box { background: rgba(15, 23, 42, 0.6); padding: 15px; border-radius: 12px; text-align: center; border: 1px solid #1e293b; }
    </style>
    """, unsafe_allow_html=True)

# --- MENU BOCZNE ---
st.sidebar.title("🚜 FarmFuel Cloud")
menu = st.sidebar.selectbox("MENU", ["Pulpit Operacyjny", "Raporty i Analizy", "Garaż i Faktury"])
target_date = st.sidebar.date_input("📅 Data wpisu", date.today())

# --- MODUŁ 1: PULPIT ---
if menu == "Pulpit Operacyjny":
    # Wskaźniki u góry
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(f'<div class="metric-box">💰 Średnia Cena<br><span style="font-size:22px; color:#10b981;">{avg_price:.2f} zł/L</span></div>', unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="metric-box">⛽ W zbiorniku<br><span style="font-size:22px; color:#3b82f6;">{current_stock:.1f} L</span></div>', unsafe_allow_html=True)
    with c3: 
        color = "#10b981" if days_left > 3 else "#ef4444"
        st.markdown(f'<div class="metric-box">⏳ Zapas na<br><span style="font-size:22px; color:{color};">{days_left:.1f} dni</span></div>', unsafe_allow_html=True)
    with c4: st.markdown(f'<div class="metric-box">🚜 Spalone (suma)<br><span style="font-size:22px; color:#8b5cf6;">{df_logs["Spalone"].sum() if not df_logs.empty else 0:.0f} L</span></div>', unsafe_allow_html=True)

    st.divider()
    
    col_tractors, col_gauge = st.columns([2, 1])
    
    with col_tractors:
        st.subheader("Monitoring Maszyn")
        for _, t in df_fleet.iterrows():
            t_logs = df_logs[df_logs['ID'] == t['ID']]
            last_mth = t_logs['MTH'].max() if not t_logs.empty else t['MTH_Start']
            fuel_in_t = t_logs['Dolano'].sum() - t_logs['Spalone'].sum()
            
            # Serwis
            mth_since_start = last_mth - t['MTH_Start']
            to_service = t['Serwis_Co'] - (mth_since_start % t['Serwis_Co'])
            
            st.markdown(f'<div class="tractor-card">', unsafe_allow_html=True)
            ca, cb, cc = st.columns([1, 1, 1])
            ca.markdown(f"### {t['Nazwa']}")
            ca.write(f"📟 Licznik: **{last_mth:.1f} MTH**")
            
            cb.write(f"⛽ Paliwo: **{fuel_in_t:.1f} L**")
            cb.progress(min(max(fuel_in_t/t['Bak'], 0.0), 1.0))
            
            s_color = "#10b981" if to_service > 50 else "#f59e0b" if to_service > 10 else "#ef4444"
            cc.write(f"🔧 Serwis za: **{to_service:.1f} MTH**")
            cc.markdown(f'<div style="height:8px; width:100%; background:#334155; border-radius:5px;"><div style="height:8px; width:{max(0, (to_service/t["Serwis_Co"])*100)}%; background:{s_color}; border-radius:5px;"></div></div>', unsafe_allow_html=True)
            
            with st.expander(f"➕ Rejestruj pracę {t['Nazwa']}"):
                with st.form(f"work_{t['ID']}", clear_on_submit=True):
                    new_m = st.number_input("Bieżący licznik MTH", value=float(last_mth))
                    add_f = st.number_input("Ile litrów dolałeś?", value=0.0)
                    if st.form_submit_button("ZAPISZ W CHMURZE"):
                        burned = (new_m - last_mth) * t['Norma']
                        new_row = pd.DataFrame([[str(target_date), t['ID'], new_m, add_f, burned]], columns=df_logs.columns)
                        updated_logs = pd.concat([df_logs, new_row], ignore_index=True)
                        conn.update(worksheet="logs", data=updated_logs)
                        st.success("Zaktualizowano Google Sheets!")
                        st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    with col_gauge:
        st.subheader("Główny Zbiornik")
        fig = go.Figure(go.Indicator(
            mode = "gauge+number", value = current_stock,
            gauge = {
                'axis': {'range': [0, MAX_STORAGE]},
                'bar': {'color': "#3b82f6" if current_stock > LOW_FUEL_ALERT else "#ef4444"},
                'steps': [{'range': [0, LOW_FUEL_ALERT], 'color': "rgba(239, 68, 68, 0.2)"}]
            }
        ))
        fig.update_layout(height=300, paper_bgcolor='rgba(0,0,0,0)', font_color="white", margin=dict(t=50, b=0))
        st.plotly_chart(fig, use_container_width=True)

# --- MODUŁ 2: RAPORTY ---
elif menu == "Raporty i Analizy":
    st.title("📊 Analiza Zużycia")
    cur_y = datetime.now().year
    years = range(2024, cur_y + 3)
    c1, c2 = st.columns(2)
    y = c1.selectbox("Rok", years, index=list(years).index(cur_y))
    m = c2.selectbox("Miesiąc", list(calendar.month_name)[1:], index=datetime.now().month-1)
    
    m_idx = list(calendar.month_name).index(m)
    m_logs = df_logs[(pd.to_datetime(df_logs['Data']).dt.year == y) & (pd.to_datetime(df_logs['Data']).dt.month == m_idx)]
    
    if not m_logs.empty:
        res = m_logs.merge(df_fleet, on='ID').groupby('Nazwa')['Spalone'].sum().reset_index()
        col_a, col_b = st.columns(2)
        with col_a:
            st.plotly_chart(px.pie(res, values='Spalone', names='Nazwa', title="Udział w spalaniu"), use_container_width=True)
        with col_b:
            st.plotly_chart(px.bar(res, x='Nazwa', y='Spalone', title="Litry na ciągnik"), use_container_width=True)
        
        st.write("Szczegóły miesiąca:")
        st.dataframe(m_logs, use_container_width=True)
    else:
        st.info("Brak danych dla wybranego okresu.")

# --- MODUŁ 3: GARAŻ ---
elif menu == "Garaż i Faktury":
    st.title("⚙️ Garaż i Logistyka")
    
    tab_f, tab_t = st.tabs(["📄 Faktury", "🚜 Flota"])
    
    with tab_f:
        with st.form("new_inv"):
            st.write("Dodaj nową fakturę")
            l = st.number_input("Ilość (L)", value=100.0)
            k = st.number_input("Kwota (zł)", value=600.0)
            if st.form_submit_button("DODAJ FAKTURĘ"):
                new_i = pd.DataFrame([[str(target_date), l, k]], columns=df_inv.columns)
                updated_inv = pd.concat([df_inv, new_i], ignore_index=True)
                conn.update(worksheet="inv", data=updated_inv)
                st.rerun()
        st.dataframe(df_inv.sort_values('Data', ascending=False), use_container_width=True)

    with tab_t:
        with st.expander("➕ Dodaj nowy ciągnik"):
            with st.form("add_t"):
                n = st.text_input("Nazwa ciągnika")
                no = st.number_input("Norma L/MTH", value=5.0)
                ba = st.number_input("Pojemność baku (L)", value=100.0)
                ms = st.number_input("MTH Startowe", value=0.0)
                sc = st.number_input("Serwis co (MTH)", value=250.0)
                if st.form_submit_button("DODAJ DO FLOTY"):
                    new_id = df_fleet['ID'].max() + 1 if not df_fleet.empty else 1
                    new_row = pd.DataFrame([[new_id, n, no, ba, ms, sc]], columns=df_fleet.columns)
                    updated_fleet = pd.concat([df_fleet, new_row], ignore_index=True)
                    conn.update(worksheet="fleet", data=updated_fleet)
                    st.rerun()
        st.dataframe(df_fleet, use_container_width=True)