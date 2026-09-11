from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_snapshots" / "hkma_banking_liquidity_daily.json"

# These official HKMA bulletin endpoints are daily-frequency datasets. GitHub
# Actions probes show that small newest-first pages are fast and reliable,
# while large date-filtered requests can time out or return 502.
MARKET_OP_URL = "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/monetary-operation/market-operation-daily"
BASE_URL = "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/monetary-operation/monetary-base-daily"
HIBOR_URL = "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/er-ir/hk-interbank-ir-daily"

# Optional richer/current endpoints. Failure here must never block the durable
# daily backbone above.
INTERBANK_URL = "https://api.hkma.gov.hk/public/market-data-and-statistics/daily-monetary-statistics/daily-figures-interbank-liquidity"
CURRENT_BASE_URL = "https://api.hkma.gov.hk/public/market-data-and-statistics/daily-monetary-statistics/daily-figures-monetary-base"

PAGE_SIZE = 20
ROLLING_DAYS = 550
MAX_PAGES = 30


def _decode_payload(raw: bytes) -> dict:
    """Decode either native HKMA JSON or the same JSON carried by r.jina.ai."""
    text = raw.decode("utf-8", errors="replace").strip()
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    # r.jina.ai is transport-only. In unusual responses it may prepend a small
    # text wrapper, so recover the first complete-looking JSON object.
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        payload = json.loads(text[start : end + 1])
        if isinstance(payload, dict):
            return payload
    raise RuntimeError("HKMA response was not a JSON object")


def _fetch_bytes(url: str, timeout: int) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; MacroDashboard/1.0; +https://github.com/yingjieli176-art/macro_dashboard)",
            "Accept": "application/json,text/plain,*/*",
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
            "Connection": "close",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def _request(url: str, params: dict[str, str], *, timeout: int = 12, attempts: int = 2) -> list[dict]:
    """Fetch HKMA rows with a transport fallback for GitHub-hosted runners.

    The data source remains HKMA in both cases. r.jina.ai is used only as an
    HTTP transport relay because GitHub-hosted runners intermittently time out
    when connecting directly to api.hkma.gov.hk.
    """
    query = urllib.parse.urlencode(params)
    official = f"{url}?{query}"
    proxy = "https://r.jina.ai/http://" + official.removeprefix("https://")
    candidates = ((proxy, max(timeout, 35)), (official, timeout))
    errors: list[str] = []

    for candidate, candidate_timeout in candidates:
        for attempt in range(attempts):
            try:
                payload = _decode_payload(_fetch_bytes(candidate, candidate_timeout))
                header = payload.get("header") or {}
                if header.get("success") is False:
                    raise RuntimeError(header.get("err_msg") or "HKMA API failure")
                rows = (payload.get("result") or {}).get("records") or []
                if not isinstance(rows, list):
                    raise RuntimeError("HKMA result.records is not a list")
                return rows
            except Exception as exc:
                errors.append(f"{candidate.split('?')[0]} attempt {attempt + 1}: {type(exc).__name__}: {exc}")
                if attempt < attempts - 1:
                    time.sleep(1.0)

    raise RuntimeError("HKMA request failed: " + " | ".join(errors[-6:]))


def _fetch_recent_pages(
    url: str,
    date_field: str,
    start_day: date,
    extra: dict[str, str] | None = None,
) -> list[dict]:
    """Fetch a rolling daily buffer using only small offset pages.

    Do not add choose/from/to or fields here. Those query shapes were the source
    of repeated timeout/502 failures from GitHub-hosted runners, while a live
    probe confirmed pagesize=20 newest-first calls complete in about one second.
    """
    rows: list[dict] = []
    for page in range(MAX_PAGES):
        offset = page * PAGE_SIZE
        params = {
            "pagesize": str(PAGE_SIZE),
            "offset": str(offset),
            "sortby": date_field,
            "sortorder": "desc",
        }
        if extra:
            params.update(extra)
        batch = _request(url, params)
        print(url.rsplit("/", 1)[-1], "offset", offset, "rows", len(batch), flush=True)
        if not batch:
            break
        rows.extend(batch)

        dates = []
        for row in batch:
            raw = str(row.get(date_field) or "")
            try:
                dates.append(datetime.strptime(raw, "%Y-%m-%d").date())
            except ValueError:
                continue
        if dates and min(dates) <= start_day:
            break
        if len(batch) < PAGE_SIZE:
            break
    else:
        raise RuntimeError(f"HKMA pagination exceeded safety limit for {url}")

    deduped: dict[str, dict] = {}
    for row in rows:
        key = str(row.get(date_field) or "")
        try:
            day = datetime.strptime(key, "%Y-%m-%d").date()
        except ValueError:
            continue
        if day >= start_day:
            deduped[key] = row
    return [deduped[key] for key in sorted(deduped)]


