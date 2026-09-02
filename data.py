import streamlit as st
import pandas as pd
import requests


# =========================
# FRED API
# =========================

FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"


def get_fred_series(series_id):
    """
    从 FRED API 获取指定经济指标
    """

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
# 10Y Treasury
# =========================

@st.cache_data(ttl=3600)
def get_dgs10():

    return get_fred_series(
        "DGS10"
    )


# =========================
# 10Y TIPS Real Yield
# =========================

@st.cache_data(ttl=3600)
def get_dfii10():

    return get_fred_series(
        "DFII10"
    )
