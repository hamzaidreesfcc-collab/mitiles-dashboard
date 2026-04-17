import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from itertools import combinations
import time
import google.auth.transport.requests
import smtplib
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
st.set_page_config(page_title="Mi-Tiles Intelligence", page_icon="🏠", layout="wide", initial_sidebar_state="expanded")

DATA_PATH = st.secrets.get("DATA_PATH", r"C:\Users\hp\OneDrive\Desktop\5.3.25.xlsx")
SESSION_TIMEOUT = 20 * 60
LOCAL_ADJ       = 0.047
IMPORTED_ADJ    = 0.13

EXPENSES_TEMPLATE = {
    "Salaries & Wages":     {"FIDA": 125000, "SAQIB": 125000, "ASHAR": 45000,
                             "JAVED": 45000, "ZEESHAN": 45000, "AFTAB": 45000,
                             "HAMMAD": 45000, "KHURRAM": 45000, "Other Staff": 0},
    "Rent":                 {"Showroom": 0, "Warehouse": 0},
    "Utilities":            {"Electricity": 0, "Gas": 0, "Internet": 0},
    "Transport & Delivery": {"Transport": 0},
    "Marketing":            {"Digital Marketing": 0, "Print": 0},
    "Other Expenses":       {"Miscellaneous": 0},
}

ASSETS_TEMPLATE = {
    "Current Assets": {"Cash in Hand": 0, "Cash at Bank": 0, "Trade Receivables": 0,
                       "Advance to Suppliers": 0, "Other Current Assets": 0},
    "Fixed Assets":   {"Furniture & Fixtures": 0, "Vehicles": 0, "Equipment": 0, "Building/Leasehold": 0},
    "Liabilities":    {"Trade Payables": 0, "Short Term Loans": 0, "Long Term Loans": 0, "Other Liabilities": 0}
}

