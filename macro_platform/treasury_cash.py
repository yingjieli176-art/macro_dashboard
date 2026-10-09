"""Canonical U.S. Treasury DTS TGA closing balance interpretation.

Beginning 2022-04-18, Treasury's 'Treasury General Account (TGA)
Closing Balance' row is a *closing balance label* whose published balance
appears in open_today_bal. In that one row, the field label does NOT mean
the opening TGA cash balance. Do not generalize this exception to ordinary
opening-balance rows. Preserve true dates and never fill missing days.
"""
from __future__ import annotations

import pandas as pd

TGA_CLOSING_LABEL = "treasury general account"
UNIT_USD_MILLIONS_TO_TRILLIONS = 1_000_000.0


def parse_dts_tga_rows(rows) -> pd.DataFrame:
    """Select explicitly named TGA closes, with only labeled total fallback.

    Return columns observation_date / TGA_DAILY (USD trillions); date-based
    deduplication chooses an explicit closing row over Total Operating Balance.
    """
    columns = ["observation_date", "TGA_DAILY"]
    frame = pd.DataFrame(rows or [])
    if frame.empty or not {"record_date", "account_type"} <= set(frame):
        return pd.DataFrame(columns=columns)
    frame["observation_date"] = pd.to_datetime(
        frame["record_date"], errors="coerce"
    ).dt.tz_localize(None)
    frame["account_label"] = frame["account_type"].fillna("").astype(str).str.lower()
    for key in ("close_today_bal", "open_today_bal"):
        frame[key] = pd.to_numeric(frame.get(key), errors="coerce")
    is_tga = frame["account_label"].str.contains(TGA_CLOSING_LABEL, regex=False)
    is_closing = frame["account_label"].str.contains("closing", regex=False)
    is_total = frame["account_label"].str.contains("total operating balance", regex=False)

    # Explicit TGA closing-balance ROW: after Apr 2022 the value resides
    # in open_today_bal. Otherwise use close_today_bal where published.
    # The total-operating-balance fallback may use ONLY close_today_bal.
    frame["_value"] = frame["close_today_bal"].where(
        ~is_tga | ~is_closing,
        frame["close_today_bal"].combine_first(frame["open_today_bal"]),
    )
    frame.loc[~(is_tga & is_closing), "_value"] = frame.loc[
        ~(is_tga & is_closing), "close_today_bal"
    ]
    frame["_priority"] = 9
    frame.loc[is_tga & is_closing, "_priority"] = 0
    frame.loc[is_total, "_priority"] = 1
    frame.loc[is_tga & ~is_closing, "_priority"] = 2

    selected = frame.loc[
        (frame["_priority"] < 9) &
        frame["observation_date"].notna() &
        (frame["_value"] > 0) &
        (frame["observation_date"] <= pd.Timestamp.now().normalize() + pd.Timedelta(days=1))
    ].copy()
    if selected.empty:
        return pd.DataFrame(columns=columns)
    selected = (selected.sort_values(["observation_date", "_priority"])
                .drop_duplicates("observation_date", keep="first")
                .sort_values("observation_date"))
    selected["TGA_DAILY"] = selected["_value"] / UNIT_USD_MILLIONS_TO_TRILLIONS
    result = selected[columns].reset_index(drop=True)
    result.attrs.update({
        "source": "U.S. Treasury Daily Treasury Statement / TGA Closing Balance",
        "frequency": "daily",
        "is_fallback": False,
        "total_operating_fallback_dates": int((selected["_priority"] == 1).sum()),
        "post_2022_closing_row_compatible": True,
    })
    return result
