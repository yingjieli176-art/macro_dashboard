"""Append EUR/USD and USD/JPY 1M observations from MINKABU's dated FX reports."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from unicodedata import normalize
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from lxml import html
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from macro_platform.cross_asset_volatility import (
    EURUSD_REFERENCE_IDENTITY, EURUSD_REFERENCE_SNAPSHOT, MINKABU_NEWS_URL,
    USDJPY_REFERENCE_IDENTITY, USDJPY_REFERENCE_SNAPSHOT, _validate_records,
)

PAIRS = {"EURUSD": EURUSD_REFERENCE_IDENTITY, "USDJPY": USDJPY_REFERENCE_IDENTITY}
TOKYO = ZoneInfo("Asia/Tokyo")
REPORT_TITLE = re.compile(r"通貨オプション\s+ボラティリティ[ーｰ]?")
ARTICLE_URL = re.compile(r"https://fx\.minkabu\.jp/news/[0-9]+/?")
NUMBER = r"([0-9]+(?:\.[0-9]+)?)"
TABLE = re.compile(
    r"USD/JPY\s+EUR/USD\s+EUR/JPY\s+GBP/USD\s+1WK\s+"
    + r"\s+".join([NUMBER] * 4)
    + r"\s+1MO\s+" + r"\s+".join([NUMBER] * 4) + r"(?=\s|$)"
)


def _report_links(document):
    for anchor in html.fromstring(document).xpath("//a[@href]"):
        url = urljoin(MINKABU_NEWS_URL + "/", anchor.get("href"))
        title = normalize("NFKC", " ".join(anchor.itertext()))
        if ARTICLE_URL.fullmatch(url) and REPORT_TITLE.search(title):
            yield url.rstrip("/")


def parse_report(document, url, now=None):
    page = html.fromstring(document)
    titles = page.xpath("//h1")
    if not titles or not REPORT_TITLE.search(normalize("NFKC", titles[0].text_content())):
        raise ValueError("Not a MINKABU FX option volatility report")
    for br in page.xpath("//br"):
        br.tail = " " + (br.tail or "")
    text = normalize("NFKC", " ".join(page.itertext()))
    table = TABLE.search(text)
    published = re.search(r"(20\d{2}/\d{2}/\d{2})\s*\([^)]{1,3}\)\s*(\d{1,2}:\d{2})", text)
    clock = re.search(r"東京時間\s*(\d{1,2}:\d{2})\s*現在", text)
    if table is None or published is None or clock is None:
        raise ValueError("Missing FX option table or dated Tokyo observation")
    day, published_time = published.groups()
    stamp = datetime.strptime(f"{day} {clock[1]}", "%Y/%m/%d %H:%M").replace(tzinfo=TOKYO)
    publication = datetime.strptime(f"{day} {published_time}", "%Y/%m/%d %H:%M").replace(tzinfo=TOKYO)
    if stamp > publication or publication > (now or datetime.now(timezone.utc)):
        raise ValueError("Invalid observation or publication time")
    yen, euro = map(float, table.groups()[4:6])
    if not all(0 < value < 100 for value in (yen, euro)):
        raise ValueError("Invalid 1M implied volatility")
    return {
        pair: {"observation_date": stamp.date().isoformat(),
               "observation_timestamp": stamp.isoformat(), "value": value, "source_url": url}
        for pair, value in (("EURUSD", euro), ("USDJPY", yen))
    }


def fetch(url):
    response = requests.get(url, timeout=(5, 20), headers={
        "User-Agent": "Mozilla/5.0 (compatible; macro-dashboard-data-collector/1.0)"})
    response.raise_for_status()
    return response


def collect_observations(get=fetch, *, pages=5, now=None):
    links = {}
    for index in range(1, pages + 1):
        endpoint = MINKABU_NEWS_URL if index == 1 else f"{MINKABU_NEWS_URL}?page={index}"
        links.update(dict.fromkeys(_report_links(get(endpoint).text)))
    observations = {pair: {} for pair in PAIRS}
    for url in links:
        try:
            records = parse_report(get(url).text, url, now=now)
        except (requests.RequestException, ValueError) as exc:
            print(f"MINKABU report skipped: {url} ({exc})", file=sys.stderr)
            continue
        for pair, row in records.items():
            day = row["observation_date"]
            prior = observations[pair].get(day)
            if not prior or row["observation_timestamp"] > prior["observation_timestamp"]:
                observations[pair][day] = row
    if not any(observations.values()):
        raise ValueError("No verified MINKABU one-month observations")
    return {pair: [rows[day] for day in sorted(rows)] for pair, rows in observations.items()}


def update_snapshot(path, identity, observations):
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else dict(identity, records=[])
    _validate_records(payload, identity)
    previous = payload["records"]
    merged = {row["observation_date"]: row for row in previous}
    for row in observations:
        day = row["observation_date"]
        if day not in merged or row["observation_timestamp"] > merged[day]["observation_timestamp"]:
            merged[day] = row
    records = [merged[day] for day in sorted(merged)]
    if records == previous:
        return records
    payload.update(source_url=records[-1]["source_url"], coverage_start=records[0]["observation_date"],
                   coverage_end=records[-1]["observation_date"], record_count=len(records), records=records)
    _validate_records(payload, identity)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=EURUSD_REFERENCE_SNAPSHOT)
    parser.add_argument("--usdjpy-snapshot", type=Path, default=USDJPY_REFERENCE_SNAPSHOT)
    args = parser.parse_args()
    observed = collect_observations()
    for pair, path in (("EURUSD", args.snapshot), ("USDJPY", args.usdjpy_snapshot)):
        records = update_snapshot(path, PAIRS[pair], observed[pair])
        print(f"{pair} 1M MINKABU: {len(records)} observations, latest={records[-1]['observation_date']}")


if __name__ == "__main__":
    main()
