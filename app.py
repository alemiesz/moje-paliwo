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
st.set_page_config(page_title="FarmFuel PRO", layout="wide")

POLSKIE_MIESIACE = [
    "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec", 
    "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"
]

conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    try:
        f = conn.read(worksheet="fleet", ttl=0).dropna(how="all")
        i = conn.read(worksheet="inv", ttl=0).dropna(how="all")
        l = conn.read(worksheet="logs", ttl=0).dropna(how="all")
        if not i.empty: i['Data_Faktury'] = pd.to_datetime(i['Data_Faktury']).dt.date
        if not l.empty: l['Data'] = pd.to_datetime(l['Data']).dt.date
        return f, i, l
    except Exception as e:
        st.error(f"Błąd danych: {e}")
        st.stop()

df_fleet, df_inv, df_logs = load_data()

# --- LOGIKA OBLICZEŃ ---
total_purchased = round(df_inv['Litry'].sum(), 1) if not df_inv.empty else 0
total_used = round(df_logs['Dolano'].sum(), 1) if not df_logs.empty else 0
current_stock = round(max(0, total_purchased - total_used), 1)
avg_price = round((df_inv['Kwota'].sum() / total_purchased), 2) if total_purchased > 0 else 0

# --- MENU BOCZNE ---
st.sidebar.title("⛽ FarmFuel PRO")
menu = st.sidebar.radio("NAWIGACJA", ["🏠 Pulpit Operacyjny", "📊 Raporty i Analizy", "🛠️ Garaż i Faktury"])
target_date = st.sidebar.date_input("📅 Data wpisu", date.today())

# --- MODUŁ 1: PULPIT ---
if menu == "🏠 Pulpit Operacyjny":
    c1, c2, c3 = st.columns(3)
    c1.metric("⛽ W zbiorniku głównym", f"{current_stock:.1f} L")
    c2.metric("💰 Średnia cena ON", f"{avg_price:.2f} zł/L")
    c3.metric("🚜 Spalone (całość)", f"{df_logs['Spalone'].sum() if not df_logs.empty else 0:.1f} L")
    
    st.divider()
    
    col_tractors, col_gauge = st.columns([2, 1])
    
    with col_tractors:
        st.subheader("Monitoring Ciągników")
        for _, t in df_fleet.iterrows():
            t_logs = df_logs[df_logs['ID'] == t['ID']]
            last_mth = round(t_logs['MTH'].max(), 1) if not t_logs.empty else round(t['MTH_Start'], 1)
            fuel_in_t = round(t_logs['Dolano'].sum() - t_logs['Spalone'].sum(), 1)
            
            # Serwis
            mth_since_start = last_mth - t['MTH_Start']
            to_service = round(t['Serwis_Co'] - (mth_since_start % t['Serwis_Co']), 1)
            
            st.markdown(f'<div style="background: rgba(30, 41, 59, 0.4); padding: 15px; border-radius: 10px; border: 1px solid #334155; margin-bottom: 15px;"><span style="font-size: 18px; font-weight: bold;">{t["Nazwa"]}</span></div>', unsafe_allow_html=True)
            
            ca, cb, cc = st.columns([1, 1, 1])
            ca.write(f"📟 Licznik: **{last_mth:.1f} MTH**")
            cb.write(f"⛽ Bak: **{fuel_in_t:.1f} L**")
            cb.progress(min(max(fuel_in_t/t['Bak'], 0.0), 1.0))
            
            s_color = "#10b981" if to_service > 50 else "#f59e0b" if to_service > 10 else "#ef4444"
            cc.write(f"🔧 Serwis: **{to_service:.1f} MTH**")
            cc.markdown(f'<div style="height:8px; width:100%; background:#334155; border-radius:5px;"><div style="height:8px; width:{max(0, (to_service/t["Serwis_Co"])*100)}%; background:{s_color}; border-radius:5px;"></div></div>', unsafe_allow_html=True)
            
            with st.expander(f"Zapisz pracę / tankowanie"):
                with st.form(f"work_{t['ID']}", clear_on_submit=True):
                    new_m = st.number_input("Bieżący licznik MTH", value=float(last_mth), step=0.1)
                    add_f = st.number_input("Dolałeś paliwa? (L)", value=0.0, step=1.0)
                    if st.form_submit_button("ZAPISZ"):
                        burned = round((new_m - last_mth) * t['Norma'], 1)
                        new_row = pd.DataFrame([[str(target_date), t['ID'], round(new_m, 1), round(add_f, 1), burned]], columns=df_logs.columns)
                        conn.update(worksheet="logs", data=pd.concat([df_logs, new_row], ignore_index=True))
                        st.rerun()
            st.divider()

    with col_gauge:
        st.subheader("Główny Bak")
        fig = go.Figure(go.Indicator(
            mode = "gauge+number", value = current_stock,
            number = {'valueformat': '.1f'},
            gauge = {'axis': {'range': [0, MAX_STORAGE], 'tickformat': '.1f'}, 'bar': {'color': "#3b82f6" if current_stock > LOW_FUEL_ALERT else "#ef4444"}}
        ))
        fig.update_layout(height=300, paper_bgcolor='rgba(0,0,0,0)', font_color="white", margin=dict(t=50, b=0))
        st.plotly_chart(fig, use_container_width=True)