def _optional_latest(url: str, date_field: str, extra: dict[str, str] | None = None) -> list[dict]:
    params = {
        "pagesize": "20",
        "offset": "0",
        "sortby": date_field,
        "sortorder": "desc",
    }
    if extra:
        params.update(extra)
    try:
        rows = _request(url, params, timeout=8, attempts=1)
        print("optional", url.rsplit("/", 1)[-1], "rows", len(rows), flush=True)
        return rows
    except Exception as exc:
        print("optional endpoint unavailable:", url.rsplit("/", 1)[-1], repr(exc), flush=True)
        return []


def main() -> None:
    end_day = datetime.now(timezone.utc).date()
    start_day = end_day - timedelta(days=ROLLING_DAYS)

    market_ops = _fetch_recent_pages(MARKET_OP_URL, "end_of_day", start_day)
    monetary_base = _fetch_recent_pages(BASE_URL, "end_of_day", start_day)
    hibor = _fetch_recent_pages(
        HIBOR_URL,
        "end_of_day",
        start_day,
        {"segment": "hibor.fixing"},
    )

    # Best-effort latest enrichment. These add opening balance, T+1 forecast,
    # current Aggregate Balance and Base Rate when the newer daily-statistics
    # service is reachable, but are never required for snapshot publication.
    current_base = _optional_latest(CURRENT_BASE_URL, "end_of_date")
    interbank = _optional_latest(INTERBANK_URL, "end_of_date")

    merged: dict[str, dict] = {}

    def target_for(key: str) -> dict:
        return merged.setdefault(
            key,
            {
                "end_of_date": key,
                "opening_balance": None,
                "closing_balance": None,
                "forecast_aggregate_bal_t1": None,
                "outstanding_efbn": None,
                "ow_lb_bf_disc_win": None,
                "aggr_balance_bf_disc_win": None,
                "hibor_overnight": None,
                "hibor_3m": None,
                "disc_win_base_rate": None,
                "cu_weakside": None,
                "cu_strongside": None,
            },
        )

    for row in market_ops:
        key = str(row.get("end_of_day") or "")
        if len(key) == 10:
            target = target_for(key)
            if row.get("closing_balance") is not None:
                target["closing_balance"] = row.get("closing_balance")

    for row in monetary_base:
        key = str(row.get("end_of_day") or "")
        if len(key) == 10:
            target = target_for(key)
            for field in ("outstanding_efbn", "ow_lb_bf_disc_win", "aggr_balance_bf_disc_win"):
                if row.get(field) is not None:
                    target[field] = row.get(field)
            if target.get("closing_balance") is None and row.get("aggr_balance_bf_disc_win") is not None:
                target["closing_balance"] = row.get("aggr_balance_bf_disc_win")

    for row in hibor:
        key = str(row.get("end_of_day") or "")
        if len(key) == 10:
            target = target_for(key)
            if row.get("ir_overnight") is not None:
                target["hibor_overnight"] = row.get("ir_overnight")
            if row.get("ir_3m") is not None:
                target["hibor_3m"] = row.get("ir_3m")

    for row in current_base:
        key = str(row.get("end_of_date") or "")
        if len(key) == 10:
            target = target_for(key)
            for field in ("outstanding_efbn", "ow_lb_bf_disc_win", "aggr_balance_bf_disc_win"):
                if row.get(field) is not None:
                    target[field] = row.get(field)
            if row.get("aggr_balance_bf_disc_win") is not None:
                target["closing_balance"] = row.get("aggr_balance_bf_disc_win")

    for row in interbank:
        key = str(row.get("end_of_date") or "")
        if len(key) == 10:
            target = target_for(key)
            for field in (
                "opening_balance",
                "closing_balance",
                "forecast_aggregate_bal_t1",
                "disc_win_base_rate",
                "cu_weakside",
                "cu_strongside",
                "hibor_overnight",
            ):
                if row.get(field) is not None:
                    target[field] = row.get(field)

    records = [merged[key] for key in sorted(merged)]
    funding_rows = [r for r in records if r.get("hibor_overnight") is not None and r.get("hibor_3m") is not None]
    balance_rows = [r for r in records if r.get("closing_balance") is not None]
    if len(records) < 200 or len(funding_rows) < 200 or len(balance_rows) < 200:
        raise RuntimeError(
            f"daily snapshot incomplete: records={len(records)}, funding={len(funding_rows)}, balance={len(balance_rows)}"
        )

    payload = {
        "source": "HKMA official daily bulletin datasets; current daily-statistics enrichment when available",
        "source_urls": [MARKET_OP_URL, BASE_URL, HIBOR_URL, CURRENT_BASE_URL, INTERBANK_URL],
        "transport_fallback": "r.jina.ai relay when direct api.hkma.gov.hk access is unavailable from CI",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "coverage_start": records[0]["end_of_date"],
        "coverage_end": records[-1]["end_of_date"],
        "record_count": len(records),
        "fetch_strategy": "small newest-first pagesize=20 offset pagination; no date-filter query; proxy/direct transport fallback; optional current enrichment",
        "records": records,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", len(records), "daily rows", payload["coverage_start"], payload["coverage_end"], flush=True)


if __name__ == "__main__":
    main()
