import pandas as pd
import requests
from io import StringIO


def get_fred_series(series_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"

    response = requests.get(url, timeout=10)
    response.raise_for_status()

    df = pd.read_csv(StringIO(response.text))
    df["observation_date"] = pd.to_datetime(df["observation_date"])
    df = df.tail(600)

    return df


def get_dgs10():
    return get_fred_series("DGS10")


def get_dfii10():
    return get_fred_series("DFII10")


def get_breakeven10():
    nominal = get_dgs10()
    real = get_dfii10()

    df = pd.merge(
        nominal,
        real,
        on="observation_date",
        how="inner"
    )

    df["BREAKEVEN10"] = df["DGS10"] - df["DFII10"]

    return df
