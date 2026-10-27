"""CSI price-index closes and full-history drawdowns, without live estimates."""
import json
from pathlib import Path

import pandas as pd

from macro_platform.equity_drawdown import calculate_drawdown, build_drawdown_figure
from macro_platform.request_runtime import observed_cache

SNAPSHOT = Path(__file__).resolve().parents[1] / "data_snapshots/china_equity_daily.json"
SOURCE = "https://www.csindex.com.cn/csindex-home/perf/index-perf"
PRICE_BASIS = "index_price_close_ex_dividends"
SERIES = {
    "000300": {"name": "沪深300", "color": "#5070dd", "base_date": "2004-12-31"},
    "000852": {"name": "中证1000", "color": "#ea580c", "base_date": "2004-12-31"},
    "932000": {"name": "中证2000", "color": "#16a34a", "base_date": "2013-12-31"},
}


def completed_china_date(now=None):
    clock = pd.Timestamp.now(tz="Asia/Shanghai") if now is None else pd.Timestamp(now)
    clock = clock.tz_localize("UTC") if clock.tzinfo is None else clock
    clock = clock.tz_convert("Asia/Shanghai")
    day = clock.normalize().tz_localize(None)
    return day if (clock.hour, clock.minute) >= (15, 15) else day - pd.Timedelta(days=1)


def parse_csindex_history(payload, code, now=None):
    config = SERIES[code]
    if payload.get("success") is not True or not payload.get("data"):
        raise ValueError(f"{code}: missing official CSI history")
    records = payload["data"]
    if any(str(row.get("indexCode")) != code or row.get("indexNameCn") != config["name"]
           for row in records):
        raise ValueError(f"{code}: wrong index identity")
    frame = pd.DataFrame(records)
    frame["observation_date"] = pd.to_datetime(frame.tradeDate, format="%Y%m%d", errors="coerce")
    # The API can insert a carry-in value at the requested startDate, even
    # before the index base date. It is not an original index observation.
    frame = frame.loc[frame.observation_date.ge(config["base_date"])
                      & frame.observation_date.le(completed_china_date(now))]
    frame = calculate_drawdown(frame)[["observation_date", "close"]].dropna(subset=["close"])
    if frame.observation_date.dt.dayofweek.ge(5).any():
        raise ValueError(f"{code}: unexpected weekend observation")
    return frame


@observed_cache(paths=lambda: (SNAPSHOT,))
def load_china_history(code):
    empty = pd.DataFrame(columns=["observation_date", "close"])
    try:
        payload = json.loads(SNAPSHOT.read_text())
        node = payload["series"][code]
        if (payload.get("price_basis") != PRICE_BASIS or node.get("code") != code
                or node.get("frequency") != "1d"):
            return empty
        frame = calculate_drawdown(pd.DataFrame(node["records"]).rename(columns={"date": "observation_date"}))
        return frame.loc[frame.observation_date.ge(SERIES[code]["base_date"])
                         & frame.observation_date.le(completed_china_date()), ["observation_date", "close"]]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return empty


def build_china_drawdown_figure(histories=None):
    if histories is None:
        histories = {code: load_china_history(code) for code in SERIES}
    figure = build_drawdown_figure(histories, series=SERIES)
    figure.layout.meta["price_basis"] = PRICE_BASIS
    return figure
