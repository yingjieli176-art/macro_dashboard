"""MOF three-month Treasury discount bill auction yields (not daily fixings)."""
import json
from pathlib import Path
import re

import pandas as pd
from lxml import html

from macro_platform.request_runtime import observed_cache

SNAPSHOT = Path(__file__).resolve().parents[1] / "data_snapshots/japan_3m_auctions.json"
ARCHIVE_URL = "https://www.mof.go.jp/jgbs/reference/appendix/fb_historical_data.xls"
CALENDAR_URL = "https://www.mof.go.jp/jgbs/auction/calendar/{month}.htm"
COLUMN = "japan_3m"


def clean_observations(frame):
    out = frame.reindex(columns=["observation_date", COLUMN]).copy()
    out["observation_date"] = pd.to_datetime(out.observation_date, errors="coerce")
    out[COLUMN] = pd.to_numeric(out[COLUMN], errors="coerce")
    today = pd.Timestamp.now(tz="Asia/Tokyo").tz_localize(None).normalize()
    return (out.loc[out.observation_date.le(today) & out[COLUMN].between(-10, 30)]
            .dropna().sort_values("observation_date")
            .drop_duplicates("observation_date", keep="last").reset_index(drop=True))


@observed_cache(paths=lambda: [SNAPSHOT], ttl=300)
def load_japan_3m():
    """Use the scheduled, verified snapshot without adding chart-time requests."""
    try:
        payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        if payload["unit"] != "percent" or payload["series_id"] != "MOF_TBILL_3M_AVERAGE_AUCTION":
            raise ValueError("Wrong Japanese 3M series")
        return clean_observations(pd.DataFrame(payload["records"]))
    except (OSError, ValueError, KeyError, TypeError):
        return clean_observations(pd.DataFrame())


def auction_result_urls(text):
    """Select only results explicitly identified as three-month bills."""
    tree = html.fromstring(text)
    return [a.get("href").strip() for row in tree.xpath("//tr")
            if "国庫短期証券（3ヶ月）" in row.text_content()
            for a in row.xpath(".//a[@href]")
            if re.fullmatch(r"https://www\.mof\.go\.jp/jgbs/auction/calendar/tbill/tbill_nyusatsu/resul\d{8}\.htm", a.get("href").strip())]


def parse_auction_result(text, url):
    rows = html.fromstring(text).xpath("//tr")
    for row in rows:
        content = " ".join(row.text_content().split())
        if "募入平均利回り" in content:
            match = re.search(r"([-+]?\d+(?:\.\d+)?)\s*[％%]", content)
            if match:
                return {"observation_date": pd.to_datetime(re.search(r"resul(\d{8})", url)[1]).strftime("%Y-%m-%d"),
                        COLUMN: float(match[1])}
    raise ValueError("MOF average auction yield missing")
