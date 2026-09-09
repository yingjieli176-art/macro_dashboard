from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import akshare as ak
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_snapshots" / "hstech_monthly.json"


def main() -> None:
    daily = ak.stock_hk_index_daily_sina(symbol="HSTECH").copy()
    if daily.empty or "date" not in daily.columns or "close" not in daily.columns:
        raise RuntimeError("Sina HSTECH history returned no usable data")
    daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
    daily["close"] = pd.to_numeric(daily["close"], errors="coerce")
    daily = daily.dropna(subset=["date", "close"]).sort_values("date")
    cutoff = pd.Timestamp.now().normalize() - pd.DateOffset(years=5, months=2)
    daily = daily[daily["date"] >= cutoff]
    monthly = (
        daily.set_index("date")["close"]
        .resample("MS")
        .last()
        .dropna()
        .rename("close")
        .reset_index()
    )
    if len(monthly) < 60:
        raise RuntimeError(f"HSTECH snapshot too short: {len(monthly)} months")
    records = [
        {"observation_date": row.date.strftime("%Y-%m-%d"), "close": float(row.close)}
        for row in monthly.itertuples(index=False)
    ]
    payload = {
        "symbol": "HSTECH",
        "name": "Hang Seng TECH Index",
        "source": "Sina Finance Hong Kong Index History",
        "source_page": "https://stock.finance.sina.com.cn/hkstock/quotes/HSTECH.html",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "coverage_start": records[0]["observation_date"],
        "coverage_end": records[-1]["observation_date"],
        "records": records,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "wrote HSTECH monthly snapshot",
        len(records),
        payload["coverage_start"],
        payload["coverage_end"],
        "latest", records[-1],
    )


if __name__ == "__main__":
    main()
