"""BIS daily Japan policy settings with a verified repository fallback."""
from io import StringIO
import json
from pathlib import Path

import pandas as pd
import requests

from macro_platform.fred_observations import validate_observations
from macro_platform.request_runtime import http_get, observed_cache


BOJ_POLICY_NAME = "BOJ 政策利率（右轴）"
SERIES = "D.JP"
API_URL = "https://stats.bis.org/api/v1/data/BIS,WS_CBPOL,1.0/D.JP"
SNAPSHOT = Path(__file__).resolve().parents[1] / "data_snapshots/boj_policy_rate.json"
RATE_COLUMN = "boj_policy_pct"


def _validated_policy(frame):
    frame["observation_date"] = pd.to_datetime(frame.observation_date, format="%Y-%m-%d")
    frame[RATE_COLUMN] = pd.to_numeric(frame[RATE_COLUMN], errors="raise")
    return validate_observations(frame.sort_values("observation_date"), SERIES, value_column=RATE_COLUMN)


def parse_bis_policy_csv(text):
    raw = pd.read_csv(StringIO(text), dtype={"UNIT_MEASURE": str})
    expected = {"DATAFLOW": "BIS:WS_CBPOL(1.0)", "FREQ": "D", "REF_AREA": "JP", "UNIT_MEASURE": "368"}
    if not {*expected, "TIME_PERIOD", "OBS_VALUE"}.issubset(raw.columns) or any(
        not raw[column].eq(value).all() for column, value in expected.items()
    ):
        raise ValueError("Expected BIS Japan daily policy interest rate in percent")
    return _validated_policy(raw[["TIME_PERIOD", "OBS_VALUE"]].rename(
        columns={"TIME_PERIOD": "observation_date", "OBS_VALUE": RATE_COLUMN}))


@observed_cache(ttl=3600)
def _fetch_bis_policy(start):
    response = http_get(API_URL, params={"startPeriod": start},
                        headers={"Accept": "application/vnd.sdmx.data+csv;version=1.0.0"},
                        timeout=(2, 4))
    response.raise_for_status()
    return parse_bis_policy_csv(response.text)


def load_boj_policy(path=SNAPSHOT):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload["series_id"] != SERIES or payload["unit"] != "percent":
            raise ValueError("Wrong BOJ policy snapshot")
        archive = _validated_policy(pd.DataFrame(payload["records"], columns=["observation_date", RATE_COLUMN]))
    except (OSError, ValueError, KeyError, TypeError):
        archive = pd.DataFrame(columns=["observation_date", RATE_COLUMN])
    start = archive.observation_date.max().strftime("%Y-%m-%d") if not archive.empty else "2021-01-01"
    try:
        recent = _fetch_bis_policy(start)
    except (requests.RequestException, ValueError):
        return archive
    if archive.empty:
        return recent
    return pd.concat([archive, recent], ignore_index=True).drop_duplicates(
        "observation_date", keep="last").sort_values("observation_date")
