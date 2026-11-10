"""Refresh five years of observed MOF 3M auction yields; xlrd is maintenance-only."""
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import sys

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from macro_platform.japan_short_rates import (
    ARCHIVE_URL, CALENDAR_URL, COLUMN, SNAPSHOT, auction_result_urls,
    clean_observations, load_japan_3m, parse_auction_result,
)


def get(url):
    response = requests.get(url, timeout=(12, 35))
    response.raise_for_status()
    response.encoding = "utf-8"
    return response


def read_archive(content, cutoff):
    frames = []
    book = pd.ExcelFile(BytesIO(content), engine="xlrd")
    # The newest six fiscal years cover the supported five-year viewport.
    for sheet in book.sheet_names[:6]:
        raw = pd.read_excel(book, sheet_name=sheet, header=None)
        if raw.iloc[2, 1] != "入札日" or raw.iloc[3, 8] != "平均利回":
            raise ValueError("MOF auction archive schema changed")
        dates = raw.iloc[6:, 1:4].apply(lambda col: pd.to_datetime(col, errors="coerce"))
        # Bills issued as 3M can run slightly longer around year-end holidays.
        is_3m = (dates.iloc[:, 2] - dates.iloc[:, 1]).dt.days.between(80, 110)
        frame = pd.DataFrame({"observation_date": dates.iloc[:, 0], COLUMN: raw.loc[dates.index, 8]})
        frames.append(frame.loc[is_3m & dates.iloc[:, 0].ge(cutoff)])
    return clean_observations(pd.concat(frames, ignore_index=True))


def main():
    today = pd.Timestamp.now(tz="Asia/Tokyo").tz_localize(None).normalize()
    cutoff = today - pd.DateOffset(years=5, days=14)
    previous = load_japan_3m()
    archive = read_archive(get(ARCHIVE_URL).content, cutoff)
    frames = [previous, archive]
    # Bridge the lag between the monthly archive and today's auction calendar.
    start = archive.observation_date.max().replace(day=1)
    urls = []
    for month in pd.date_range(start, today, freq="MS"):
        url = CALENDAR_URL.format(month=month.strftime("%y%m"))
        urls.extend(result for result in auction_result_urls(get(url).text)
                    if result[-12:-4] > archive.observation_date.max().strftime("%Y%m%d"))
    records = [parse_auction_result(get(url).text, url) for url in dict.fromkeys(urls)]
    if records:
        frames.append(pd.DataFrame(records))
    combined = clean_observations(pd.concat(frames, ignore_index=True))
    combined = combined.loc[combined.observation_date.ge(cutoff)]
    if len(combined) < 240 or (today - combined.observation_date.max()).days > 14:
        raise ValueError("MOF 3M history is incomplete or stale")
    if not previous.empty and combined.observation_date.max() < previous.observation_date.max():
        raise ValueError("MOF 3M history regressed")
    combined["observation_date"] = combined.observation_date.dt.strftime("%Y-%m-%d")
    payload = dict(series_id="MOF_TBILL_3M_AVERAGE_AUCTION", unit="percent",
                   source="Japan MOF 3-month Treasury discount bills, average auction yield",
                   source_urls=[ARCHIVE_URL, *dict.fromkeys(urls)],
                   updated_at=datetime.now(timezone.utc).isoformat(),
                   records=combined.to_dict("records"))
    SNAPSHOT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print("MOF 3M", len(combined), payload["records"][-1])


if __name__ == "__main__":
    main()
