import streamlit as st
import pandas as pd
import numpy as np
import io
import requests
from google.oauth2 import service_account
import google.auth.transport.requests

st.set_page_config(page_title="MiTiles Dashboard", layout="wide")

# ----------------------------
# PRODUCT CLEANING
# ----------------------------

def clean_product(x):
    return (
        str(x)
        .replace("\xa0", " ")
        .replace("  ", " ")
        .strip()
    )

# ----------------------------
# LOAD DATA
# ----------------------------

@st.cache_data(ttl=3600)
def load_data():

    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )

    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)

    file_id = st.secrets["GOOGLE_FILE_ID"]

    url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx"

    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {creds.token}"}
    )

    buffer = io.BytesIO(response.content)

    df = pd.read_excel(buffer, sheet_name="SALE HISTORY")

    buffer.seek(0)
    prod = pd.read_excel(buffer, sheet_name="PRODUCT DATA")

    # ----------------------------
    # DATE CLEANING
    # ----------------------------

    df["Date"] = pd.to_datetime(
        df["Date"].astype(str).str.replace("\xa0"," ").str.strip(),
        errors="coerce",
        dayfirst=True
    )

    df = df[df["Date"].notna()]

    # ----------------------------
    # PRODUCT CLEAN
    # ----------------------------

    df["Product No."] = df["Product No."].apply(clean_product)
    prod["Product No."] = prod["Product No."].apply(clean_product)

    # ----------------------------
    # REMOVE NON STOCK TYPES
    # ----------------------------

    valid_types = ["P","S","S.R","P.R","O.S"]
    df = df[df["Type"].isin(valid_types)]

    # ----------------------------
    # NUMERIC CLEAN
    # ----------------------------

    numeric_cols = [
        "Sq.m","Rate","Closing","Profit",
        "SALE","RETURN"
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",",""),
                errors="coerce"
            ).fillna(0)

    # ----------------------------
    # SORT
    # ----------------------------

    sort_cols = ["Product No.","Date"]

    if "Invoice No." in df.columns:
        sort_cols.append("Invoice No.")

    df = df.sort_values(sort_cols, kind="mergesort").reset_index(drop=True)

    # ----------------------------
    # SALES VALUE FIX
    # ----------------------------

    sale_mask = (df["SALE"] == 0) & (df["Type"] == "S")
    df.loc[sale_mask,"SALE"] = df.loc[sale_mask,"Sq.m"] * df.loc[sale_mask,"Rate"]

    ret_mask = (df["RETURN"] == 0) & (df["Type"] == "S.R")
    df.loc[ret_mask,"RETURN"] = df.loc[ret_mask,"Sq.m"] * df.loc[ret_mask,"Rate"]

    # ----------------------------
    # MERGE PRODUCT MASTER
    # ----------------------------

    df = df.merge(
        prod[
            [
                "Product No.",
                "Brand Name",
                "Category",
                "Sub-Category",
                "Size",
                "Company Name",
                "Sq.m/Box"
            ]
        ],
        on="Product No.",
        how="left"
    )

    # ----------------------------
    # WAC CALCULATION
    # ----------------------------

    purch = df[df["Type"].isin(["P","O.S"])]

    wac = (
        purch.assign(value=purch["Sq.m"] * purch["Rate"])
        .groupby("Product No.",as_index=False)
        .agg({"value":"sum","Sq.m":"sum"})
    )

    wac["WAC Rate"] = wac["value"] / wac["Sq.m"]

    wac = wac[["Product No.","WAC Rate"]]

    df = df.merge(wac,on="Product No.",how="left")

    df["WAC Rate"] = df["WAC Rate"].fillna(0)

    # ----------------------------
    # ACTUAL PROFIT
    # ----------------------------

    df["Actual Profit"] = np.where(
        df["Type"] == "S",
        df["SALE"] - df["Sq.m"] * df["WAC Rate"],
        0
    )

    return df, prod


df, prod = load_data()

# ----------------------------
# DEBUG INVENTORY
# ----------------------------

def debug_inventory(df, product):

    x = df[df["Product No."] == product].copy()

    x = x.sort_values(["Date"])

    x["Change"] = np.where(
        x["Type"].isin(["P","O.S"]), x["Sq.m"],
        np.where(
            x["Type"].isin(["S","P.R"]), -x["Sq.m"],
            np.where(x["Type"]=="S.R", x["Sq.m"],0)
        )
    )

    x["Running Stock"] = x["Change"].cumsum()

    return x


# ----------------------------
# DASHBOARD
# ----------------------------

st.title("MiTiles Inventory Dashboard")

col1,col2,col3 = st.columns(3)

col1.metric("Transactions",len(df))
col2.metric("Products",df["Product No."].nunique())
col3.metric("Total Stock",round(df["Closing"].iloc[-1],2))

# ----------------------------
# DEBUG TOOL
# ----------------------------

st.sidebar.header("Debug")

product = st.sidebar.text_input(
    "Product Number",
    "OCM6600051"
)

if product:

    debug = debug_inventory(df,product)

    st.subheader(f"Inventory Timeline — {product}")

    st.dataframe(debug)