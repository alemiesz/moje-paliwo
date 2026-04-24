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
        
        if not i.empty: 
            i['Data_Faktury'] = pd.to_datetime(i['Data_Faktury']).dt.date
        if not l.empty: 
            l['Data'] = pd.to_datetime(l['Data']).dt.date
        return f, i, l
    except Exception as e:
        st.error(f"Błąd danych: {e}. Sprawdź czy nagłówki w Arkuszu Google są poprawne.")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

df_fleet, df_inv, df_logs = load_data()

# --- LOGIKA SYSTEMOWA ---
total_purchased = df_inv['Litry'].sum() if not df_inv.empty else 0
total_used = df_logs['Dolano'].sum() if not df_logs.empty else 0
current_stock = max(0, total_purchased - total_used)
avg_price = (df_inv['Kwota'].sum() / total_purchased) if total_purchased > 0 else 0

# --- MENU BOCZNE ---
st.sidebar.title("🚜 FarmFuel Cloud")
menu = st.sidebar.selectbox("MENU", ["Pulpit Operacyjny", "Raporty i Analizy", "Garaż i Faktury"])
target_date = st.sidebar.date_input("📅 Data dzisiejsza (wpisu)", date.today())

# --- MODUŁ 1: PULPIT ---
if menu == "Pulpit Operacyjny":
    c1, c2, c3 = st.columns(3)
    c1.metric("⛽ W zbiorniku", f"{current_stock:.1f} L")
    c2.metric("💰 Średnia cena", f"{avg_price:.2f} zł/L")
    c3.metric("🚜 Spalone (całość)", f"{df_logs['Spalone'].sum() if not df_logs.empty else 0:.0f} L")
    st.divider()
    
    col_tractors, col_gauge = st.columns([2, 1])
    with col_tractors:
        st.subheader("Stan Ciągników")
        for _, t in df_fleet.iterrows():
            t_logs = df_logs[df_logs['ID'] == t['ID']]
            last_mth = t_logs['MTH'].max() if not t_logs.empty else t['MTH_Start']
            fuel_in_t = t_logs['Dolano'].sum() - t_logs['Spalone'].sum()
            
            with st.container():
                st.markdown(f'<div style="background: rgba(30, 41, 59, 0.4); padding: 15px; border-radius: 10px; border: 1px solid #334155; margin-bottom: 10px;">', unsafe_allow_html=True)
                ca, cb, cc = st.columns([1, 1, 1])
                ca.write(f"### {t['Nazwa']}")
                ca.write(f"📟 Licznik: **{last_mth:.1f} MTH**")
                cb.write(f"⛽ Paliwo: **{fuel_in_t:.1f} L**")
                cb.progress(min(max(fuel_in_t/t['Bak'], 0.0), 1.0))
                
                with cc.expander("➕ Loguj"):
                    with st.form(f"work_{t['ID']}", clear_on_submit=True):
                        new_m = st.number_input("Stan licznika", value=float(last_mth))
                        add_f = st.number_input("Dolewasz? (L)", value=0.0)
                        if st.form_submit_button("ZAPISZ"):
                            burned = (new_m - last_mth) * t['Norma']
                            new_row = pd.DataFrame([[str(target_date), t['ID'], new_m, add_f, burned]], columns=df_logs.columns)
                            conn.update(worksheet="logs", data=pd.concat([df_logs, new_row], ignore_index=True))
                            st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

    with col_gauge:
        st.subheader("Główny Bak")
        fig = go.Figure(go.Indicator(mode = "gauge+number", value = current_stock, gauge = {'axis': {'range': [0, MAX_STORAGE]}, 'bar': {'color': "#3b82f6"}}))
        fig.update_layout(height=250, paper_bgcolor='rgba(0,0,0,0)', font_color="white", margin=dict(t=30, b=0))
        st.plotly_chart(fig, use_container_width=True)

