from __future__ import annotations

import io
import json
import re
import time
from calendar import monthrange
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_snapshots" / "copper_market_daily.json"

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/HG%3DF"
WESTMETALL_URL = "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Cu_cash&year={year}"
COCHILCO_URL = "https://boletin.cochilco.cl/productos/boletin.asp?anio={year}&mes={month:02d}&tabla=tabla4_2"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MacroDashboard/1.0; +https://github.com/yingjieli176-art/macro_dashboard)",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
}


def _five_year_start() -> date:
    today = date.today()
    try:
        return today.replace(year=today.year - 5)
    except ValueError:
        return today.replace(year=today.year - 5, day=28)


def _request(url: str, *, timeout: int = 30, attempts: int = 3) -> requests.Response:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            response = requests.get(url, headers=HEADERS, timeout=timeout)
            response.raise_for_status()
            return response
        except Exception as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"request failed for {url}: {last}")


def _fetch_comex_price() -> pd.DataFrame:
    response = _request(
        YAHOO_CHART_URL
        + "?range=5y&interval=1d&includePrePost=false&events=div%2Csplits",
        timeout=20,
    )
    result = (((response.json() or {}).get("chart") or {}).get("result") or [])
    if not result:
        raise RuntimeError("Yahoo HG=F returned no chart result")
    node = result[0]
    timestamps = node.get("timestamp") or []
    closes = (((node.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
    size = min(len(timestamps), len(closes))
    if not size:
        raise RuntimeError("Yahoo HG=F returned no daily closes")
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(timestamps[:size], unit="s", utc=True).tz_convert("America/New_York").tz_localize(None).normalize(),
            "comex_price_usd_lb": pd.to_numeric(closes[:size], errors="coerce"),
        }
    )
    return frame.dropna().drop_duplicates("date", keep="last").sort_values("date")


def _fetch_westmetall_year(year: int) -> pd.DataFrame:
    response = _request(WESTMETALL_URL.format(year=year), timeout=35)
    tables = pd.read_html(io.StringIO(response.text), thousands=",", decimal=".")
    target = None
    for table in tables:
        if any("Cash-Settlement" in str(col) for col in table.columns):
            target = table
            break
    if target is None or target.empty:
        raise RuntimeError(f"Westmetall copper table not found for {year}")

    work = target.iloc[:, :4].copy()
    work.columns = ["date", "lme_cash_usd_t", "lme_3m_usd_t", "lme_stock_t"]
    work = work[work["date"].astype(str).str.lower() != "date"]
    work["date"] = pd.to_datetime(work["date"], format="%d. %B %Y", errors="coerce")
    for col in ("lme_cash_usd_t", "lme_3m_usd_t", "lme_stock_t"):
        work[col] = pd.to_numeric(work[col], errors="coerce")
    return work.dropna(subset=["date"]).drop_duplicates("date", keep="last").sort_values("date")


def _fetch_lme_history() -> pd.DataFrame:
    start = _five_year_start()
    frames = []
    for year in range(start.year, date.today().year + 1):
        frames.append(_fetch_westmetall_year(year))
        time.sleep(0.35)
    data = pd.concat(frames, ignore_index=True)
    return data[data["date"].dt.date >= start].drop_duplicates("date", keep="last").sort_values("date")


def _parse_mt(text: str) -> float | None:
    cleaned = re.sub(r"\s+", "", str(text or "")).replace("\xa0", "")
    if cleaned in {"", "-", "–", "—"}:
        return None
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_cochilco_month(year: int, month: int) -> list[dict]:
    """Parse COCHILCO table 4.2 while preserving Chilean thousands separators.

    Data rows have the form:
      day | LME America | Asia | Europe | LME total | change |
      COMEX total | change | SHFE total | change | combined total | change
    """
    url = COCHILCO_URL.format(year=year, month=month)
    response = _request(url, timeout=25, attempts=2)
    soup = BeautifulSoup(response.text, "html.parser")
    rows: list[dict] = []

    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) < 7:
            continue
        first = re.sub(r"\D", "", cells[0])
        if not first or len(first) > 2:
            continue
        day = int(first)
        if day < 1 or day > monthrange(year, month)[1]:
            continue
        lme_total = _parse_mt(cells[4])
        comex_total = _parse_mt(cells[6])
        if lme_total is None and comex_total is None:
            continue
        try:
            stamp = date(year, month, day).isoformat()
        except ValueError:
            continue
        rows.append(
            {
                "date": stamp,
                "cochilco_lme_stock_t": lme_total,
                "comex_stock_t": comex_total,
            }
        )

    if not rows:
        raise RuntimeError(f"COCHILCO copper inventory table had no data rows: {year}-{month:02d}")
    return rows


def _iter_months(start: date, end: date):
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1