# --- MODUŁ 2: RAPORTY ---
elif menu == "📊 Raporty i Analizy":
    st.title("📊 Rozliczenie Miesięczne")
    cur_y = datetime.now().year
    col_y, col_m = st.columns(2)
    with col_y: y = st.selectbox("Rok", range(2024, cur_y + 3), index=list(range(2024, cur_y + 3)).index(cur_y))
    with col_m: m_nazwa = st.selectbox("Miesiąc", POLSKIE_MIESIACE, index=datetime.now().month-1)
    
    m_idx = POLSKIE_MIESIACE.index(m_nazwa) + 1
    m_logs = df_logs[(pd.to_datetime(df_logs['Data']).dt.year == y) & (pd.to_datetime(df_logs['Data']).dt.month == m_idx)]
    
    if not m_logs.empty:
        total_m_burned = round(m_logs['Spalone'].sum(), 1)
        st.info(f"Podsumowanie: {m_nazwa} {y} | Zużycie: {total_m_burned:.1f} L | Koszt: {(total_m_burned * avg_price):.2f} zł")
        
        report_list = []
        for _, t in df_fleet.iterrows():
            t_m_logs = m_logs[m_logs['ID'] == t['ID']]
            if not t_m_logs.empty:
                m_burned = round(t_m_logs['Spalone'].sum(), 1)
                m_mth = round(t_m_logs['MTH'].max() - t_m_logs['MTH'].min(), 1)
                report_list.append({
                    "Ciągnik": t['Nazwa'],
                    "Zrobione MTH": m_mth,
                    "Zużyte Litry": m_burned,
                    "Koszt (zł)": round(m_burned * avg_price, 2)
                })
        
        df_rep = pd.DataFrame(report_list)
        # Formatowanie tabeli dla pewności wyświetlania 1 miejsca
        st.table(df_rep.style.format({
            "Zrobione MTH": "{:.1f}",
            "Zużyte Litry": "{:.1f}",
            "Koszt (zł)": "{:.2f}"
        }))
        
        st.plotly_chart(px.bar(df_rep, x='Ciągnik', y='Zużyte Litry', color='Ciągnik', text_auto=".1f"), use_container_width=True)
    else:
        st.info(f"Brak danych dla {m_nazwa} {y}.")

# --- MODUŁ 3: GARAŻ ---
elif menu == "🛠️ Garaż i Faktury":
    st.title("⚙️ Logistyka")
    tab_f, tab_t = st.tabs(["📄 Faktury", "🚜 Flota"])
    with tab_f:
        with st.form("new_inv", clear_on_submit=True):
            c1, c2 = st.columns(2)
            inv_num = c1.text_input("Numer Faktury")
            inv_date = c2.date_input("Data Faktury", date.today())
            inv_qty = c1.number_input("Litry", min_value=0.0, step=1.0)
            inv_price = c2.number_input("Kwota brutto", min_value=0.0, step=1.0)
            if st.form_submit_button("Zapisz Fakturę"):
                new_row = pd.DataFrame([[str(date.today()), str(inv_date), inv_num, round(inv_qty, 1), round(inv_price, 2)]], columns=df_inv.columns)
                conn.update(worksheet="inv", data=pd.concat([df_inv, new_row], ignore_index=True))
                st.rerun()
        st.dataframe(df_inv.sort_values('Data_Faktury', ascending=False), use_container_width=True)
    with tab_t:
        st.table(df_fleet)