# --- MODUŁ 2: RAPORTY (ULEPSZONY) ---
elif menu == "Raporty i Analizy":
    st.title("📊 Rozliczenie Miesięczne")
    
    cur_y = datetime.now().year
    y = st.selectbox("Wybierz Rok", range(2024, cur_y + 3), index=list(range(2024, cur_y + 3)).index(cur_y))
    m = st.selectbox("Wybierz Miesiąc", list(calendar.month_name)[1:], index=datetime.now().month-1)
    m_idx = list(calendar.month_name).index(m)
    
    m_logs = df_logs[(pd.to_datetime(df_logs['Data']).dt.year == y) & (pd.to_datetime(df_logs['Data']).dt.month == m_idx)]
    
    if not m_logs.empty:
        total_m_burned = m_logs['Spalone'].sum()
        st.markdown(f'<div style="background:#1e293b; padding:20px; border-radius:10px; border-left: 5px solid #3b82f6;"><h3>Suma zużycia w {m}: {total_m_burned:.1f} L</h3><p>Szacunkowy koszt: {(total_m_burned * avg_price):.2f} zł</p></div>', unsafe_allow_html=True)
        
        st.divider()
        st.subheader("Tabela Zbiorcza Ciągników")
        
        # Obliczanie tabeli raportu
        report_list = []
        for _, t in df_fleet.iterrows():
            t_m_logs = m_logs[m_logs['ID'] == t['ID']]
            if not t_m_logs.empty:
                m_burned = t_m_logs['Spalone'].sum()
                m_mth = t_m_logs['MTH'].max() - t_m_logs['MTH'].min()
                report_list.append({
                    "Ciągnik": t['Nazwa'],
                    "Zrobione MTH": round(m_mth, 1),
                    "Zużyte Litry": round(m_burned, 1),
                    "Koszt (zł)": round(m_burned * avg_price, 2)
                })
        
        st.table(pd.DataFrame(report_list))
        
        st.subheader("Wykres Spalania")
        st.plotly_chart(px.bar(pd.DataFrame(report_list), x='Ciągnik', y='Zużyte Litry', color='Ciągnik', text_auto=True), use_container_width=True)
    else:
        st.info("Brak danych dla wybranego miesiąca.")

# --- MODUŁ 3: GARAŻ I FAKTURY (ULEPSZONY) ---
elif menu == "Garaż i Faktury":
    st.title("⚙️ Logistyka i Flota")
    tab_f, tab_t = st.tabs(["📄 Faktury (Zakupy)", "🚜 Zarządzanie Flotą"])
    
    with tab_f:
        with st.form("new_inv"):
            st.subheader("Dodaj nową fakturę")
            c1, c2 = st.columns(2)
            inv_num = c1.text_input("Numer Faktury")
            inv_date = c2.date_input("Data na Fakturze", date.today())
            inv_qty = c1.number_input("Ilość Litrów (L)", min_value=0.0)
            inv_price = c2.number_input("Kwota Brutto (zł)", min_value=0.0)
            
            if st.form_submit_button("ZAPISZ FAKTURĘ"):
                # Data_Wpisu, Data_Faktury, Numer_Faktury, Litry, Kwota
                new_row_inv = pd.DataFrame([[str(date.today()), str(inv_date), inv_num, inv_qty, inv_price]], columns=df_inv.columns)
                conn.update(worksheet="inv", data=pd.concat([df_inv, new_row_inv], ignore_index=True))
                st.success("Faktura dodana!")
                st.rerun()
        
        st.divider()
        st.subheader("Historia Zakupów")
        if not df_inv.empty:
            st.dataframe(df_inv.sort_values('Data_Faktury', ascending=False), use_container_width=True)

    with tab_t:
        with st.expander("➕ Dodaj nowy ciągnik"):
            with st.form("add_t"):
                n = st.text_input("Nazwa")
                no = st.number_input("Norma L/MTH", value=5.0)
                ba = st.number_input("Pojemność baku (L)", value=100.0)
                ms = st.number_input("MTH Startowe", value=0.0)
                sc = st.number_input("Serwis co (MTH)", value=250.0)
                if st.form_submit_button("DODAJ"):
                    new_id = df_fleet['ID'].max() + 1 if not df_fleet.empty else 1
                    new_row_t = pd.DataFrame([[new_id, n, no, ba, ms, sc]], columns=df_fleet.columns)
                    conn.update(worksheet="fleet", data=pd.concat([df_fleet, new_row_t], ignore_index=True))
                    st.rerun()
        st.write("Twoja flota:")
        st.table(df_fleet)