def _load_existing_inventory() -> dict[str, dict]:
    if not OUT.exists():
        return {}
    try:
        payload = json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return {}
    result = {}
    for row in payload.get("records") or []:
        stamp = str(row.get("date") or "")
        if len(stamp) != 10:
            continue
        if row.get("comex_stock_t") is None and row.get("cochilco_lme_stock_t") is None:
            continue
        result[stamp] = {
            "date": stamp,
            "comex_stock_t": row.get("comex_stock_t"),
            "cochilco_lme_stock_t": row.get("cochilco_lme_stock_t"),
        }
    return result


def _fetch_comex_inventory() -> pd.DataFrame:
    existing = _load_existing_inventory()
    today = date.today()
    start = _five_year_start()

    # First publication backfills the full dashboard horizon. Once the snapshot
    # exists, retain its history and refresh only the current and prior month.
    if len(existing) >= 300:
        refresh_start = (today.replace(day=1) - pd.DateOffset(months=1)).date()
    else:
        refresh_start = start.replace(day=1)

    for year, month in _iter_months(refresh_start, today):
        try:
            batch = _parse_cochilco_month(year, month)
            for row in batch:
                existing[row["date"]] = row
            print("COCHILCO", year, f"{month:02d}", "rows", len(batch), flush=True)
        except Exception as exc:
            # Current-month bulletin pages may not be published yet. Historical
            # gaps remain visible rather than blocking the entire snapshot.
            print("COCHILCO unavailable", year, f"{month:02d}", repr(exc), flush=True)
        time.sleep(0.15)

    rows = [row for stamp, row in sorted(existing.items()) if stamp >= start.isoformat()]
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=["date", "comex_stock_t", "cochilco_lme_stock_t"])
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    for col in ("comex_stock_t", "cochilco_lme_stock_t"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame.dropna(subset=["date"]).drop_duplicates("date", keep="last").sort_values("date")


def main() -> None:
    comex_price = _fetch_comex_price()
    lme = _fetch_lme_history()
    inventory = _fetch_comex_inventory()

    data = comex_price.merge(lme, on="date", how="outer")
    if not inventory.empty:
        data = data.merge(inventory, on="date", how="outer")
    data = data.sort_values("date")
    data = data[data["date"].dt.date >= _five_year_start()]

    # Westmetall's LME stock series is the primary LME inventory. COCHILCO is
    # retained as a cross-check/fallback on dates where the primary field is absent.
    if "cochilco_lme_stock_t" in data.columns:
        data["lme_stock_t"] = pd.to_numeric(data.get("lme_stock_t"), errors="coerce").combine_first(
            pd.to_numeric(data["cochilco_lme_stock_t"], errors="coerce")
        )
    else:
        data["cochilco_lme_stock_t"] = pd.NA

    counts = {
        "comex_price": int(data.get("comex_price_usd_lb", pd.Series(dtype=float)).notna().sum()),
        "comex_stock": int(data.get("comex_stock_t", pd.Series(dtype=float)).notna().sum()),
        "lme_price": int(data.get("lme_cash_usd_t", pd.Series(dtype=float)).notna().sum()),
        "lme_stock": int(data.get("lme_stock_t", pd.Series(dtype=float)).notna().sum()),
    }
    if counts["comex_price"] < 700 or counts["lme_price"] < 700 or counts["lme_stock"] < 700:
        raise RuntimeError(f"copper snapshot core series too short: {counts}")
    if counts["comex_stock"] < 250:
        raise RuntimeError(f"COMEX inventory series too short: {counts}")

    columns = [
        "date",
        "comex_price_usd_lb",
        "comex_stock_t",
        "lme_cash_usd_t",
        "lme_3m_usd_t",
        "lme_stock_t",
        "cochilco_lme_stock_t",
    ]
    for col in columns:
        if col not in data.columns:
            data[col] = pd.NA

    records = []
    for row in data[columns].itertuples(index=False, name=None):
        item = {"date": row[0].strftime("%Y-%m-%d")}
        for col, value in zip(columns[1:], row[1:]):
            item[col] = None if pd.isna(value) else float(value)
        records.append(item)

    payload = {
        "source": "COMEX HG price via Yahoo chart API; LME copper price/stock via Westmetall LME tables; COMEX/LME inventory cross-check via COCHILCO Table 4.2",
        "source_urls": {
            "comex_price": "https://finance.yahoo.com/quote/HG=F/history/",
            "cme_inventory_reference": "https://www.cmegroup.com/solutions/clearing/operations-and-deliveries/nymex-delivery-notices.html",
            "lme_reference": "https://www.lme.com/copper",
            "lme_price_stock": "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Cu_cash",
            "cochilco_inventory": "https://boletin.cochilco.cl/productos/boletin.asp?tabla=tabla4_2",
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "coverage_start": records[0]["date"],
        "coverage_end": records[-1]["date"],
        "counts": counts,
        "units": {
            "comex_price_usd_lb": "USD/lb",
            "comex_stock_t": "metric tonnes",
            "lme_cash_usd_t": "USD/metric tonne",
            "lme_3m_usd_t": "USD/metric tonne",
            "lme_stock_t": "metric tonnes",
        },
        "records": records,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote copper snapshot", counts, payload["coverage_start"], payload["coverage_end"], flush=True)


if __name__ == "__main__":
    main()