def send_login_alert(username, ip_info="Streamlit Cloud"):
    try:
        alert_email = st.secrets.get("ALERT_EMAIL", "")
        smtp_pass   = st.secrets.get("SMTP_PASSWORD", "")
        if not alert_email or not smtp_pass:
            return
        msg = MIMEMultipart()
        msg['From']    = alert_email
        msg['To']      = alert_email
        msg['Subject'] = f"🔐 Mi-Tiles Login Alert — {username}"
        body = f"""
Mi-Tiles Dashboard Login Alert

User:     {username}
Time:     {datetime.now().strftime('%d %b %Y %H:%M:%S')}
Location: {ip_info}

If this was not you, change your password immediately.
        """
        msg.attach(MIMEText(body, 'plain'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(alert_email, smtp_pass)
            server.send_message(msg)
    except Exception:
        pass  # Silent fail — never block login due to email issues

# ─────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────
USERS = {
    "hamza": {"password": st.secrets.get("PASS_HAMZA", ""), "role": "admin", "name": "Hamza"},
}

def login():
    st.markdown("<div style='text-align:center;padding:60px 0 20px'><h1>🏠 Mi-Tiles</h1><h3 style='color:gray'>Inventory Intelligence Dashboard</h3></div>", unsafe_allow_html=True)
    _, col, _ = st.columns([1,1,1])
    with col:
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Login", use_container_width=True):
            if u in USERS and USERS[u]["password"] == p:
                st.session_state.update({'logged_in':True,'user':u,'role':USERS[u]["role"],'name':USERS[u]["name"],'last_active':time.time()})
                send_login_alert(u)
                st.rerun()
            else:
                st.error("Invalid username or password")

def check_session():
    if 'last_active' in st.session_state:
        if time.time() - st.session_state['last_active'] > SESSION_TIMEOUT:
            for k in ['logged_in','user','role','name','last_active']: st.session_state.pop(k, None)
            st.warning("Session expired."); st.rerun()
    st.session_state['last_active'] = time.time()

if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if not st.session_state['logged_in']: login(); st.stop()
check_session()
is_admin = st.session_state['role'] == 'admin'

# ─────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_data(path):
    import io
    import requests
    from google.oauth2 import service_account
    import google.auth.transport.requests

    try:
        creds = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=["https://www.googleapis.com/auth/drive.readonly"]
        )
        auth_req = google.auth.transport.requests.Request()
        creds.refresh(auth_req)

        file_id = st.secrets.get("GOOGLE_FILE_ID", "1ikdIp0wAtDD8B2PCDTc0X_cyxyXwaolLw_HTZtnT6No")
        download_url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx"

        response = requests.get(download_url, headers={"Authorization": f"Bearer {creds.token}"}, timeout=60)
        response.raise_for_status()
        buffer = io.BytesIO(response.content)

    except Exception as e:
        st.error(f"Failed to load data: {e}")
        st.stop()

    df   = pd.read_excel(buffer, sheet_name='SALE HISTORY')
    buffer.seek(0)
    prod = pd.read_excel(buffer, sheet_name='PRODUCT DATA')

    df['Date'] = pd.to_datetime(df['Date'].astype(str).str.strip(), format='%d-%m-%Y   %I:%M %p', errors='coerce')
    df['Sale Day'] = df['Date'].dt.date
    df['Month']    = df['Date'].dt.to_period('M').astype(str)
    df['Year']     = df['Date'].dt.year
    df['Bill No.'] = df['Bill No.'].astype(str)
    df['Account Name'] = df['Account Name'].astype(str).str.replace('\xa0',' ').str.strip()

    for col in ['Sq.m','Rate','Closing','Profit','SALE','RETURN','GROSS PROFIT','NET SALE']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    sale_mask = (df['SALE'] == 0) & (df['Type'] == 'S')
    df.loc[sale_mask, 'SALE'] = df.loc[sale_mask, 'Sq.m'] * df.loc[sale_mask, 'Rate']
    ret_mask = (df['RETURN'] == 0) & (df['Type'] == 'S.R')
    df.loc[ret_mask, 'RETURN'] = df.loc[ret_mask, 'Sq.m'] * df.loc[ret_mask, 'Rate']

    df['Product No.']  = df['Product No.'].astype(str).str.replace('\xa0',' ').str.strip()
    prod['Product No.']= prod['Product No.'].astype(str).str.replace('\xa0',' ').str.strip()

    if 'Size' in df.columns: df = df.drop(columns=['Size'])
    df = df.merge(prod[['Product No.','Brand Name','Category','Sub-Category','Size','Company Name','Sq.m/Box']], on='Product No.', how='left')

    purch = df[df['Type'].isin(['P','O.S'])].copy()
    wac   = purch.groupby('Product No.').apply(lambda x: (x['Sq.m']*x['Rate']).sum()/x['Sq.m'].sum() if x['Sq.m'].sum()>0 else 0).reset_index()
    wac.columns = ['Product No.','WAC Rate']
    df = df.merge(wac, on='Product No.', how='left')
    df['WAC Rate'] = df['WAC Rate'].fillna(0)

    def ap(row):
        adj = LOCAL_ADJ if 'LOCAL' in str(row.get('Category','')).upper() else IMPORTED_ADJ
        return row['SALE'] - row['Sq.m'] * row['WAC Rate'] * (1 - adj)
    df['Actual Profit'] = df.apply(ap, axis=1)

    return df, prod


@st.cache_data(ttl=3600)
def build_pi(_df, _prod):
    today = pd.Timestamp.today().normalize()
    results = []
    for prod_no, g in _df.groupby('Product No.'):
        pur = g[g['Type'].isin(['P','O.S'])]
        sal = g[g['Type'] == 'S']
        ret = g[g['Type'].isin(['S.R','P.R','D.S'])]
        fp  = pur['Date'].min() if len(pur)>0 else pd.NaT
        ls  = sal['Date'].max() if len(sal)>0 else pd.NaT
        di  = int((today-pd.Timestamp(fp)).days) if pd.notna(fp) else None
        ds  = int((today-pd.Timestamp(ls)).days) if pd.notna(ls) else None
        cs  = g.sort_values('Date').iloc[-1]['Closing'] if len(g)>0 else 0
        ts  = sal['Sq.m'].sum()
        ns  = max(0, ts - ret['Sq.m'].sum())
        s30 = sal[sal['Date']>=today-timedelta(30)]['Sq.m'].sum()
        s90 = sal[sal['Date']>=today-timedelta(90)]['Sq.m'].sum()
        s180= sal[sal['Date']>=today-timedelta(180)]['Sq.m'].sum()
        s360= sal[sal['Date']>=today-timedelta(360)]['Sq.m'].sum()
        vel = (ns/di*30) if di and di>0 else 0
        psq = pur['Sq.m'].sum(); pval= (pur['Sq.m']*pur['Rate']).sum()
        wac = pval/psq if psq>0 else 0
        sv  = max(0,cs)*wac
        mos = (cs/vel) if vel>0 and cs>0 else 0
        sdays= sal['Date'].dt.date.nunique() if len(sal)>0 else 0
        freq = sdays/di if di and di>0 else 0
        avd  = ns/di if di and di>0 else 0
        std  = sal['Sq.m'].std() if len(sal)>1 else 0
        cv   = std/avd if avd>0 else 0
        rev  = sal['SALE'].sum(); erpp=sal['Profit'].sum(); actp=sal['Actual Profit'].sum()
        em   = (erpp/rev*100) if rev>0 else 0; am=(actp/rev*100) if rev>0 else 0

        # Composite Reorder Score
        unique_customers = sal['Account Name'].nunique() if len(sal)>0 else 0
        vel_norm  = min(vel/500*100,  100) if vel>0  else 0
        cust_norm = min(unique_customers/50*100, 100) if unique_customers>0 else 0
        freq_norm = min(freq/0.3*100, 100) if freq>0 else 0
        st_norm   = min((ns/max(psq,1))*100, 100)
        reorder_score = round(vel_norm*0.40 + cust_norm*0.25 + freq_norm*0.20 + st_norm*0.15, 1)

        if ns<=0:              dp='No Sales / Returns Only'
        elif freq>=0.15 and cv<3: dp='Stable Fast Mover'
        elif freq>=0.15:       dp='Volatile Fast Mover'
        elif 0.05<=freq<0.15 and cv<3: dp='Slow Stable'
        elif 0.05<=freq<0.15:  dp='Erratic Demand'
        else:                  dp='Dead / Negligible'

        if cs<=0:              inv='Out of Stock'
        elif ds is None:       inv='No Sales'
        elif ds<=30:           inv='Active'
        elif ds<=90:           inv='Slow'
        elif ds<=180:          inv='At Risk'
        elif ds<=360:          inv='Critical'
        else:                  inv='Dead Stock'

        if cs<=0:              sh='No Stock'
        elif mos<=1:           sh='Reorder Now'
        elif mos<=3:           sh='Healthy'
        elif mos<=6:           sh='Overstocked'
        else:                  sh='Dead Stock'

        total_months = _df['Date'].dt.to_period('M').nunique()
        cons = sdays/total_months*100 if total_months>0 else 0
        xyz  = 'X' if cons>=50 else ('Y' if cons>=20 else 'Z')

        results.append({'Product No.':prod_no,'First Purchase Date':fp.date() if pd.notna(fp) else None,
            'Last Sale Date':ls.date() if pd.notna(ls) else None,'Days in Inventory':di,
            'Days Since Last Sale':ds,'Total Sales Sqm':round(ts,2),'Net Sales Sqm':round(ns,2),
            'Sales Last 30 Days':round(s30,2),'Sales Last 90 Days':round(s90,2),
            'Sales Last 180 Days':round(s180,2),'Sales Last 360 Days':round(s360,2),
            'Sales Velocity/Month':round(vel,2),'Current Stock Sqm':round(cs,2),
            'WAC Rate':round(wac,2),'Stock Value PKR':round(sv,2),'Months of Stock':round(mos,2),
            'Total Revenue':round(rev,2),'ERP Profit':round(erpp,2),'Actual Profit':round(actp,2),
            'ERP Margin %':round(em,2),'Actual Margin %':round(am,2),
            'Demand Pattern':dp,'Inventory Status':inv,'Stock Health':sh,'XYZ':xyz,
            'Consistency %':round(cons,1),'Reorder Score':reorder_score})

    pi = pd.DataFrame(results)
    pi = pi.merge(_prod[['Product No.','Brand Name','Category','Sub-Category','Size','Company Name','Sq.m/Box']], on='Product No.', how='left')
    pi = pi.sort_values('Total Revenue', ascending=False)
    pi['Cum %'] = pi['Total Revenue'].cumsum()/pi['Total Revenue'].sum()*100
    pi['ABC']   = pi['Cum %'].apply(lambda x: 'A' if x<=70 else ('B' if x<=90 else 'C'))
    pi['ABC_XYZ']= pi['ABC'] + pi['XYZ']

    purch2  = _df[_df['Type'].isin(['P','O.S'])].groupby('Product No.')['Sq.m'].sum().reset_index()
    purch2.columns=['Product No.','Total Purchased']
    sold2   = _df[_df['Type']=='S'].groupby('Product No.')['Sq.m'].sum().reset_index()
    sold2.columns=['Product No.','Total Sold']
    str2    = purch2.merge(sold2, on='Product No.', how='left').fillna(0)
    str2['Sell Through %'] = (str2['Total Sold']/str2['Total Purchased']*100).round(1)
    pi = pi.merge(str2[['Product No.','Sell Through %']], on='Product No.', how='left')

    return pi


@st.cache_data(ttl=3600)
def build_pairs(_df, _prod):
    sales = _df[_df['Type']=='S'].copy()
    bill_prods = sales.groupby('Bill No.').apply(
        lambda x: list({p:(p,s) for p,s in zip(x['Product No.'],x['Size'].fillna('?'))}.values())
    ).reset_index()
    bill_prods.columns = ['Bill No.','Products']
    bill_prods = bill_prods[bill_prods['Products'].apply(len)>=2]
    pair_counts = {}
    for _, row in bill_prods.iterrows():
        items = row['Products'][:8]
        for i in range(len(items)):
            for j in range(i+1, len(items)):
                p1,s1 = items[i]; p2,s2 = items[j]
                if p1>p2: p1,s1,p2,s2 = p2,s2,p1,s1
                key=(p1,s1,p2,s2)
                pair_counts[key] = pair_counts.get(key,0)+1
    pairs = pd.DataFrame([(k[0],k[1],k[2],k[3],v) for k,v in pair_counts.items()],
                          columns=['Product A','Size A','Product B','Size B','Co-occurrence'])
    pairs = pairs.sort_values('Co-occurrence', ascending=False).head(2000)
    bill_sizes = sales.groupby('Bill No.')['Size'].apply(lambda x: list(set(x.dropna()))).reset_index()
    bill_sizes = bill_sizes[bill_sizes['Size'].apply(len)>=2]
    sp = {}
    for _, row in bill_sizes.iterrows():
        for s1,s2 in combinations(sorted(row['Size']),2):
            key=(s1,s2); sp[key]=sp.get(key,0)+1
    size_pairs = pd.DataFrame([(k[0],k[1],v) for k,v in sp.items()],
                               columns=['Size A','Size B','Co-occurrence']).sort_values('Co-occurrence',ascending=False)
    return pairs, size_pairs


# ─────────────────────────────────────────────
# LOAD
# ─────────────────────────────────────────────
with st.spinner("Loading Mi-Tiles data..."):
    df, prod = load_data(DATA_PATH)
    pi       = build_pi(df, prod)
    pairs_df, size_pairs_df = build_pairs(df, prod)

# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"👤 **{st.session_state['name']}** ({st.session_state['role']})")
    elapsed = time.time()-st.session_state.get('last_active',time.time())
    remaining = max(0, SESSION_TIMEOUT-elapsed)
    st.caption(f"⏱ {int(remaining//60)}m {int(remaining%60)}s remaining")
    if st.button("🚪 Logout"):
        for k in ['logged_in','user','role','name','last_active']: st.session_state.pop(k,None)
        st.rerun()
    st.divider()
    page = st.radio("Navigate",[
        "📊 Overview","📈 Sales Trends","🔴 Dead Stock","✅ Fast Movers",
        "📦 Product Intelligence","🏭 Brand & Company","👤 Customer Intelligence",
        "💰 Margin Analysis","🧑‍💼 Salesman Performance","🎯 Incentive Calculator",
        "🏹 Dead Stock Targets","🛒 Product Pairs","📊 ABC-XYZ Analysis",
        "📉 Sell Through","🔮 Demand Forecast","⚠️ Reorder Alerts",
        "📦 Stock Comparison","🔍 Search","📊 Period Comparison",
        "📦 Closing Stock","📋 Income Statement","🏦 Assets Position",
        "📊 Salesman Rate Analysis",
    ], label_visibility="collapsed")
    st.divider()
    if st.button("🔄 Refresh Data"): st.cache_data.clear(); st.rerun()
    st.caption(f"Updated: {datetime.now().strftime('%d %b %Y %H:%M')}")

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def fmt_m(v): return f"Rs {v/1e6:.2f}M"
def fmt_k(v): return f"Rs {v/1e3:.1f}K"

def global_filters(df, key_prefix, show_date=True, show_salesman=True, show_warehouse=True, show_inventory=False):
    dff = df.copy()
    if show_date:
        c1, c2 = st.columns([2,1])
        with c1:
            min_d = df['Date'].min().date(); max_d = df['Date'].max().date()
            dr = st.date_input("📅 Date Range", value=(min_d,max_d), min_value=min_d, max_value=max_d, key=f"{key_prefix}_date")
            if len(dr)==2:
                s,e = dr
                dff = dff[(dff['Date'].dt.date>=s)&(dff['Date'].dt.date<=e)]
        with c2:
            if show_warehouse:
                wh = st.selectbox("Warehouse", ['All']+sorted(df['Warehouse'].dropna().unique().tolist()), key=f"{key_prefix}_wh")
                if wh!='All': dff=dff[dff['Warehouse']==wh]
    c1,c2,c3,c4 = st.columns(4)
    with c1:
        br = st.selectbox("Brand", ['All']+sorted(df['Brand Name'].dropna().unique().tolist()), key=f"{key_prefix}_br")
        if br!='All': dff=dff[dff['Brand Name']==br]
    with c2:
        co = st.selectbox("Company", ['All']+sorted(df['Company Name'].dropna().unique().tolist()), key=f"{key_prefix}_co")
        if co!='All': dff=dff[dff['Company Name']==co]
    with c3:
        cat = st.selectbox("Category", ['All']+sorted(df['Category'].dropna().unique().tolist()), key=f"{key_prefix}_cat")
        if cat!='All': dff=dff[dff['Category']==cat]
    with c4:
        sz = st.selectbox("Size", ['All']+sorted(prod['Size'].dropna().unique().tolist()), key=f"{key_prefix}_sz")
        if sz!='All': dff=dff[dff['Size']==sz]
    if show_salesman and not show_date:
        sal = st.selectbox("Salesman", ['All']+sorted(df['Salesman'].dropna().unique().tolist()), key=f"{key_prefix}_sal")
        if sal!='All': dff=dff[dff['Salesman']==sal]
    elif show_salesman:
        c1,c2 = st.columns(2)
        with c1:
            sal = st.selectbox("Salesman", ['All']+sorted(df['Salesman'].dropna().unique().tolist()), key=f"{key_prefix}_sal")
            if sal!='All': dff=dff[dff['Salesman']==sal]
    return dff

def pi_filters(pi_df, key_prefix):
    flt = pi_df.copy()
    c1,c2,c3,c4,c5 = st.columns(5)
    with c1:
        br = st.selectbox("Brand", ['All']+sorted(pi_df['Brand Name'].dropna().unique().tolist()), key=f"{key_prefix}_br")
        if br!='All': flt=flt[flt['Brand Name']==br]
    with c2:
        co = st.selectbox("Company", ['All']+sorted(pi_df['Company Name'].dropna().unique().tolist()), key=f"{key_prefix}_co")
        if co!='All': flt=flt[flt['Company Name']==co]
    with c3:
        cat = st.selectbox("Category", ['All']+sorted(pi_df['Category'].dropna().unique().tolist()), key=f"{key_prefix}_cat")
        if cat!='All': flt=flt[flt['Category']==cat]
    with c4:
        sz = st.selectbox("Size", ['All']+sorted(prod['Size'].dropna().unique().tolist()), key=f"{key_prefix}_sz")
        if sz!='All': flt=flt[flt['Size']==sz]
    with c5:
        st_f = st.selectbox("Stock Health", ['All']+sorted(pi_df['Stock Health'].dropna().unique().tolist()), key=f"{key_prefix}_sh")
        if st_f!='All': flt=flt[flt['Stock Health']==st_f]
    return flt


# ─────────────────────────────────────────────
# PAGE 1 — OVERVIEW
# ─────────────────────────────────────────────
if page == "📊 Overview":
    st.title("📊 Inventory Overview")
    with st.expander("🔍 Filters", expanded=False):
        dff = global_filters(df, "ov")
    sales_df = dff[dff['Type']=='S'].copy()
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Total Stock Value",   fmt_m(pi['Stock Value PKR'].sum()))
    c2.metric("Total Stock Sqm",     f"{pi[pi['Current Stock Sqm']>0]['Current Stock Sqm'].sum():,.0f}")
    c3.metric("Active Products",     f"{(pi['Inventory Status']=='Active').sum():,}")
    c4.metric("Dead Stock Products", f"{(pi['Inventory Status']=='Dead Stock').sum():,}")
    c5.metric("Dead Stock Value",    fmt_m(pi[pi['Inventory Status']=='Dead Stock']['Stock Value PKR'].sum()))
    st.divider()
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Revenue (Filtered)",  fmt_m(sales_df['SALE'].sum()))
    c2.metric("ERP Profit",          fmt_m(sales_df['Profit'].sum()))
    c3.metric("Transactions",        f"{len(sales_df):,}")
    c4.metric("Unique Customers",    f"{sales_df['Account Name'].nunique():,}")
    st.divider()
    ca,cb = st.columns(2)
    with ca:
        st.subheader("Inventory Status")
        s = pi.groupby('Inventory Status').agg(Products=('Product No.','count'),Value=('Stock Value PKR','sum')).reset_index().sort_values('Products',ascending=False)
        s['Stock Value']=s['Value'].apply(fmt_m)
        st.dataframe(s[['Inventory Status','Products','Stock Value']], hide_index=True, use_container_width=True)
    with cb:
        st.subheader("Demand Pattern")
        p = pi.groupby('Demand Pattern').agg(Products=('Product No.','count'),Value=('Stock Value PKR','sum')).reset_index().sort_values('Products',ascending=False)
        p['Stock Value']=p['Value'].apply(fmt_m)
        st.dataframe(p[['Demand Pattern','Products','Stock Value']], hide_index=True, use_container_width=True)
    st.divider()
    st.subheader("Stock Health")
    h = pi.groupby('Stock Health').agg(Products=('Product No.','count'),Value=('Stock Value PKR','sum'),Sqm=('Current Stock Sqm','sum')).reset_index().sort_values('Value',ascending=False)
    h['Stock Value']=h['Value'].apply(fmt_m); h['Sqm']=h['Sqm'].apply(lambda x:f"{x:,.0f}")
    st.dataframe(h[['Stock Health','Products','Stock Value','Sqm']], hide_index=True, use_container_width=True)


# ─────────────────────────────────────────────
# PAGE 2 — SALES TRENDS
# ─────────────────────────────────────────────
elif page == "📈 Sales Trends":
    st.title("📈 Sales Trends")
    with st.expander("🔍 Filters", expanded=True):
        dff = global_filters(df, "st")
    sales_df   = dff[dff['Type']=='S'].copy()
    returns_df = dff[dff['Type']=='S.R'].copy()

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Gross Sale Value", fmt_m(sales_df['SALE'].sum()))
    c2.metric("Return Value",     fmt_m(returns_df['RETURN'].sum()))
    c3.metric("Net Sale Value",   fmt_m(sales_df['SALE'].sum()-returns_df['RETURN'].sum()))
    avg_bill = sales_df.groupby('Bill No.')['SALE'].sum().mean() if len(sales_df)>0 else 0
    c4.metric("Avg Bill Value",   f"Rs {avg_bill:,.0f}")
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Gross Sale Sqm",  f"{sales_df['Sq.m'].sum():,.1f}")
    c2.metric("Return Sqm",      f"{returns_df['Sq.m'].sum():,.1f}")
    c3.metric("Net Sale Sqm",    f"{sales_df['Sq.m'].sum()-returns_df['Sq.m'].sum():,.1f}")
    c4.metric("Total Bills",     f"{sales_df['Bill No.'].nunique():,}")
    st.divider()

    st.subheader("Monthly Trend")
    ms = sales_df.groupby('Month').agg(Sale_Val=('SALE','sum'),Sale_Sqm=('Sq.m','sum'),ERP_P=('Profit','sum'),Act_P=('Actual Profit','sum'),Bills=('Bill No.','nunique')).reset_index()
    mr = returns_df.groupby('Month').agg(Ret_Val=('RETURN','sum'),Ret_Sqm=('Sq.m','sum')).reset_index()
    monthly = ms.merge(mr, on='Month', how='left').fillna(0).sort_values('Month')
    monthly['Net Value'] = monthly['Sale_Val']-monthly['Ret_Val']
    monthly['Net Sqm']   = monthly['Sale_Sqm']-monthly['Ret_Sqm']
    monthly['ERP M%']    = (monthly['ERP_P']/monthly['Sale_Val']*100).round(1)
    monthly['Sale Value']= monthly['Sale_Val'].apply(fmt_m)
    monthly['Ret Value'] = monthly['Ret_Val'].apply(fmt_m)
    monthly['Net']       = monthly['Net Value'].apply(fmt_m)
    monthly['ERP Profit']= monthly['ERP_P'].apply(fmt_m)
    disp = ['Month','Sale Value','Sale_Sqm','Ret Value','Ret_Sqm','Net','Net Sqm','ERP Profit','ERP M%','Bills']
    if is_admin:
        monthly['Actual Profit']  = monthly['Act_P'].apply(fmt_m)
        monthly['Actual M%']      = (monthly['Act_P']/monthly['Sale_Val']*100).round(1)
        disp += ['Actual Profit','Actual M%']
    # Totals row
    tot = {c: '' for c in disp}
    tot['Month']      = '📊 TOTAL'
    tot['Sale Value'] = fmt_m(monthly['Sale_Val'].sum())
    tot['Sale_Sqm']   = round(monthly['Sale_Sqm'].sum(), 1)
    tot['Ret Value']  = fmt_m(monthly['Ret_Val'].sum())
    tot['Ret_Sqm']    = round(monthly['Ret_Sqm'].sum(), 1)
    tot['Net']        = fmt_m(monthly['Net Value'].sum())
    tot['Net Sqm']    = round(monthly['Net Sqm'].sum(), 1)
    tot['ERP Profit'] = fmt_m(monthly['ERP_P'].sum())
    tot['ERP M%']     = round(monthly['ERP_P'].sum()/monthly['Sale_Val'].sum()*100, 1) if monthly['Sale_Val'].sum()>0 else 0
    tot['Bills']      = monthly['Bills'].sum()
    if is_admin:
        tot['Actual Profit'] = fmt_m(monthly['Act_P'].sum())
        tot['Actual M%']     = round(monthly['Act_P'].sum()/monthly['Sale_Val'].sum()*100, 1) if monthly['Sale_Val'].sum()>0 else 0
    monthly_with_tot = pd.concat([monthly[disp], pd.DataFrame([tot])], ignore_index=True)
    st.dataframe(monthly_with_tot, hide_index=True, use_container_width=True)
    st.divider()

    st.subheader("All Products by Revenue")
    pr = sales_df.groupby('Product No.').agg(Sale_Val=('SALE','sum'),Sale_Sqm=('Sq.m','sum'),Ret_Val=('RETURN','sum'),ERP_P=('Profit','sum'),Act_P=('Actual Profit','sum'),Bills=('Bill No.','nunique')).reset_index().sort_values('Sale_Val',ascending=False)
    pr = pr.merge(prod[['Product No.','Brand Name','Category','Size']], on='Product No.', how='left')
    pr['Net Value']   = pr['Sale_Val']-pr['Ret_Val']
    pr['ERP M%']      = (pr['ERP_P']/pr['Sale_Val']*100).round(1)
    pr['Sale Value']  = pr['Sale_Val'].apply(fmt_m)
    pr['Ret Value']   = pr['Ret_Val'].apply(fmt_m)
    pr['Net']         = pr['Net Value'].apply(fmt_m)
    pr['ERP Profit']  = pr['ERP_P'].apply(fmt_m)
    disp2 = ['Product No.','Brand Name','Category','Size','Sale Value','Sale_Sqm','Ret Value','Net','Bills','ERP Profit','ERP M%']
    if is_admin:
        pr['Actual M%']    = (pr['Act_P']/pr['Sale_Val']*100).round(1)
        pr['Actual Profit']= pr['Act_P'].apply(fmt_m)
        disp2 += ['Actual Profit','Actual M%']
    st.dataframe(pr[disp2], hide_index=True, use_container_width=True)
    st.download_button("📥 Download", pr.to_csv(index=False), "product_sales.csv", "text/csv")
    st.divider()

    ca,cb = st.columns(2)
    with ca:
        st.subheader("By Category")
        cr = sales_df.groupby('Category').agg(Sale_Val=('SALE','sum'),Sale_Sqm=('Sq.m','sum'),ERP_P=('Profit','sum'),Act_P=('Actual Profit','sum')).reset_index().sort_values('Sale_Val',ascending=False)
        cr['ERP M%']   = (cr['ERP_P']/cr['Sale_Val']*100).round(1)
        cr['Sale Value']= cr['Sale_Val'].apply(fmt_m)
        cr['ERP Profit']= cr['ERP_P'].apply(fmt_m)
        d=['Category','Sale Value','Sale_Sqm','ERP Profit','ERP M%']
        if is_admin:
            cr['Act M%']=(cr['Act_P']/cr['Sale_Val']*100).round(1); cr['Act Profit']=cr['Act_P'].apply(fmt_m); d+=['Act Profit','Act M%']
        st.dataframe(cr[d], hide_index=True, use_container_width=True)
    with cb:
        st.subheader("By Brand")
        br2 = sales_df.groupby('Brand Name').agg(Sale_Val=('SALE','sum'),Sale_Sqm=('Sq.m','sum'),ERP_P=('Profit','sum'),Act_P=('Actual Profit','sum')).reset_index().sort_values('Sale_Val',ascending=False)
        br2['ERP M%']   = (br2['ERP_P']/br2['Sale_Val']*100).round(1)
        br2['Sale Value']= br2['Sale_Val'].apply(fmt_m)
        br2['ERP Profit']= br2['ERP_P'].apply(fmt_m)
        d=['Brand Name','Sale Value','Sale_Sqm','ERP Profit','ERP M%']
        if is_admin:
            br2['Act M%']=(br2['Act_P']/br2['Sale_Val']*100).round(1); br2['Act Profit']=br2['Act_P'].apply(fmt_m); d+=['Act Profit','Act M%']
        st.dataframe(br2[d], hide_index=True, use_container_width=True)
    st.divider()
    st.subheader("By Warehouse")
    wh2 = sales_df.groupby('Warehouse').agg(Sale_Val=('SALE','sum'),Sale_Sqm=('Sq.m','sum'),Bills=('Bill No.','nunique')).reset_index().sort_values('Sale_Val',ascending=False)
    wh2['Sale Value']=wh2['Sale_Val'].apply(fmt_m)
    st.dataframe(wh2[['Warehouse','Sale Value','Sale_Sqm','Bills']], hide_index=True, use_container_width=True)

# ─────────────────────────────────────────────
# PAGE 3 — DEAD STOCK
# ─────────────────────────────────────────────
elif page == "🔴 Dead Stock":
    st.title("🔴 Dead Stock Analysis")
    with st.expander("🔍 Filters", expanded=True):
        flt = pi_filters(pi, "ds")
    dead = flt[(flt['Inventory Status']=='Dead Stock')&(flt['Current Stock Sqm']>0)].copy().sort_values('Stock Value PKR',ascending=False)
    c1,c2,c3 = st.columns(3)
    c1.metric("Dead Stock Products",    f"{len(dead):,}")
    c2.metric("Total Dead Stock Value", fmt_m(dead['Stock Value PKR'].sum()))
    c3.metric("Total Dead Stock Sqm",   f"{dead['Current Stock Sqm'].sum():,.0f}")
    st.divider()
    min_v = st.number_input("Min Stock Value (Rs)", value=0, step=10000)
    dead  = dead[dead['Stock Value PKR']>=min_v]
    dead['Suggested Discount %'] = dead['Days Since Last Sale'].apply(lambda x: 10 if x<=450 else (20 if x<=540 else (30 if x<=630 else 40)))
    dead['Liquidation Price']    = (dead['WAC Rate']*(1-dead['Suggested Discount %']/100)).round(0)
    cols = ['Product No.','Brand Name','Category','Size','Current Stock Sqm','WAC Rate','Stock Value PKR','Days Since Last Sale','Suggested Discount %','Liquidation Price']
    st.caption(f"Showing {len(dead):,} products — {fmt_m(dead['Stock Value PKR'].sum())}")
    st.dataframe(dead[cols], hide_index=True, use_container_width=True)
    st.download_button("📥 Download", dead[cols].to_csv(index=False), "dead_stock.csv", "text/csv")


elif page == "✅ Fast Movers":
    st.title("✅ Fast Movers")
    with st.expander("🔍 Filters", expanded=True):
        flt = pi_filters(pi, "fm")
    fast = flt[flt['Demand Pattern'].isin(['Stable Fast Mover','Volatile Fast Mover'])].copy().sort_values('Sales Velocity/Month',ascending=False)
    c1,c2,c3 = st.columns(3)
    c1.metric("Fast Moving Products", f"{len(fast):,}")
    c2.metric("Total Sales Velocity", f"{fast['Sales Velocity/Month'].sum():,.0f} sqm/month")
    c3.metric("Reorder Alerts",       f"{(fast['Stock Health']=='Reorder Now').sum():,}")
    st.divider()
    reorder = fast[fast['Stock Health']=='Reorder Now']
    if len(reorder)>0:
        st.subheader(f"🚨 Reorder Now — {len(reorder)} Products")
        st.dataframe(reorder[['Product No.','Brand Name','Category','Size','Current Stock Sqm','Sales Velocity/Month','Months of Stock','Demand Pattern']], hide_index=True, use_container_width=True)
        st.divider()
    st.subheader("All Fast Movers")
    st.dataframe(fast[['Product No.','Brand Name','Category','Size','Current Stock Sqm','Stock Value PKR','Sales Velocity/Month','Months of Stock','Demand Pattern','Stock Health','Reorder Score']], hide_index=True, use_container_width=True)


elif page == "📦 Product Intelligence":
    st.title("📦 Product Intelligence")
    with st.expander("🔍 Filters", expanded=True):
        flt = pi_filters(pi, "pi")
        c1,c2 = st.columns(2)
        with c1:
            pat_f = st.selectbox("Demand Pattern", ['All']+sorted(pi['Demand Pattern'].dropna().unique().tolist()), key="pi_pat")
            if pat_f!='All': flt=flt[flt['Demand Pattern']==pat_f]
        with c2:
            inv_f = st.selectbox("Inventory Status", ['All']+sorted(pi['Inventory Status'].dropna().unique().tolist()), key="pi_inv")
            if inv_f!='All': flt=flt[flt['Inventory Status']==inv_f]
    if not is_admin: flt=flt.drop(columns=['Actual Profit','Actual Margin %'],errors='ignore')
    st.caption(f"Showing {len(flt):,} products — {fmt_m(flt['Stock Value PKR'].sum())}")
    st.dataframe(flt, hide_index=True, use_container_width=True)
    st.download_button("📥 Download", flt.to_csv(index=False), "product_intelligence.csv", "text/csv")


elif page == "🏭 Brand & Company":
    st.title("🏭 Brand & Company Analysis")
    with st.expander("🔍 Filters", expanded=False):
        dff = global_filters(df, "bc", show_salesman=False)
    sales_df = dff[dff['Type']=='S'].copy()
    tab1,tab2 = st.tabs(["By Brand","By Company"])
    with tab1:
        bs = pi.groupby('Brand Name').agg(Products=('Product No.','count'),Stock_Value=('Stock Value PKR','sum'),Avg_Vel=('Sales Velocity/Month','mean'),Dead=('Inventory Status',lambda x:(x=='Dead Stock').sum()),Fast=('Demand Pattern',lambda x:x.isin(['Stable Fast Mover','Volatile Fast Mover']).sum()),Rev=('Total Revenue','sum'),ERP_P=('ERP Profit','sum'),Act_P=('Actual Profit','sum')).reset_index().sort_values('Stock_Value',ascending=False)
        bs['Dead %']    = (bs['Dead']/bs['Products']*100).round(1)
        bs['Stock Value']= bs['Stock_Value'].apply(fmt_m)
        bs['Revenue']   = bs['Rev'].apply(fmt_m)
        bs['ERP M%']    = (bs['ERP_P']/bs['Rev']*100).round(1)
        bs['Avg Vel']   = bs['Avg_Vel'].round(2)
        d=['Brand Name','Products','Stock Value','Revenue','ERP M%','Fast','Dead','Dead %','Avg Vel']
        if is_admin: bs['Act M%']=(bs['Act_P']/bs['Rev']*100).round(1); bs['Act Profit']=bs['Act_P'].apply(fmt_m); d+=['Act Profit','Act M%']
        st.dataframe(bs[d], hide_index=True, use_container_width=True)
        st.download_button("📥 Download", bs.to_csv(index=False), "brand.csv", "text/csv")
    with tab2:
        cs2 = sales_df.groupby('Company Name').agg(Revenue=('SALE','sum'),ERP_P=('Profit','sum'),Act_P=('Actual Profit','sum'),Sqm=('Sq.m','sum'),Bills=('Bill No.','nunique'),Customers=('Account Name','nunique')).reset_index().sort_values('Revenue',ascending=False)
        cs2['ERP M%']=(cs2['ERP_P']/cs2['Revenue']*100).round(1)
        cs2['Revenue']=cs2['Revenue'].apply(fmt_m); cs2['ERP Profit']=cs2['ERP_P'].apply(fmt_m)
        d=['Company Name','Revenue','ERP Profit','ERP M%','Sqm','Bills','Customers']
        if is_admin: cs2['Act M%']=(cs2['Act_P']/cs2['ERP_P']*cs2['ERP M%']).round(1); d+=['Act M%']
        st.dataframe(cs2[d], hide_index=True, use_container_width=True)


elif page == "👤 Customer Intelligence":
    st.title("👤 Customer Intelligence")
    with st.expander("🔍 Filters", expanded=True):
        dff = global_filters(df, "ci", show_salesman=True)
    sales_all = df[df['Type']=='S'].copy()
    sales_df  = dff[dff['Type']=='S'].copy()
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Total Customers",      f"{sales_df['Account Name'].nunique():,}")
    c2.metric("Total Revenue",        fmt_m(sales_df['SALE'].sum()))
    avg_rev = sales_df.groupby('Account Name')['SALE'].sum().mean() if len(sales_df)>0 else 0
    c3.metric("Avg Revenue/Customer", f"Rs {avg_rev:,.0f}")
    c4.metric("Total Bills",          f"{sales_df['Bill No.'].nunique():,}")
    st.divider()
    tab1,tab2,tab3,tab4 = st.tabs(["🆕 New Customers","🔄 Returning","⭐ Top Customers","📊 Full List"])
    with tab1:
        st.subheader("New Customers in Date Range")
        first_tx = sales_all.groupby('Account Name')['Date'].min().reset_index()
        first_tx.columns=['Account Name','First Transaction Date']
        s_d = dff['Date'].min().date() if len(dff)>0 else df['Date'].min().date()
        e_d = dff['Date'].max().date() if len(dff)>0 else df['Date'].max().date()
        new = first_tx[(first_tx['First Transaction Date'].dt.date>=s_d)&(first_tx['First Transaction Date'].dt.date<=e_d)].copy()
        nr  = sales_df[sales_df['Account Name'].isin(new['Account Name'])].groupby('Account Name').agg(Revenue=('SALE','sum'),Bills=('Bill No.','nunique'),Products=('Product No.','nunique')).reset_index()
        new = new.merge(nr, on='Account Name', how='left').fillna(0)
        new['Revenue']=new['Revenue'].apply(fmt_m)
        new = new.sort_values('First Transaction Date', ascending=False)
        c1,c2,c3=st.columns(3)
        c1.metric("New Customers",f"{len(new):,}"); c2.metric("Avg Bills",f"{new['Bills'].mean():.1f}" if len(new)>0 else "0"); c3.metric("Unique Products",f"{new['Products'].sum():,.0f}")
        st.dataframe(new[['Account Name','First Transaction Date','Revenue','Bills','Products']], hide_index=True, use_container_width=True)
        st.download_button("📥 Download", new.to_csv(index=False), "new_customers.csv", "text/csv")
    with tab2:
        st.subheader("Customer Return Frequency")
        cf = sales_all.groupby('Account Name').agg(Bills=('Bill No.','nunique'),Revenue=('SALE','sum'),First=('Date','min'),Last=('Date','max')).reset_index()
        cf['Days Active']    = (cf['Last']-cf['First']).dt.days
        cf['Avg Gap (days)'] = (cf['Days Active']/cf['Bills']).round(1)
        cf['Days Since']     = (pd.Timestamp.today()-cf['Last']).dt.days
        cf['Last Visit']     = cf['Last'].dt.date
        cf['Revenue']        = cf['Revenue'].apply(fmt_m)
        cf['Visit Freq']     = cf['Avg Gap (days)'].apply(lambda x: '🔥 <7d' if x<7 else ('✅ 7-30d' if x<30 else ('🟡 30-90d' if x<90 else '🔵 >90d')))
        cf['Churn Risk']     = cf['Days Since'].apply(lambda x: '🔴 High' if x>180 else ('🟡 Med' if x>90 else '🟢 Low'))
        c1,c2 = st.columns(2)
        with c1: vf=st.selectbox("Visit Frequency",['All']+sorted(cf['Visit Freq'].unique().tolist()),key="ci_vf")
        with c2: cr2=st.selectbox("Churn Risk",['All']+sorted(cf['Churn Risk'].unique().tolist()),key="ci_cr")
        f2=cf.copy()
        if vf!='All': f2=f2[f2['Visit Freq']==vf]
        if cr2!='All': f2=f2[f2['Churn Risk']==cr2]
        st.dataframe(f2[['Account Name','Revenue','Bills','Avg Gap (days)','Last Visit','Days Since','Visit Freq','Churn Risk']].sort_values('Days Since'), hide_index=True, use_container_width=True)
        st.download_button("📥 Download", f2.to_csv(index=False), "returning.csv", "text/csv")
    with tab3:
        st.subheader("Top Customers — ABC Analysis")
        top = sales_df.groupby('Account Name').agg(Rev=('SALE','sum'),ERP_P=('Profit','sum'),Act_P=('Actual Profit','sum'),Sqm=('Sq.m','sum'),Bills=('Bill No.','nunique'),Prods=('Product No.','nunique'),Last=('Date','max')).reset_index().sort_values('Rev',ascending=False)
        top['Avg Bill']   = (top['Rev']/top['Bills']).round(0)
        top['ERP M%']     = (top['ERP_P']/top['Rev']*100).round(1)
        top['Revenue']    = top['Rev'].apply(fmt_m)
        top['ERP Profit'] = top['ERP_P'].apply(fmt_m)
        top['Last Purchase']= top['Last'].dt.date
        top['Days Since'] = (pd.Timestamp.today()-top['Last']).dt.days
        top['Cum %']      = (top['Rev'].cumsum()/top['Rev'].sum()*100)
        top['ABC']        = top['Cum %'].apply(lambda x: 'A' if x<=80 else ('B' if x<=95 else 'C'))
        c1,c2,c3=st.columns(3)
        c1.metric("Class A",f"{(top['ABC']=='A').sum():,}"); c2.metric("Class B",f"{(top['ABC']=='B').sum():,}"); c3.metric("Class C",f"{(top['ABC']=='C').sum():,}")
        abc_f=st.selectbox("ABC Class",['All','A','B','C'],key="ci_abc")
        if abc_f!='All': top=top[top['ABC']==abc_f]
        d=['Account Name','ABC','Revenue','ERP Profit','ERP M%','Bills','Prods','Avg Bill','Days Since']
        if is_admin: top['Act M%']=(top['Act_P']/top['Rev']*100).round(1); top['Act Profit']=top['Act_P'].apply(fmt_m); d+=['Act Profit','Act M%']
        st.dataframe(top[d], hide_index=True, use_container_width=True)
        st.download_button("📥 Download", top.to_csv(index=False), "top_customers.csv", "text/csv")
    with tab4:
        st.subheader("Full Customer List")
        full = sales_all.groupby('Account Name').agg(Rev=('SALE','sum'),ERP_P=('Profit','sum'),Sqm=('Sq.m','sum'),Bills=('Bill No.','nunique'),Prods=('Product No.','nunique'),First=('Date','min'),Last=('Date','max')).reset_index().sort_values('Rev',ascending=False)
        full['Avg Bill']  = (full['Rev']/full['Bills']).round(0)
        full['ERP M%']    = (full['ERP_P']/full['Rev']*100).round(1)
        full['Revenue']   = full['Rev'].apply(fmt_m)
        full['First Visit']= full['First'].dt.date
        full['Last Visit'] = full['Last'].dt.date
        full['Days Since'] = (pd.Timestamp.today()-full['Last']).dt.days
        full['Days Active']= (full['Last']-full['First']).dt.days
        full['Avg Gap']    = (full['Days Active']/full['Bills']).round(1)
        full['Cum %']      = (full['Rev'].cumsum()/full['Rev'].sum()*100)
        full['ABC']        = full['Cum %'].apply(lambda x:'A' if x<=80 else ('B' if x<=95 else 'C'))
        st.dataframe(full[['Account Name','ABC','Revenue','ERP M%','Bills','Prods','Avg Bill','First Visit','Last Visit','Days Since','Avg Gap']], hide_index=True, use_container_width=True)
        st.download_button("📥 Download", full.to_csv(index=False), "all_customers.csv", "text/csv")


elif page == "💰 Margin Analysis":
    if st.session_state['role'] not in ['admin','manager']: st.error("Access denied."); st.stop()
    st.title("💰 Margin Analysis")
    with st.expander("🔍 Filters", expanded=True):
        dff = global_filters(df, "ma")
    sales_df = dff[dff['Type']=='S'].copy()
    tr=sales_df['SALE'].sum(); ep=sales_df['Profit'].sum(); ap=sales_df['Actual Profit'].sum()
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Total Revenue",fmt_m(tr)); c2.metric("ERP Profit",fmt_m(ep))
    c3.metric("ERP Margin %",f"{ep/tr*100:.1f}%" if tr>0 else "N/A")
    c4.metric("Avg Rate/Sqm",f"Rs {sales_df['Rate'].mean():,.0f}" if len(sales_df)>0 else "N/A")
    if is_admin:
        c1,c2,c3=st.columns(3)
        c1.metric("Actual Profit",fmt_m(ap)); c2.metric("Actual Margin %",f"{ap/tr*100:.1f}%" if tr>0 else "N/A"); c3.metric("Hidden Profit",fmt_m(ap-ep))
    st.divider()
    tab1,tab2,tab3=st.tabs(["By Category","By Brand","By Product"])
    def mtbl(col):
        t=sales_df.groupby(col).agg(Rev=('SALE','sum'),ERP_P=('Profit','sum'),Act_P=('Actual Profit','sum'),Sqm=('Sq.m','sum')).reset_index()
        t['ERP M%']=(t['ERP_P']/t['Rev']*100).round(1); t['Revenue']=t['Rev'].apply(fmt_m); t['ERP Profit']=t['ERP_P'].apply(fmt_m)
        d=[col,'Revenue','Sqm','ERP Profit','ERP M%']
        if is_admin: t['Act M%']=(t['Act_P']/t['Rev']*100).round(1); t['Act Profit']=t['Act_P'].apply(fmt_m); d+=['Act Profit','Act M%']
        return t[d].sort_values('ERP M%',ascending=False)
    with tab1: st.dataframe(mtbl('Category'), hide_index=True, use_container_width=True)
    with tab2: st.dataframe(mtbl('Brand Name'), hide_index=True, use_container_width=True)
    with tab3:
        t=sales_df.groupby('Product No.').agg(Rev=('SALE','sum'),ERP_P=('Profit','sum'),Act_P=('Actual Profit','sum'),Sqm=('Sq.m','sum')).reset_index()
        t['ERP M%']=(t['ERP_P']/t['Rev']*100).round(1); t=t.sort_values('ERP_P',ascending=False)
        t['Revenue']=t['Rev'].apply(fmt_k); t['ERP Profit']=t['ERP_P'].apply(fmt_k)
        d=['Product No.','Revenue','Sqm','ERP Profit','ERP M%']
        if is_admin: t['Act M%']=(t['Act_P']/t['Rev']*100).round(1); t['Act Profit']=t['Act_P'].apply(fmt_k); d+=['Act Profit','Act M%']
        st.dataframe(t[d].head(200), hide_index=True, use_container_width=True)


elif page == "🧑‍💼 Salesman Performance":
    if st.session_state['role'] not in ['admin','manager']: st.error("Access denied."); st.stop()
    st.title("🧑‍💼 Salesman Performance")
    with st.expander("🔍 Filters", expanded=False):
        dff = global_filters(df, "sp")
    sales_df = dff[dff['Type']=='S'].copy()
    returns_df = dff[dff['Type']=='S.R'].copy()
    sal = sales_df.groupby('Salesman').agg(Revenue=('SALE','sum'),ERP_P=('Profit','sum'),Act_P=('Actual Profit','sum'),Sqm=('Sq.m','sum'),Bills=('Bill No.','nunique'),Customers=('Account Name','nunique'),Products_Sold=('Product No.','nunique')).reset_index()
    ret_sal = returns_df.groupby('Salesman').agg(Ret_Val=('RETURN','sum'),Ret_Sqm=('Sq.m','sum')).reset_index()
    sal = sal.merge(ret_sal, on='Salesman', how='left').fillna(0)
    sal['Net Revenue']  = sal['Revenue']-sal['Ret_Val']
    sal['Return Rate %']= (sal['Ret_Val']/sal['Revenue']*100).round(1)
    sal['ERP M%']       = (sal['ERP_P']/sal['Revenue']*100).round(1)
    sal['Avg Bill']     = (sal['Revenue']/sal['Bills']).round(0)
    sal['Revenue (Rs)'] = sal['Revenue'].apply(fmt_m)
    sal['Net Rev (Rs)'] = sal['Net Revenue'].apply(fmt_m)
    sal['ERP Profit']   = sal['ERP_P'].apply(fmt_m)
    sal = sal.sort_values('Revenue', ascending=False)
    c1,c2,c3=st.columns(3)
    c1.metric("Total Salesmen",f"{len(sal):,}"); c2.metric("Top Performer",sal.iloc[0]['Salesman'] if len(sal)>0 else "N/A"); c3.metric("Top Revenue",sal.iloc[0]['Revenue (Rs)'] if len(sal)>0 else "N/A")
    st.divider()
    d=['Salesman','Revenue (Rs)','Net Rev (Rs)','Return Rate %','ERP Profit','ERP M%','Bills','Customers','Products_Sold','Avg Bill']
    if is_admin: sal['Act M%']=(sal['Act_P']/sal['Revenue']*100).round(1); sal['Act Profit']=sal['Act_P'].apply(fmt_m); d+=['Act Profit','Act M%']
    st.dataframe(sal[d], hide_index=True, use_container_width=True)
    # Totals row for salesman table
    sal_tot = {c:'' for c in d}
    sal_tot['Salesman']       = '📊 TOTAL'
    sal_tot['Revenue (Rs)']   = fmt_m(sal['Revenue'].sum())
    sal_tot['Net Rev (Rs)']   = fmt_m(sal['Net Revenue'].sum())
    sal_tot['Return Rate %']  = round(sal['Ret_Val'].sum()/sal['Revenue'].sum()*100, 1) if sal['Revenue'].sum()>0 else 0
    sal_tot['ERP Profit']     = fmt_m(sal['ERP_P'].sum())
    sal_tot['ERP M%']         = round(sal['ERP_P'].sum()/sal['Revenue'].sum()*100, 1) if sal['Revenue'].sum()>0 else 0
    sal_tot['Bills']          = sal['Bills'].sum()
    sal_tot['Customers']      = sales_df['Account Name'].nunique()
    sal_tot['Products_Sold']  = sales_df['Product No.'].nunique()
    sal_tot['Avg Bill']       = round(sal['Revenue'].sum()/sal['Bills'].sum(), 0) if sal['Bills'].sum()>0 else 0
    if is_admin:
        sal_tot['Act M%']    = round(sal['Act_P'].sum()/sal['Revenue'].sum()*100, 1) if sal['Revenue'].sum()>0 else 0
        sal_tot['Act Profit']= fmt_m(sal['Act_P'].sum())
    sal_with_tot = pd.concat([sal[d], pd.DataFrame([sal_tot])], ignore_index=True)
    st.dataframe(sal_with_tot, hide_index=True, use_container_width=True)
    st.divider()
    st.subheader("Monthly Salesman Trend")
    sm=sales_df.groupby(['Month','Salesman']).agg(Revenue=('SALE','sum')).reset_index().sort_values(['Month','Revenue'],ascending=[True,False])
    sm['Revenue']=sm['Revenue'].apply(fmt_k)
    st.dataframe(sm, hide_index=True, use_container_width=True)

elif page == "🎯 Incentive Calculator":
    if not is_admin: st.error("Admin only."); st.stop()
    st.title("🎯 Salesman Incentive Calculator")
    SALESMAN_CONFIG = {
        'FIDA':    {'salary':125000,'exp':20,'tier':'Senior',  'base_target':20000000,'commission':0.005,'bonus_target':30000000,'bonus':50000,'return_threshold':5.0,'return_penalty':0.001},
        'SAQIB':   {'salary':125000,'exp':20,'tier':'Senior',  'base_target':20000000,'commission':0.005,'bonus_target':30000000,'bonus':50000,'return_threshold':5.0,'return_penalty':0.001},
        'ASHAR':   {'salary':45000, 'exp':15,'tier':'Mid',     'base_target':8000000, 'commission':0.0075,'bonus_target':15000000,'bonus':30000,'return_threshold':5.0,'return_penalty':0.001},
        'JAVED':   {'salary':45000, 'exp':15,'tier':'Mid',     'base_target':8000000, 'commission':0.0075,'bonus_target':15000000,'bonus':30000,'return_threshold':5.0,'return_penalty':0.001},
        'ZEESHAN': {'salary':45000, 'exp':7, 'tier':'Junior',  'base_target':5000000, 'commission':0.01,  'bonus_target':10000000,'bonus':20000,'return_threshold':6.0,'return_penalty':0.002},
        'AFTAB':   {'salary':45000, 'exp':7, 'tier':'Junior',  'base_target':5000000, 'commission':0.01,  'bonus_target':10000000,'bonus':20000,'return_threshold':6.0,'return_penalty':0.002},
        'HAMMAD':  {'salary':45000, 'exp':7, 'tier':'Junior',  'base_target':5000000, 'commission':0.01,  'bonus_target':10000000,'bonus':20000,'return_threshold':6.0,'return_penalty':0.002},
        'KHURRAM': {'salary':45000, 'exp':7, 'tier':'Junior',  'base_target':5000000, 'commission':0.01,  'bonus_target':10000000,'bonus':20000,'return_threshold':6.0,'return_penalty':0.002},
    }
    st.info("📌 You can adjust all metrics below. Changes are live and don't affect saved config.")
    with st.expander("🔍 Date Filter", expanded=False):
        dff = global_filters(df, "ic", show_salesman=False, show_inventory=False)
    sales_df   = dff[dff['Type']=='S'].copy()
    returns_df = dff[dff['Type']=='S.R'].copy()
    sal_perf = sales_df.groupby('Salesman').agg(Revenue=('SALE','sum')).reset_index()
    ret_perf = returns_df.groupby('Salesman').agg(Ret_Val=('RETURN','sum')).reset_index()
    sal_perf = sal_perf.merge(ret_perf, on='Salesman', how='left').fillna(0)
    sal_perf['Net Revenue']  = sal_perf['Revenue'] - sal_perf['Ret_Val']
    sal_perf['Return Rate %']= (sal_perf['Ret_Val']/sal_perf['Revenue']*100).round(1)
    st.divider()
    results = []
    for sal_name, cfg in SALESMAN_CONFIG.items():
        row = sal_perf[sal_perf['Salesman']==sal_name]
        if len(row)==0: continue
        r = row.iloc[0]
        with st.expander(f"⚙️ {sal_name} — {cfg['tier']} | Salary: Rs {cfg['salary']:,}", expanded=False):
            c1,c2,c3 = st.columns(3)
            with c1:
                base_target = st.number_input(f"Base Target (Rs)", value=cfg['base_target'], step=500000, key=f"{sal_name}_bt")
                commission  = st.number_input(f"Commission %", value=cfg['commission']*100, step=0.1, format="%.2f", key=f"{sal_name}_cm") / 100
            with c2:
                bonus_target = st.number_input(f"Bonus Target (Rs)", value=cfg['bonus_target'], step=500000, key=f"{sal_name}_bnt")
                bonus_amt    = st.number_input(f"Bonus Amount (Rs)", value=cfg['bonus'], step=5000, key=f"{sal_name}_ba")
            with c3:
                ret_threshold= st.number_input(f"Return Rate Threshold %", value=cfg['return_threshold'], step=0.5, key=f"{sal_name}_rt")
                ret_penalty  = st.number_input(f"Return Penalty % per 1% excess", value=cfg['return_penalty']*100, step=0.05, format="%.3f", key=f"{sal_name}_rp") / 100
            dead_bonus = st.number_input(f"Dead Stock Commission %", value=1.5, step=0.1, format="%.1f", key=f"{sal_name}_db") / 100
        net_rev      = r['Net Revenue']
        return_rate  = r['Return Rate %']
        commission_earned = max(0, net_rev - base_target) * commission
        bonus_earned      = bonus_amt if net_rev >= bonus_target else 0
        excess_return     = max(0, return_rate - ret_threshold)
        return_deduction  = net_rev * ret_penalty * excess_return
        total_incentive   = commission_earned + bonus_earned - return_deduction
        total_payout      = cfg['salary'] + max(0, total_incentive)
        results.append({'Salesman':sal_name,'Tier':cfg['tier'],'Base Salary':cfg['salary'],
            'Net Revenue':round(net_rev),'Base Target':base_target,'Target Hit':'✅' if net_rev>=base_target else '❌',
            'Commission':round(commission_earned),'Bonus Target Hit':'✅' if net_rev>=bonus_target else '❌',
            'Bonus':round(bonus_earned),'Return Rate %':return_rate,'Return Deduction':round(return_deduction),
            'Total Incentive':round(max(0,total_incentive)),'Total Payout':round(total_payout),
            'Cost to Revenue %':round(total_payout/net_rev*100,2) if net_rev>0 else 0})
    if results:
        res_df = pd.DataFrame(results)
        res_df['Net Revenue']      = res_df['Net Revenue'].apply(fmt_m)
        res_df['Commission']       = res_df['Commission'].apply(lambda x: f"Rs {x:,}")
        res_df['Bonus']            = res_df['Bonus'].apply(lambda x: f"Rs {x:,}")
        res_df['Return Deduction'] = res_df['Return Deduction'].apply(lambda x: f"Rs {x:,}")
        res_df['Total Incentive']  = res_df['Total Incentive'].apply(lambda x: f"Rs {x:,}")
        res_df['Total Payout']     = res_df['Total Payout'].apply(lambda x: f"Rs {x:,}")
        st.subheader("📊 Incentive Summary")
        st.dataframe(res_df, hide_index=True, use_container_width=True)
        st.info("💡 ASHAR is generating Rs 12.7M/month at Rs 45,000 salary — recommend immediate raise to Rs 75,000-80,000")
        st.download_button("📥 Download", res_df.to_csv(index=False), "incentives.csv", "text/csv")


elif page == "🏹 Dead Stock Targets":
    if not is_admin: st.error("Admin only."); st.stop()
    st.title("🏹 Dead Stock Salesman Targets")
    with st.expander("🔍 Filters", expanded=True):
        flt = pi_filters(pi, "dst")
    dead = flt[(flt['Inventory Status']=='Dead Stock')&(flt['Current Stock Sqm']>0)].copy()
    dead['Suggested Discount %'] = dead['Days Since Last Sale'].apply(lambda x: 10 if x<=450 else (20 if x<=540 else (30 if x<=630 else 40)))
    dead['Liquidation Price']    = (dead['WAC Rate']*(1-dead['Suggested Discount %']/100)).round(0)
    dead['Potential Revenue']    = (dead['Current Stock Sqm']*dead['Liquidation Price']).round(0)
    st.subheader("Dead Stock Overview by Brand")
    brand_dead = dead.groupby('Brand Name').agg(Products=('Product No.','count'),Stock_Value=('Stock Value PKR','sum'),Potential_Rev=('Potential Revenue','sum')).reset_index().sort_values('Stock_Value',ascending=False)
    brand_dead['Stock Value']    = brand_dead['Stock_Value'].apply(fmt_m)
    brand_dead['Potential Rev']  = brand_dead['Potential_Rev'].apply(fmt_m)
    ASSIGNMENTS = {
        'OREAL CERAMICS':['FIDA','SAQIB'],'MONTAGE CERAMICS (TIME)':['ASHAR','KHURRAM'],
        'MAGNET':['ZEESHAN','AFTAB'],'GHANI':['JAVED','HAMMAD'],
        'CHINA':['FIDA','SAQIB','ASHAR','JAVED','ZEESHAN','AFTAB','HAMMAD','KHURRAM'],
        'ORIENT':['ZEESHAN','AFTAB'],'GREAT WALL':['JAVED','HAMMAD'],'KEMPINS':['ASHAR','KHURRAM'],
    }
    brand_dead['Assigned To'] = brand_dead['Brand Name'].map(lambda x: ', '.join(ASSIGNMENTS.get(x,['All'])))
    st.dataframe(brand_dead[['Brand Name','Products','Stock Value','Potential Rev','Assigned To']], hide_index=True, use_container_width=True)
    st.divider()
    sal_sel = st.selectbox("Show dead stock assigned to:", ['All']+['FIDA','SAQIB','ASHAR','JAVED','ZEESHAN','AFTAB','HAMMAD','KHURRAM'])
    dead_display = dead.copy()
    if sal_sel != 'All':
        assigned_brands = [b for b,sals in ASSIGNMENTS.items() if sal_sel in sals or sals==['All']]
        dead_display = dead_display[dead_display['Brand Name'].isin(assigned_brands)]
    st.caption(f"Showing {len(dead_display):,} products — {fmt_m(dead_display['Stock Value PKR'].sum())} stock value")
    cols = ['Product No.','Brand Name','Category','Size','Current Stock Sqm','WAC Rate','Stock Value PKR','Days Since Last Sale','Suggested Discount %','Liquidation Price','Potential Revenue']
    st.dataframe(dead_display[cols], hide_index=True, use_container_width=True)
    st.download_button("📥 Download", dead_display[cols].to_csv(index=False), "dead_stock_targets.csv", "text/csv")


elif page == "🛒 Product Pairs":
    st.title("🛒 Frequently Bought Together")
    tab1, tab2 = st.tabs(["📦 Product SKU Pairs","📐 Size Pairs"])
    with tab1:
        st.subheader("Product SKU Pairs")
        c1,c2,c3 = st.columns(3)
        with c1: min_co = st.number_input("Min Co-occurrence", value=10, step=5, key="pp_min")
        with c2: sz_filter = st.selectbox("Filter by Size", ['All']+sorted(prod['Size'].dropna().unique().tolist()), key="pp_sz")
        with c3: br_filter = st.selectbox("Filter by Brand", ['All']+sorted(prod['Brand Name'].dropna().unique().tolist()), key="pp_br")
        pairs_show = pairs_df[pairs_df['Co-occurrence']>=min_co].copy()
        if sz_filter!='All': pairs_show = pairs_show[(pairs_show['Size A']==sz_filter)|(pairs_show['Size B']==sz_filter)]
        if br_filter!='All':
            br_prods = prod[prod['Brand Name']==br_filter]['Product No.'].tolist()
            pairs_show = pairs_show[(pairs_show['Product A'].isin(br_prods))|(pairs_show['Product B'].isin(br_prods))]
        br_map = prod.set_index('Product No.')['Brand Name'].to_dict()
        pairs_show['Brand A'] = pairs_show['Product A'].map(br_map)
        pairs_show['Brand B'] = pairs_show['Product B'].map(br_map)
        st.caption(f"Showing {len(pairs_show):,} pairs")
        st.dataframe(pairs_show[['Product A','Size A','Brand A','Product B','Size B','Brand B','Co-occurrence']], hide_index=True, use_container_width=True)
        st.download_button("📥 Download", pairs_show.to_csv(index=False), "product_pairs.csv", "text/csv")
    with tab2:
        st.subheader("Size Pairs")
        min_co2 = st.number_input("Min Co-occurrence", value=50, step=25, key="sp_min")
        sp_show = size_pairs_df[size_pairs_df['Co-occurrence']>=min_co2].copy()
        st.dataframe(sp_show, hide_index=True, use_container_width=True)
        st.subheader("💡 Top Size Combinations")
        for _, row in size_pairs_df.head(10).iterrows():
            st.write(f"**{row['Size A']} + {row['Size B']}** — bought together {row['Co-occurrence']:,} times")


elif page == "📊 ABC-XYZ Analysis":
    st.title("📊 ABC-XYZ Inventory Classification")
    with st.expander("🔍 Filters", expanded=True):
        flt = pi_filters(pi, "axyz")
    st.subheader("Classification Matrix")
    matrix_data = []
    for abc in ['A','B','C']:
        row = {'ABC': abc}
        for xyz in ['X','Y','Z']:
            code = abc+xyz
            count = len(flt[flt['ABC_XYZ']==code])
            value = flt[flt['ABC_XYZ']==code]['Stock Value PKR'].sum()
            row[xyz] = f"{count} products\n{fmt_m(value)}"
        matrix_data.append(row)
    matrix_df = pd.DataFrame(matrix_data).set_index('ABC')
    st.dataframe(matrix_df, use_container_width=True)
    st.divider()
    st.markdown("""
    | Class | Stock Strategy | Reorder Strategy |
    |-------|---------------|-----------------|
    | **AX** | Never stockout — keep 3 months | Auto reorder at 1 month |
    | **AY** | Keep 2 months stock | Reorder at 6 weeks |
    | **AZ** | Keep 1 month + safety stock | Order on demand |
    | **BX** | Keep 2 months | Reorder at 6 weeks |
    | **BY** | Keep 1.5 months | Reorder at 1 month |
    | **BZ** | Keep minimal | Order on demand |
    | **CZ** | **Liquidate or discontinue** | Do not reorder |
    """)
    st.divider()
    c1,c2 = st.columns(2)
    with c1: abc_sel = st.selectbox("Filter ABC", ['All','A','B','C'], key="axyz_abc")
    with c2: xyz_sel = st.selectbox("Filter XYZ", ['All','X','Y','Z'], key="axyz_xyz")
    flt2 = flt.copy()
    if abc_sel!='All': flt2=flt2[flt2['ABC']==abc_sel]
    if xyz_sel!='All': flt2=flt2[flt2['XYZ']==xyz_sel]
    flt2 = flt2.sort_values('Total Revenue', ascending=False)
    disp_cols = ['Product No.','Brand Name','Category','Size','ABC_XYZ','ABC','XYZ','Consistency %','Total Revenue','Stock Value PKR','Current Stock Sqm','Sales Velocity/Month','Reorder Score','Inventory Status']
    st.dataframe(flt2[disp_cols], hide_index=True, use_container_width=True)
    st.download_button("📥 Download", flt2[disp_cols].to_csv(index=False), "abc_xyz.csv", "text/csv")


elif page == "📉 Sell Through":
    st.title("📉 Sell Through Rate Analysis")
    with st.expander("🔍 Filters", expanded=True):
        flt = pi_filters(pi, "str")
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Avg Sell Through",    f"{flt['Sell Through %'].mean():.1f}%")
    c2.metric("Products >80%",       f"{(flt['Sell Through %']>80).sum():,}")
    c3.metric("Products 20-80%",     f"{((flt['Sell Through %']>=20)&(flt['Sell Through %']<=80)).sum():,}")
    c4.metric("Products <20%",       f"{(flt['Sell Through %']<20).sum():,}")
    st.divider()
    c1,c2 = st.columns(2)
    with c1: min_st = st.slider("Min Sell Through %", 0, 100, 0, key="str_min")
    with c2: max_st = st.slider("Max Sell Through %", 0, 200, 200, key="str_max")
    flt2 = flt[(flt['Sell Through %']>=min_st)&(flt['Sell Through %']<=max_st)].copy().sort_values('Sell Through %')
    flt2['ST Category'] = flt2['Sell Through %'].apply(
        lambda x: '🔴 <20%' if x<20 else ('🟡 20-50%' if x<50 else ('🟢 50-80%' if x<80 else ('✅ >80%' if x<=100 else '⚠️ >100%'))))
    disp = ['Product No.','Brand Name','Category','Size','Sell Through %','ST Category','Current Stock Sqm','Stock Value PKR','Net Sales Sqm','Sales Velocity/Month']
    st.dataframe(flt2[disp], hide_index=True, use_container_width=True)
    st.download_button("📥 Download", flt2[disp].to_csv(index=False), "sell_through.csv", "text/csv")
    st.divider()
    st.subheader("Sell Through by Brand")
    br_st = flt.groupby('Brand Name').agg(Products=('Product No.','count'),Avg_ST=('Sell Through %','mean'),Low=('Sell Through %',lambda x:(x<20).sum()),High=('Sell Through %',lambda x:(x>80).sum()),Val=('Stock Value PKR','sum')).reset_index().sort_values('Avg_ST',ascending=False)
    br_st['Avg ST %']=br_st['Avg_ST'].round(1); br_st['Stock Value']=br_st['Val'].apply(fmt_m)
    st.dataframe(br_st[['Brand Name','Products','Avg ST %','High','Low','Stock Value']], hide_index=True, use_container_width=True)


elif page == "🔮 Demand Forecast":
    st.title("🔮 Demand Forecast (30/60/90 Days)")
    with st.expander("🔍 Filters", expanded=True):
        flt = pi_filters(pi, "df")
    fast = flt[flt['Demand Pattern'].isin(['Stable Fast Mover','Volatile Fast Mover','Slow Stable'])].copy()
    fast = fast[fast['Sales Velocity/Month']>0]
    fast['Forecast 30 Days']    = (fast['Sales Velocity/Month']*1).round(2)
    fast['Forecast 60 Days']    = (fast['Sales Velocity/Month']*2).round(2)
    fast['Forecast 90 Days']    = (fast['Sales Velocity/Month']*3).round(2)
    fast['Stock Covers (Days)'] = (fast['Current Stock Sqm']/(fast['Sales Velocity/Month']/30)).round(0)
    fast['Stockout Risk']       = fast['Stock Covers (Days)'].apply(lambda x:'🔴 High' if x<=30 else ('🟡 Medium' if x<=60 else '🟢 Low'))
    risk_f = st.selectbox("Stockout Risk", ['All','🔴 High','🟡 Medium','🟢 Low'], key="df_risk")
    if risk_f!='All': fast=fast[fast['Stockout Risk']==risk_f]
    fast = fast.sort_values('Stock Covers (Days)')
    disp=['Product No.','Brand Name','Category','Size','Current Stock Sqm','Sales Velocity/Month','Forecast 30 Days','Forecast 60 Days','Forecast 90 Days','Stock Covers (Days)','Stockout Risk']
    st.dataframe(fast[disp], hide_index=True, use_container_width=True)
    st.download_button("📥 Download", fast[disp].to_csv(index=False), "forecast.csv", "text/csv")


elif page == "⚠️ Reorder Alerts":
    st.title("⚠️ Reorder Alerts")
    with st.expander("🔍 Filters", expanded=True):
        flt = pi_filters(pi, "ra")
    reorder = flt[(flt['Stock Health']=='Reorder Now')&(flt['Current Stock Sqm']>0)&(flt['Sales Velocity/Month']>0)].copy().sort_values('Sales Velocity/Month',ascending=False)
    reorder['Suggested Reorder Sqm']   = (reorder['Sales Velocity/Month']*3-reorder['Current Stock Sqm']).clip(lower=0).round(2)
    reorder['Suggested Reorder Boxes'] = (reorder['Suggested Reorder Sqm']/reorder['Sq.m/Box']).apply(lambda x: max(1,round(x)) if pd.notna(x) else 0)
    reorder['Reorder Value (Rs)']      = (reorder['Suggested Reorder Sqm']*reorder['WAC Rate']).round(0)
    c1,c2,c3=st.columns(3)
    c1.metric("Products Needing Reorder",f"{len(reorder):,}")
    c2.metric("Total Reorder Qty",       f"{reorder['Suggested Reorder Sqm'].sum():,.0f} sqm")
    c3.metric("Estimated Reorder Value", fmt_m(reorder['Reorder Value (Rs)'].sum()))
    st.divider()
    cols=['Product No.','Brand Name','Category','Size','Current Stock Sqm','Months of Stock','Sales Velocity/Month','Reorder Score','Suggested Reorder Sqm','Suggested Reorder Boxes','Reorder Value (Rs)']
    st.dataframe(reorder[cols], hide_index=True, use_container_width=True)
    st.download_button("📥 Download", reorder[cols].to_csv(index=False), "reorder_alerts.csv", "text/csv")


elif page == "📦 Stock Comparison":
    st.title("📦 Stock Level Comparison")
    with st.expander("🔍 Period Selection & Filters", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Current Period**")
            curr_end   = st.date_input("End Date",   value=df['Date'].max().date(), key="sc_ce")
            curr_start = st.date_input("Start Date", value=(df['Date'].max()-pd.Timedelta(days=30)).date(), key="sc_cs")
        with c2:
            st.markdown("**Previous Period**")
            prev_end   = st.date_input("End Date",   value=(df['Date'].max()-pd.Timedelta(days=30)).date(), key="sc_pe")
            prev_start = st.date_input("Start Date", value=(df['Date'].max()-pd.Timedelta(days=60)).date(), key="sc_ps")
        c1,c2,c3,c4 = st.columns(4)
        with c1: br_f  = st.selectbox("Brand",    ['All']+sorted(df['Brand Name'].dropna().unique().tolist()),   key="sc_br")
        with c2: co_f  = st.selectbox("Company",  ['All']+sorted(df['Company Name'].dropna().unique().tolist()), key="sc_co")
        with c3: cat_f = st.selectbox("Category", ['All']+sorted(df['Category'].dropna().unique().tolist()),     key="sc_cat")
        with c4: sz_f  = st.selectbox("Size",     ['All']+sorted(prod['Size'].dropna().unique().tolist()),       key="sc_sz")

    @st.cache_data(ttl=3600)
    def stock_snapshot(_df, as_of):
        snap = _df[_df['Date']<=pd.Timestamp(as_of)].sort_values('Date').groupby('Product No.').last()[['Closing','WAC Rate']].reset_index()
        snap.columns = ['Product No.','Stock Sqm','WAC Rate']
        snap['Stock Value'] = snap['Stock Sqm'] * snap['WAC Rate']
        return snap

    with st.spinner("Calculating..."):
        curr_snap = stock_snapshot(df, curr_end)
        prev_snap = stock_snapshot(df, prev_end)
    curr_snap.columns = ['Product No.','Curr Sqm','Curr WAC','Curr Value']
    prev_snap.columns = ['Product No.','Prev Sqm','Prev WAC','Prev Value']
    comp = curr_snap.merge(prev_snap, on='Product No.', how='outer').fillna(0)
    comp = comp.merge(prod[['Product No.','Brand Name','Category','Size','Company Name']], on='Product No.', how='left')
    comp['Sqm Change']   = comp['Curr Sqm']   - comp['Prev Sqm']
    comp['Value Change'] = comp['Curr Value'] - comp['Prev Value']
    comp['Sqm Change %'] = (comp['Sqm Change'] / comp['Prev Sqm'].replace(0, np.nan) * 100).round(1)
    comp['Direction']    = comp['Sqm Change'].apply(lambda x: '🔺 Up' if x>0 else ('🔻 Down' if x<0 else '➡️ Same'))
    flt = comp.copy()
    if br_f  != 'All': flt = flt[flt['Brand Name']   == br_f]
    if co_f  != 'All': flt = flt[flt['Company Name'] == co_f]
    if cat_f != 'All': flt = flt[flt['Category']     == cat_f]
    if sz_f  != 'All': flt = flt[flt['Size']         == sz_f]
    st.divider()
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Current Stock Sqm",  f"{flt['Curr Sqm'].sum():,.0f}", delta=f"{flt['Sqm Change'].sum():+,.0f} sqm")
    c2.metric("Current Stock Value", fmt_m(flt['Curr Value'].sum()), delta=fmt_m(flt['Value Change'].sum()))
    c3.metric("Products Increased",  f"{(flt['Sqm Change']>0).sum():,}")
    c4.metric("Products Decreased",  f"{(flt['Sqm Change']<0).sum():,}")
    st.divider()
    tab1, tab2, tab3 = st.tabs(["🏭 By Brand","📂 By Category","📦 By Product"])
    def make_comp_table(group_col, df_in):
        t = df_in.groupby(group_col).agg(Curr_Sqm=('Curr Sqm','sum'),Prev_Sqm=('Prev Sqm','sum'),Curr_Value=('Curr Value','sum'),Prev_Value=('Prev Value','sum')).reset_index()
        t['Sqm Δ']     = t['Curr_Sqm']-t['Prev_Sqm']
        t['Value Δ']   = t['Curr_Value']-t['Prev_Value']
        t['Change %']  = (t['Sqm Δ']/t['Prev_Sqm'].replace(0,np.nan)*100).round(1)
        t['Dir']       = t['Sqm Δ'].apply(lambda x:'🔺' if x>0 else ('🔻' if x<0 else '➡️'))
        t['Curr Sqm']  = t['Curr_Sqm'].apply(lambda x:f"{x:,.0f}")
        t['Prev Sqm']  = t['Prev_Sqm'].apply(lambda x:f"{x:,.0f}")
        t['Curr Value']= t['Curr_Value'].apply(fmt_m)
        t['Prev Value']= t['Prev_Value'].apply(fmt_m)
        t['Sqm Change']= t['Sqm Δ'].apply(lambda x:f"+{x:,.0f}" if x>0 else f"{x:,.0f}")
        t['Val Change']= t['Value Δ'].apply(lambda x:("+"+fmt_m(x)) if x>0 else fmt_m(x))
        cols = ['Dir',group_col,'Prev Sqm','Curr Sqm','Sqm Change','Change %','Prev Value','Curr Value','Val Change']
        return t.sort_values('Value Δ')[cols]
    with tab1: st.dataframe(make_comp_table('Brand Name', flt), hide_index=True, use_container_width=True)
    with tab2: st.dataframe(make_comp_table('Category', flt), hide_index=True, use_container_width=True)
    with tab3:
        dir_f = st.selectbox("Filter Direction", ['All','🔺 Up','🔻 Down','➡️ Same'], key="sc_dir")
        flt2  = flt.copy()
        if dir_f != 'All': flt2 = flt2[flt2['Direction']==dir_f]
        flt2 = flt2.sort_values('Value Change')
        flt2['Curr Sqm']   = flt2['Curr Sqm'].apply(lambda x:f"{x:,.2f}")
        flt2['Prev Sqm']   = flt2['Prev Sqm'].apply(lambda x:f"{x:,.2f}")
        flt2['Curr Value'] = flt2['Curr Value'].apply(fmt_m)
        flt2['Prev Value'] = flt2['Prev Value'].apply(fmt_m)
        flt2['Sqm Δ']      = flt2['Sqm Change'].apply(lambda x:f"+{x:,.2f}" if x>0 else f"{x:,.2f}")
        flt2['Val Δ']      = flt2['Value Change'].apply(lambda x:("+"+fmt_m(x)) if x>0 else fmt_m(x))
        flt2['Change %']   = flt2['Sqm Change %'].apply(lambda x:f"+{x}%" if pd.notna(x) and x>0 else f"{x}%")
        st.dataframe(flt2[['Direction','Product No.','Brand Name','Category','Size','Prev Sqm','Curr Sqm','Sqm Δ','Change %','Prev Value','Curr Value','Val Δ']], hide_index=True, use_container_width=True)
        st.download_button("📥 Download", flt2.to_csv(index=False), "stock_comparison.csv", "text/csv")


elif page == "🔍 Search":
    st.title("🔍 Universal Search")
    query = st.text_input("Search — product, customer, brand, category, size, salesman...", placeholder="e.g. MONTAGE POLISH, IDREES BROTHER, 60 X 120...")
    if query and len(query) >= 2:
        q = query.upper()
        tab1, tab2, tab3 = st.tabs(["📦 Products","👤 Customers","📋 Transactions"])
        with tab1:
            res = pi[pi['Product No.'].str.upper().str.contains(q,na=False)|pi['Brand Name'].str.upper().str.contains(q,na=False)|pi['Category'].str.upper().str.contains(q,na=False)|pi['Size'].str.upper().str.contains(q,na=False)|pi['Company Name'].str.upper().str.contains(q,na=False)].copy()
            st.caption(f"{len(res)} products found")
            if len(res)>0:
                disp=['Product No.','Brand Name','Category','Size','Current Stock Sqm','Stock Value PKR','Reorder Score','Sales Velocity/Month','Inventory Status','Stock Health']
                st.dataframe(res[disp], hide_index=True, use_container_width=True)
                st.download_button("📥 Download", res[disp].to_csv(index=False), "search_products.csv")
        with tab2:
            sales_all2 = df[df['Type']=='S'].copy()
            cr = sales_all2[sales_all2['Account Name'].str.upper().str.contains(q,na=False)].groupby('Account Name').agg(Revenue=('SALE','sum'),Bills=('Bill No.','nunique'),Products=('Product No.','nunique'),Last=('Date','max')).reset_index()
            cr['Revenue']      = cr['Revenue'].apply(fmt_m)
            cr['Last Purchase']= cr['Last'].dt.date
            cr['Days Since']   = (pd.Timestamp.today()-cr['Last']).dt.days
            st.caption(f"{len(cr)} customers found")
            if len(cr)>0:
                st.dataframe(cr[['Account Name','Revenue','Bills','Products','Last Purchase','Days Since']], hide_index=True, use_container_width=True)
        with tab3:
            tx = df[df['Product No.'].str.upper().str.contains(q,na=False)|df['Account Name'].str.upper().str.contains(q,na=False)|df['Salesman'].str.upper().str.contains(q,na=False)].copy().sort_values('Date',ascending=False).head(500)
            st.caption(f"{len(tx)} transactions found (max 500)")
            if len(tx)>0:
                tx['Date2'] = tx['Date'].dt.strftime('%d-%m-%Y %H:%M')
                st.dataframe(tx[['Date2','Type','Product No.','Account Name','Salesman','Sq.m','Rate','SALE','RETURN','Warehouse']], hide_index=True, use_container_width=True)
    else:
        st.info("Type at least 2 characters to search")


elif page == "📊 Period Comparison":
    st.title("📊 Period Comparison")
    st.caption("Compare any two date ranges side by side")
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("**📅 Period A**")
        pa_s = st.date_input("Start", value=(df['Date'].max()-pd.Timedelta(days=60)).date(), key="pa_s")
        pa_e = st.date_input("End",   value=(df['Date'].max()-pd.Timedelta(days=31)).date(), key="pa_e")
        pa_l = st.text_input("Label", value="Period A", key="pa_l")
    with c2:
        st.markdown("**📅 Period B**")
        pb_s = st.date_input("Start", value=(df['Date'].max()-pd.Timedelta(days=30)).date(), key="pb_s")
        pb_e = st.date_input("End",   value=df['Date'].max().date(), key="pb_e")
        pb_l = st.text_input("Label", value="Period B", key="pb_l")
    with st.expander("🔍 Filters", expanded=False):
        c1,c2,c3,c4 = st.columns(4)
        with c1: br_f  = st.selectbox("Brand",    ['All']+sorted(df['Brand Name'].dropna().unique().tolist()),   key="pc_br")
        with c2: co_f  = st.selectbox("Company",  ['All']+sorted(df['Company Name'].dropna().unique().tolist()), key="pc_co")
        with c3: cat_f = st.selectbox("Category", ['All']+sorted(df['Category'].dropna().unique().tolist()),     key="pc_cat")
        with c4: sz_f  = st.selectbox("Size",     ['All']+sorted(prod['Size'].dropna().unique().tolist()),       key="pc_sz")
    def apply_flt(dff):
        if br_f !='All': dff=dff[dff['Brand Name']  ==br_f]
        if co_f !='All': dff=dff[dff['Company Name']==co_f]
        if cat_f!='All': dff=dff[dff['Category']    ==cat_f]
        if sz_f !='All': dff=dff[dff['Size']        ==sz_f]
        return dff
    dfa = apply_flt(df[(df['Date'].dt.date>=pa_s)&(df['Date'].dt.date<=pa_e)])
    dfb = apply_flt(df[(df['Date'].dt.date>=pb_s)&(df['Date'].dt.date<=pb_e)])
    sa  = dfa[dfa['Type']=='S'].copy(); sb = dfb[dfb['Type']=='S'].copy()
    ra  = dfa[dfa['Type']=='S.R'].copy(); rb = dfb[dfb['Type']=='S.R'].copy()
    st.divider()
    st.subheader("📊 Key Metrics Comparison")
    def chg(a,b): return f"{((b-a)/a*100):+.1f}%" if a!=0 else "N/A"
    def dir_(a,b): return "🔺" if b>a else ("🔻" if b<a else "➡️")
    metrics = [
        ("Gross Revenue",    sa['SALE'].sum(),          sb['SALE'].sum(),          True),
        ("Sales Returns",    ra['RETURN'].sum(),         rb['RETURN'].sum(),         True),
        ("Net Revenue",      sa['SALE'].sum()-ra['RETURN'].sum(), sb['SALE'].sum()-rb['RETURN'].sum(), True),
        ("ERP Gross Profit", sa['Profit'].sum(),         sb['Profit'].sum(),         True),
        ("Sqm Sold",         sa['Sq.m'].sum(),           sb['Sq.m'].sum(),           False),
        ("Unique Customers", sa['Account Name'].nunique(),sb['Account Name'].nunique(),False),
        ("Total Bills",      sa['Bill No.'].nunique(),   sb['Bill No.'].nunique(),   False),
        ("Avg Bill Value",   sa['SALE'].sum()/max(sa['Bill No.'].nunique(),1), sb['SALE'].sum()/max(sb['Bill No.'].nunique(),1), True),
    ]
    if is_admin:
        metrics.append(("Actual Gross Profit", sa['Actual Profit'].sum(), sb['Actual Profit'].sum(), True))
    rows = []
    for name,va,vb,is_money in metrics:
        fmt = fmt_m if is_money else lambda x:f"{x:,.0f}"
        rows.append({"Metric":name, pa_l:fmt(va), pb_l:fmt(vb),
            "Change":("+"+fmt_m(vb-va)) if (vb-va)>0 and is_money else (fmt_m(vb-va) if is_money else f"{vb-va:+,.0f}"),
            "Change %":chg(va,vb), "Dir":dir_(va,vb)})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.divider()
    def pc_table(col):
        a = sa.groupby(col).agg(Rev_A=('SALE','sum'),Sqm_A=('Sq.m','sum')).reset_index()
        b = sb.groupby(col).agg(Rev_B=('SALE','sum'),Sqm_B=('Sq.m','sum')).reset_index()
        t = a.merge(b, on=col, how='outer').fillna(0)
        t['Rev Δ']  = t['Rev_B']-t['Rev_A']
        t['Rev Δ%'] = (t['Rev Δ']/t['Rev_A'].replace(0,np.nan)*100).round(1)
        t['Dir']    = t['Rev Δ'].apply(lambda x:'🔺' if x>0 else ('🔻' if x<0 else '➡️'))
        t[f'{pa_l} Rev'] = t['Rev_A'].apply(fmt_m)
        t[f'{pb_l} Rev'] = t['Rev_B'].apply(fmt_m)
        t['Change'] = t['Rev Δ'].apply(lambda x:("+"+fmt_m(x)) if x>0 else fmt_m(x))
        return t[['Dir',col,f'{pa_l} Rev',f'{pb_l} Rev','Change','Rev Δ%','Sqm_A','Sqm_B']].sort_values('Rev Δ',ascending=False)
    tab1,tab2,tab3,tab4,tab5 = st.tabs(["🏭 Brand","📂 Category","👤 Customer","📦 Product","📐 Size"])
    with tab1: st.dataframe(pc_table('Brand Name'),   hide_index=True, use_container_width=True)
    with tab2: st.dataframe(pc_table('Category'),     hide_index=True, use_container_width=True)
    with tab3: st.dataframe(pc_table('Account Name'), hide_index=True, use_container_width=True)
    with tab4: st.dataframe(pc_table('Product No.'),  hide_index=True, use_container_width=True)
    with tab5: st.dataframe(pc_table('Size'),         hide_index=True, use_container_width=True)


elif page == "📦 Closing Stock":
    st.title("📦 Closing Stock Report")
    with st.expander("🔍 Filters", expanded=True):
        c1,c2 = st.columns(2)
        with c1:
            min_d = df['Date'].min().date(); max_d = df['Date'].max().date()
            cs_date = st.date_input("📅 As of Date", value=max_d, min_value=min_d, max_value=max_d, key="csr_date")
        with c2:
            st.markdown(" ")
            st.markdown(" ")
            st.caption(f"Showing closing stock as of **{cs_date}**")

        @st.cache_data(ttl=3600)
        def closing_stock_snap(_df, _prod, as_of):
            snap = _df[_df['Date']<=pd.Timestamp(as_of)].sort_values('Date').groupby('Product No.').last()[['Closing']].reset_index()
            snap.columns = ['Product No.','Current Stock Sqm']
            purch2 = _df[(_df['Date']<=pd.Timestamp(as_of))&(_df['Type'].isin(['P','O.S']))].copy()
            wac2   = purch2.groupby('Product No.').apply(lambda x: (x['Sq.m']*x['Rate']).sum()/x['Sq.m'].sum() if x['Sq.m'].sum()>0 else 0).reset_index()
            wac2.columns = ['Product No.','WAC Rate']
            snap = snap.merge(wac2, on='Product No.', how='left').fillna(0)
            snap['Stock Value PKR'] = snap['Current Stock Sqm'] * snap['WAC Rate']
            snap = snap.merge(_prod[['Product No.','Brand Name','Category','Size','Company Name']], on='Product No.', how='left')
            return snap

        snap_flt = closing_stock_snap(df, prod, cs_date)

        c1,c2,c3,c4 = st.columns(4)
        with c1: br_f  = st.selectbox("Brand",    ['All']+sorted(snap_flt['Brand Name'].dropna().unique().tolist()),   key="csr_br")
        with c2: co_f  = st.selectbox("Company",  ['All']+sorted(snap_flt['Company Name'].dropna().unique().tolist()), key="csr_co")
        with c3: cat_f = st.selectbox("Category", ['All']+sorted(snap_flt['Category'].dropna().unique().tolist()),     key="csr_cat")
        with c4: sz_f  = st.selectbox("Size",     ['All']+sorted(prod['Size'].dropna().unique().tolist()),             key="csr_sz")

    flt2 = snap_flt[snap_flt['Current Stock Sqm']>0].copy().sort_values('Stock Value PKR',ascending=False)
    if br_f  != 'All': flt2 = flt2[flt2['Brand Name']   == br_f]
    if co_f  != 'All': flt2 = flt2[flt2['Company Name'] == co_f]
    if cat_f != 'All': flt2 = flt2[flt2['Category']     == cat_f]
    if sz_f  != 'All': flt2 = flt2[flt2['Size']         == sz_f]
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Products in Stock",  f"{len(flt2):,}")
    c2.metric("Total Stock Sqm",    f"{flt2['Current Stock Sqm'].sum():,.0f}")
    c3.metric("Total Stock Value",  fmt_m(flt2['Stock Value PKR'].sum()))
    c4.metric("Avg WAC Rate",       f"Rs {flt2['WAC Rate'].mean():,.0f}")
    st.divider()
    tab1,tab2,tab3,tab4 = st.tabs(["📦 By Product","🏭 By Brand","📂 By Category","📐 By Size"])
    with tab1:
        disp=['Product No.','Brand Name','Category','Size','Current Stock Sqm','WAC Rate','Stock Value PKR','Inventory Status','Stock Health','Days Since Last Sale']
        st.dataframe(flt2[disp], hide_index=True, use_container_width=True)
        st.download_button("📥 Download", flt2[disp].to_csv(index=False), "closing_stock.csv")
    with tab2:
        bs = flt2.groupby('Brand Name').agg(Products=('Product No.','count'),Sqm=('Current Stock Sqm','sum'),Val=('Stock Value PKR','sum'),WAC=('WAC Rate','mean')).reset_index().sort_values('Val',ascending=False)
        bs['Stock Value']=bs['Val'].apply(fmt_m); bs['% of Total']=(bs['Val']/flt2['Stock Value PKR'].sum()*100).round(1); bs['Avg WAC']=bs['WAC'].round(0)
        st.dataframe(bs[['Brand Name','Products','Sqm','Stock Value','Avg WAC','% of Total']], hide_index=True, use_container_width=True)
    with tab3:
        cs = flt2.groupby('Category').agg(Products=('Product No.','count'),Sqm=('Current Stock Sqm','sum'),Val=('Stock Value PKR','sum')).reset_index().sort_values('Val',ascending=False)
        cs['Stock Value']=cs['Val'].apply(fmt_m); cs['% of Total']=(cs['Val']/flt2['Stock Value PKR'].sum()*100).round(1)
        st.dataframe(cs[['Category','Products','Sqm','Stock Value','% of Total']], hide_index=True, use_container_width=True)
    with tab4:
        ss = flt2.groupby('Size').agg(Products=('Product No.','count'),Sqm=('Current Stock Sqm','sum'),Val=('Stock Value PKR','sum')).reset_index().sort_values('Val',ascending=False)
        ss['Stock Value']=ss['Val'].apply(fmt_m); ss['% of Total']=(ss['Val']/flt2['Stock Value PKR'].sum()*100).round(1)
        st.dataframe(ss[['Size','Products','Sqm','Stock Value','% of Total']], hide_index=True, use_container_width=True)


elif page == "📋 Income Statement":
    if st.session_state['role'] not in ['admin','manager']: st.error("Access denied."); st.stop()
    st.title("📋 Income Statement")
    with st.expander("📅 Select Period", expanded=True):
        c1,c2 = st.columns(2)
        with c1: is_s = st.date_input("From", value=df['Date'].min().date(), key="is_s")
        with c2: is_e = st.date_input("To",   value=df['Date'].max().date(), key="is_e")
    dff2  = df[(df['Date'].dt.date>=is_s)&(df['Date'].dt.date<=is_e)]
    sal2  = dff2[dff2['Type']=='S'].copy()
    ret2  = dff2[dff2['Type']=='S.R'].copy()
    pur2  = dff2[dff2['Type'].isin(['P','O.S'])].copy()
    retp2 = dff2[dff2['Type']=='P.R'].copy()
    gross_rev = sal2['SALE'].sum()
    sales_ret = ret2['RETURN'].sum()
    net_rev   = gross_rev - sales_ret
    cogs      = (pur2['Sq.m']*pur2['Rate']).sum() - (retp2['Sq.m']*retp2['Rate']).sum()
    erp_gp    = sal2['Profit'].sum()
    actual_gp = sal2['Actual Profit'].sum()
    st.divider()
    st.subheader("📊 Trading Account")
    trading_rows = [
        {"Item":"Gross Sales Revenue",      "Amount (Rs)":fmt_m(gross_rev)},
        {"Item":"Less: Sales Returns",      "Amount (Rs)":f"({fmt_m(sales_ret)})"},
        {"Item":"Net Sales Revenue",        "Amount (Rs)":fmt_m(net_rev)},
        {"Item":"─────────────────",        "Amount (Rs)":""},
        {"Item":"Cost of Goods Purchased",  "Amount (Rs)":fmt_m(cogs)},
        {"Item":"ERP Gross Profit",         "Amount (Rs)":fmt_m(erp_gp)},
        {"Item":"ERP Gross Margin %",       "Amount (Rs)":f"{erp_gp/gross_rev*100:.1f}%" if gross_rev>0 else "N/A"},
    ]
    if is_admin:
        trading_rows += [
            {"Item":"Actual Gross Profit",  "Amount (Rs)":fmt_m(actual_gp)},
            {"Item":"Actual Gross Margin %","Amount (Rs)":f"{actual_gp/gross_rev*100:.1f}%" if gross_rev>0 else "N/A"},
            {"Item":"Hidden Profit",        "Amount (Rs)":fmt_m(actual_gp-erp_gp)},
        ]
    st.dataframe(pd.DataFrame(trading_rows), hide_index=True, use_container_width=True)
    st.divider()
    st.subheader("📊 Operating Expenses")
    st.caption("Enter your actual monthly expenses — these are not saved, re-enter each session")
    total_expenses = 0
    for category, items in EXPENSES_TEMPLATE.items():
        with st.expander(f"💼 {category}", expanded=False):
            cols = st.columns(min(len(items),3))
            for i,(item,default) in enumerate(items.items()):
                with cols[i%3]:
                    val = st.number_input(item, value=default, step=1000, key=f"exp_{category}_{item}")
                    total_expenses += val
    st.divider()
    st.subheader("📊 Net Profit Summary")
    net_erp    = erp_gp    - total_expenses
    net_actual = actual_gp - total_expenses
    pnl_rows = [
        {"Item":"ERP Gross Profit",       "Amount (Rs)":fmt_m(erp_gp)},
        {"Item":"Less: Total Expenses",   "Amount (Rs)":f"({fmt_m(total_expenses)})"},
        {"Item":"ERP Net Profit",         "Amount (Rs)":fmt_m(net_erp)},
        {"Item":"ERP Net Margin %",       "Amount (Rs)":f"{net_erp/gross_rev*100:.1f}%" if gross_rev>0 else "N/A"},
    ]
    if is_admin:
        pnl_rows += [
            {"Item":"Actual Net Profit",  "Amount (Rs)":fmt_m(net_actual)},
            {"Item":"Actual Net Margin %","Amount (Rs)":f"{net_actual/gross_rev*100:.1f}%" if gross_rev>0 else "N/A"},
        ]
    st.dataframe(pd.DataFrame(pnl_rows), hide_index=True, use_container_width=True)
    st.divider()
    st.subheader("📈 Monthly Trend")
    mt = sal2.groupby('Month').agg(Revenue=('SALE','sum'),ERP_GP=('Profit','sum'),Act_GP=('Actual Profit','sum'),Sqm=('Sq.m','sum'),Bills=('Bill No.','nunique')).reset_index()
    mt_r = ret2.groupby('Month').agg(Returns=('RETURN','sum')).reset_index()
    mt = mt.merge(mt_r, on='Month', how='left').fillna(0).sort_values('Month')
    mt['Net Rev']  = mt['Revenue']-mt['Returns']
    mt['ERP M%']   = (mt['ERP_GP']/mt['Revenue']*100).round(1)
    mt['Revenue']  = mt['Revenue'].apply(fmt_m)
    mt['Returns']  = mt['Returns'].apply(fmt_m)
    mt['Net Rev']  = mt['Net Rev'].apply(fmt_m)
    mt['ERP GP']   = mt['ERP_GP'].apply(fmt_m)
    disp = ['Month','Revenue','Returns','Net Rev','ERP GP','ERP M%','Sqm','Bills']
    if is_admin:
        mt['Act M%'] = (mt['Act_GP']/mt['ERP_GP']*mt['ERP M%']).round(1)
        mt['Act GP'] = mt['Act_GP'].apply(fmt_m)
        disp += ['Act GP','Act M%']
    st.dataframe(mt[disp], hide_index=True, use_container_width=True)
    st.download_button("📥 Download", mt.to_csv(index=False), "income_statement.csv")


elif page == "🏦 Assets Position":
    if not is_admin: st.error("Admin only."); st.stop()
    st.title("🏦 Assets & Liabilities Position")
    inv_value = pi[pi['Current Stock Sqm']>0]['Stock Value PKR'].sum()
    st.info(f"📦 Inventory Value (auto from stock data): **{fmt_m(inv_value)}**")
    st.subheader("Current Assets")
    c1,c2,c3 = st.columns(3)
    with c1: cash_hand   = st.number_input("Cash in Hand (Rs)",          value=0, step=10000, key="ca_ch")
    with c2: cash_bank   = st.number_input("Cash at Bank (Rs)",          value=0, step=10000, key="ca_cb")
    with c3: receivables = st.number_input("Trade Receivables (Rs)",     value=0, step=10000, key="ca_tr")
    c1,c2 = st.columns(2)
    with c1: advances  = st.number_input("Advances to Suppliers (Rs)", value=0, step=10000, key="ca_ad")
    with c2: other_ca  = st.number_input("Other Current Assets (Rs)",  value=0, step=10000, key="ca_ot")
    total_ca = cash_hand + cash_bank + receivables + advances + other_ca + inv_value
    st.subheader("Fixed Assets")
    c1,c2,c3,c4 = st.columns(4)
    with c1: furniture = st.number_input("Furniture & Fixtures (Rs)", value=0, step=10000, key="fa_ff")
    with c2: vehicles  = st.number_input("Vehicles (Rs)",             value=0, step=10000, key="fa_vh")
    with c3: equipment = st.number_input("Equipment (Rs)",            value=0, step=10000, key="fa_eq")
    with c4: building  = st.number_input("Building/Leasehold (Rs)",   value=0, step=10000, key="fa_bl")
    total_fa = furniture + vehicles + equipment + building
    st.subheader("Liabilities")
    c1,c2,c3,c4 = st.columns(4)
    with c1: payables = st.number_input("Trade Payables (Rs)",    value=0, step=10000, key="li_tp")
    with c2: st_loans = st.number_input("Short Term Loans (Rs)",  value=0, step=10000, key="li_sl")
    with c3: lt_loans = st.number_input("Long Term Loans (Rs)",   value=0, step=10000, key="li_ll")
    with c4: other_li = st.number_input("Other Liabilities (Rs)", value=0, step=10000, key="li_ot")
    total_liab = payables + st_loans + lt_loans + other_li
    total_assets = total_ca + total_fa
    net_worth    = total_assets - total_liab
    st.divider()
    c1,c2,c3 = st.columns(3)
    c1.metric("Total Assets",      fmt_m(total_assets))
    c2.metric("Total Liabilities", fmt_m(total_liab))
    c3.metric("Net Worth",         fmt_m(net_worth))
    st.subheader("📊 Balance Sheet")
    bs_rows = [
        {"Item":"═══ CURRENT ASSETS ═══",     "Amount":""},
        {"Item":"Cash in Hand",               "Amount":fmt_m(cash_hand)},
        {"Item":"Cash at Bank",               "Amount":fmt_m(cash_bank)},
        {"Item":"Trade Receivables",          "Amount":fmt_m(receivables)},
        {"Item":"Advances to Suppliers",      "Amount":fmt_m(advances)},
        {"Item":"Inventory (Auto from data)", "Amount":fmt_m(inv_value)},
        {"Item":"Other Current Assets",       "Amount":fmt_m(other_ca)},
        {"Item":"TOTAL CURRENT ASSETS",       "Amount":fmt_m(total_ca)},
        {"Item":"","Amount":""},
        {"Item":"═══ FIXED ASSETS ═══",       "Amount":""},
        {"Item":"Furniture & Fixtures",       "Amount":fmt_m(furniture)},
        {"Item":"Vehicles",                   "Amount":fmt_m(vehicles)},
        {"Item":"Equipment",                  "Amount":fmt_m(equipment)},
        {"Item":"Building/Leasehold",         "Amount":fmt_m(building)},
        {"Item":"TOTAL FIXED ASSETS",         "Amount":fmt_m(total_fa)},
        {"Item":"","Amount":""},
        {"Item":"TOTAL ASSETS",               "Amount":fmt_m(total_assets)},
        {"Item":"","Amount":""},
        {"Item":"═══ LIABILITIES ═══",        "Amount":""},
        {"Item":"Trade Payables",             "Amount":fmt_m(payables)},
        {"Item":"Short Term Loans",           "Amount":fmt_m(st_loans)},
        {"Item":"Long Term Loans",            "Amount":fmt_m(lt_loans)},
        {"Item":"Other Liabilities",          "Amount":fmt_m(other_li)},
        {"Item":"TOTAL LIABILITIES",          "Amount":fmt_m(total_liab)},
        {"Item":"","Amount":""},
        {"Item":"NET WORTH",                  "Amount":fmt_m(net_worth)},
    ]
    st.dataframe(pd.DataFrame(bs_rows), hide_index=True, use_container_width=True)
    st.download_button("📥 Download", pd.DataFrame(bs_rows).to_csv(index=False), "balance_sheet.csv")


# ─────────────────────────────────────────────
# PAGE — SALESMAN RATE ANALYSIS
# ─────────────────────────────────────────────
elif page == "📊 Salesman Rate Analysis":
    if st.session_state['role'] not in ['admin','manager']: st.error("Access denied."); st.stop()
    st.title("📊 Salesman Rate Analysis")
    st.caption("Compare which salesman sells each product at highest/lowest rate — reveals negotiation performance")

    with st.expander("🔍 Filters", expanded=True):
        dff = global_filters(df, "sra")

    sales_df = dff[dff['Type']=='S'].copy()

    # WAC lookup
    purch = df[df['Type'].isin(['P','O.S'])].copy()
    wac = purch.groupby('Product No.').apply(
        lambda x: (x['Sq.m']*x['Rate']).sum()/x['Sq.m'].sum() if x['Sq.m'].sum()>0 else 0
    ).reset_index()
    wac.columns = ['Product No.','WAC Rate']

    tab1, tab2, tab3 = st.tabs(["📦 Product vs Salesman","🧑‍💼 Salesman Overall","🏆 Rate Leaders"])

    with tab1:
        st.subheader("Product-wise Rate Comparison Across Salesmen")
        st.caption("Shows every product sold by 2+ salesmen — who sold higher?")

        sal_prod = sales_df.groupby(['Product No.','Salesman']).agg(
            Total_Value =('SALE',         'sum'),
            Total_Sqm   =('Sq.m',         'sum'),
            Bills       =('Bill No.',     'nunique'),
            Customers   =('Account Name', 'nunique'),
        ).reset_index()
        sal_prod = sal_prod[sal_prod['Total_Sqm']>0]
        sal_prod['Avg Rate'] = (sal_prod['Total_Value'] / sal_prod['Total_Sqm']).round(0)
        sal_prod = sal_prod.merge(wac, on='Product No.', how='left')
        sal_prod = sal_prod.merge(prod[['Product No.','Brand Name','Category','Size']], on='Product No.', how='left')
        sal_prod['Rate vs WAC'] = (sal_prod['Avg Rate'] - sal_prod['WAC Rate']).round(0)
        sal_prod['Margin%']     = (sal_prod['Rate vs WAC'] / sal_prod['WAC Rate'] * 100).round(1)

        # Filter to products sold by 2+ salesmen
        multi = sal_prod.groupby('Product No.')['Salesman'].nunique()
        multi_prods = multi[multi>=2].index

        c1,c2,c3 = st.columns(3)
        with c1:
            show_all = st.checkbox("Show all products (including single salesman)", value=False)
        with c2:
            min_sqm = st.number_input("Min Sqm Sold", value=0, step=10, key="sra_sqm")
        with c3:
            br_f = st.selectbox("Brand", ['All']+sorted(prod['Brand Name'].dropna().unique().tolist()), key="sra_br")

        if not show_all:
            disp_prod = sal_prod[sal_prod['Product No.'].isin(multi_prods)]
        else:
            disp_prod = sal_prod.copy()

        if min_sqm > 0:   disp_prod = disp_prod[disp_prod['Total_Sqm']>=min_sqm]
        if br_f != 'All': disp_prod = disp_prod[disp_prod['Brand Name']==br_f]

        disp_prod = disp_prod.sort_values(['Product No.','Avg Rate'], ascending=[True,False])
        disp_prod['Avg Rate']    = disp_prod['Avg Rate'].apply(lambda x: f"Rs {x:,.0f}")
        disp_prod['WAC Rate']    = disp_prod['WAC Rate'].apply(lambda x: f"Rs {x:,.0f}")
        disp_prod['Rate vs WAC'] = disp_prod['Rate vs WAC'].apply(lambda x: f"+Rs {x:,.0f}" if x>0 else f"Rs {x:,.0f}")

        st.caption(f"Showing {len(disp_prod):,} rows — {disp_prod['Product No.'].nunique():,} products")
        st.dataframe(disp_prod[['Product No.','Brand Name','Size','Salesman','Total_Sqm','Bills','Customers','Avg Rate','WAC Rate','Rate vs WAC','Margin%']],
                     hide_index=True, use_container_width=True)
        st.download_button("📥 Download", disp_prod.to_csv(index=False), "salesman_rates.csv")

    with tab2:
        st.subheader("Overall Salesman Avg Selling Rate")
        st.caption("Higher avg rate = sells premium products or negotiates better prices")

        sal_overall = sales_df.groupby('Salesman').agg(
            Total_Value  =('SALE',          'sum'),
            Total_Sqm    =('Sq.m',          'sum'),
            Total_Ret    =('RETURN',         'sum'),
            Bills        =('Bill No.',       'nunique'),
            Customers    =('Account Name',   'nunique'),
            Products     =('Product No.',    'nunique'),
        ).reset_index()
        sal_overall = sal_overall[sal_overall['Total_Sqm']>0]
        sal_overall['Avg Rate']      = (sal_overall['Total_Value'] / sal_overall['Total_Sqm']).round(0)
        sal_overall['Net Revenue']   = sal_overall['Total_Value'] - sal_overall['Total_Ret']
        sal_overall['Revenue']       = sal_overall['Total_Value'].apply(fmt_m)
        sal_overall['Net Rev']       = sal_overall['Net Revenue'].apply(fmt_m)
        sal_overall['Avg Bill Val']  = (sal_overall['Total_Value'] / sal_overall['Bills']).round(0)
        sal_overall = sal_overall.sort_values('Avg Rate', ascending=False)

        # Totals row
        totals = pd.DataFrame([{
            'Salesman'   : '📊 TOTAL',
            'Total_Value': sal_overall['Total_Value'].sum(),
            'Total_Sqm'  : sal_overall['Total_Sqm'].sum(),
            'Bills'      : sal_overall['Bills'].sum(),
            'Customers'  : sales_df['Account Name'].nunique(),
            'Products'   : sales_df['Product No.'].nunique(),
            'Avg Rate'   : (sal_overall['Total_Value'].sum()/sal_overall['Total_Sqm'].sum()),
            'Net Revenue': sal_overall['Net Revenue'].sum(),
            'Revenue'    : fmt_m(sal_overall['Total_Value'].sum()),
            'Net Rev'    : fmt_m(sal_overall['Net Revenue'].sum()),
            'Avg Bill Val': (sal_overall['Total_Value'].sum()/sal_overall['Bills'].sum()),
        }])
        display = pd.concat([sal_overall, totals], ignore_index=True)
        display['Avg Rate']     = display['Avg Rate'].apply(lambda x: f"Rs {x:,.0f}")
        display['Avg Bill Val'] = display['Avg Bill Val'].apply(lambda x: f"Rs {x:,.0f}")

        st.dataframe(display[['Salesman','Revenue','Net Rev','Total_Sqm','Bills','Customers','Products','Avg Rate','Avg Bill Val']],
                     hide_index=True, use_container_width=True)

    with tab3:
        st.subheader("🏆 Rate Leaders — Who Sells Each Product Highest?")
        st.caption("For each product sold by multiple salesmen — who consistently gets the best rate?")

        sal_prod2 = sales_df.groupby(['Product No.','Salesman']).agg(
            Total_Value=('SALE','sum'), Total_Sqm=('Sq.m','sum'), Bills=('Bill No.','nunique')
        ).reset_index()
        sal_prod2 = sal_prod2[sal_prod2['Total_Sqm']>0]
        sal_prod2['Avg Rate'] = (sal_prod2['Total_Value']/sal_prod2['Total_Sqm']).round(0)

        multi2 = sal_prod2.groupby('Product No.')['Salesman'].nunique()
        multi_prods2 = multi2[multi2>=2].index
        sal_prod2 = sal_prod2[sal_prod2['Product No.'].isin(multi_prods2)]

        # Best rate per product
        best  = sal_prod2.loc[sal_prod2.groupby('Product No.')['Avg Rate'].idxmax()][['Product No.','Salesman','Avg Rate']].rename(columns={'Salesman':'Best Rate By','Avg Rate':'Best Rate'})
        worst = sal_prod2.loc[sal_prod2.groupby('Product No.')['Avg Rate'].idxmin()][['Product No.','Salesman','Avg Rate']].rename(columns={'Salesman':'Lowest Rate By','Avg Rate':'Lowest Rate'})

        leaders = best.merge(worst, on='Product No.', how='left')
        leaders = leaders.merge(prod[['Product No.','Brand Name','Category','Size']], on='Product No.', how='left')
        leaders['Rate Diff'] = leaders['Best Rate'] - leaders['Lowest Rate']
        leaders = leaders[leaders['Rate Diff']>0].sort_values('Rate Diff', ascending=False)
        leaders['Best Rate']    = leaders['Best Rate'].apply(lambda x: f"Rs {x:,.0f}")
        leaders['Lowest Rate']  = leaders['Lowest Rate'].apply(lambda x: f"Rs {x:,.0f}")
        leaders['Rate Diff']    = leaders['Rate Diff'].apply(lambda x: f"Rs {x:,.0f}")

        st.caption(f"Showing {len(leaders):,} products with rate differences")
        st.dataframe(leaders[['Product No.','Brand Name','Category','Size','Best Rate By','Best Rate','Lowest Rate By','Lowest Rate','Rate Diff']],
                     hide_index=True, use_container_width=True)

        st.divider()
        st.subheader("🏅 Leaderboard — Most Products with Best Rate")
        board = sal_prod2.loc[sal_prod2.groupby('Product No.')['Avg Rate'].idxmax()].groupby('Salesman').size().reset_index(name='Products with Best Rate').sort_values('Products with Best Rate', ascending=False)
        st.dataframe(board, hide_index=True, use_container_width=True)
