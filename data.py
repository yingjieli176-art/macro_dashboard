import streamlit as st
import pandas as pd
import requests


FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"


def get_fred_series(series_id):
    api_key = st.secrets["FRED_API_KEY"]

    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "asc"
    }

    response = requests.get(
        FRED_API_URL,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    df = pd.DataFrame(data["observations"])

    df["observation_date"] = pd.to_datetime(
        df["date"]
    )

    df[series_id] = pd.to_numeric(
        df["value"],
        errors="coerce"
    )

    return df[
        ["observation_date", series_id]
    ]


# =========================
# Funding / Liquidity
# =========================

@st.cache_data(ttl=3600)
def get_sofr():
    return get_fred_series("SOFR")


@st.cache_data(ttl=3600)
def get_iorb():
    return get_fred_series("IORB")


@st.cache_data(ttl=3600)
def get_effr():
    return get_fred_series("EFFR")


@st.cache_data(ttl=3600)
def get_rrp():
    return get_fred_series("RRPONTSYAWARD")


# =========================
# Yield
# =========================

@st.cache_data(ttl=3600)
def get_dgs10():
    return get_fred_series("DGS10")


@st.cache_data(ttl=3600)
def get_dfii10():
    return get_fred_series("DFII10")
