from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HK = ROOT / "macro_platform" / "hk_liquidity.py"
text = HK.read_text(encoding="utf-8")

# 1) Exact HSTECH local snapshot path.
anchor = 'DAILY_BANKING_SNAPSHOT_PATH = ROOT / "data_snapshots" / "hkma_banking_liquidity_daily.json"\n'
insert = anchor + 'HSTECH_SNAPSHOT_PATH = ROOT / "data_snapshots" / "hstech_monthly.json"\n'
if 'HSTECH_SNAPSHOT_PATH' not in text:
    if anchor not in text:
        raise RuntimeError('daily snapshot path anchor missing')
    text = text.replace(anchor, insert, 1)

# 2) Daily funding loader with honest monthly fallback.
funding_marker = '\n\ndef snapshot_metadata() -> dict[str, Any]:\n'
if 'def load_hk_funding_daily()' not in text:
    funding_loader = '''\n\ndef load_hk_funding_daily() -> pd.DataFrame:
    """Load O/N HIBOR, 3M HIBOR and Base Rate from the daily HKMA snapshot.

    If the daily snapshot is unavailable, use the monthly official series. The
    chart title separately labels this as a monthly fallback so freshness is
    never overstated.
    """
    columns = ["observation_date", "HIBOR O/N", "HIBOR 3M", "HKMA Base Rate", "O/N-3M Spread"]
    try:
        payload = json.loads(DAILY_BANKING_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        rows = payload.get("records") if isinstance(payload, dict) else payload
        frame = pd.DataFrame(rows or [])
    except Exception:
        frame = pd.DataFrame()
    if not frame.empty and "end_of_date" in frame.columns:
        frame["observation_date"] = pd.to_datetime(frame["end_of_date"], errors="coerce")
        frame["HIBOR O/N"] = pd.to_numeric(frame.get("hibor_overnight"), errors="coerce")
        frame["HIBOR 3M"] = pd.to_numeric(frame.get("hibor_3m"), errors="coerce")
        frame["HKMA Base Rate"] = pd.to_numeric(frame.get("disc_win_base_rate"), errors="coerce")
        frame["O/N-3M Spread"] = (frame["HIBOR O/N"] - frame["HIBOR 3M"]) * 100.0
        frame = frame.dropna(subset=["observation_date"]).sort_values("observation_date").drop_duplicates("observation_date", keep="last")
        if frame[["HIBOR O/N", "HIBOR 3M", "HKMA Base Rate"]].notna().any(axis=1).sum() >= 10:
            return frame[columns]
    monthly = load_hk_liquidity()
    if monthly.empty:
        return pd.DataFrame(columns=columns)
    return monthly[columns].copy()


def _daily_snapshot_available() -> bool:
    try:
        payload = json.loads(DAILY_BANKING_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        rows = payload.get("records") if isinstance(payload, dict) else payload
        return isinstance(rows, list) and len(rows) >= 10
    except Exception:
        return False
'''
    if funding_marker not in text:
        raise RuntimeError('snapshot metadata marker missing')
    text = text.replace(funding_marker, funding_loader + funding_marker, 1)

# 3) HSTECH snapshot reader before remote market-history requests.
market_marker = '\n\ndef _market_monthly_close(symbol: str, label: str) -> pd.DataFrame:\n'
if 'def _hstech_snapshot_monthly(' not in text:
    helper = '''\n\ndef _hstech_snapshot_monthly(label: str) -> pd.DataFrame:
    try:
        payload = json.loads(HSTECH_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        rows = payload.get("records") if isinstance(payload, dict) else payload
        frame = pd.DataFrame(rows or [])
    except Exception:
        return pd.DataFrame(columns=["observation_date", label])
    if frame.empty or "observation_date" not in frame.columns or "close" not in frame.columns:
        return pd.DataFrame(columns=["observation_date", label])
    frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
    frame[label] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["observation_date", label]).sort_values("observation_date")
    return frame[["observation_date", label]].drop_duplicates("observation_date", keep="last")
'''
    if market_marker not in text:
        raise RuntimeError('market history marker missing')
    text = text.replace(market_marker, helper + market_marker, 1)

signature = 'def _market_monthly_close(symbol: str, label: str) -> pd.DataFrame:\n'
if 'snapshot = _hstech_snapshot_monthly(label)' not in text:
    replacement = signature + '''    if str(symbol).upper() in {"HSTECH.HK", "^HSTECH", "HSTECH"}:
        snapshot = _hstech_snapshot_monthly(label)
        if len(snapshot) >= 48:
            return snapshot
'''
    if signature not in text:
        raise RuntimeError('market signature missing')
    text = text.replace(signature, replacement, 1)

# 4) Use daily funding data in 5-3, not monthly HIBOR when a daily snapshot exists.
line = '    banking_data = _slice_range(load_hk_banking_liquidity_daily(), date_range)\n'
if 'funding_data = _slice_range(load_hk_funding_daily(), date_range)' not in text:
    if line not in text:
        raise RuntimeError('banking data line missing')
    text = text.replace(line, line + '    funding_data = _slice_range(load_hk_funding_daily(), date_range)\n', 1)

for old, new in [
    ('add_line(funding, data, "HIBOR O/N"', 'add_line(funding, funding_data, "HIBOR O/N"'),
    ('add_line(funding, data, "HIBOR 3M"', 'add_line(funding, funding_data, "HIBOR 3M"'),
    ('add_line(funding, data, "HKMA Base Rate"', 'add_line(funding, funding_data, "HKMA Base Rate"'),
    ('add_line(funding, data, "O/N-3M Spread"', 'add_line(funding, funding_data, "O/N-3M Spread"'),
]:
    text = text.replace(old, new)

# 5) Honest titles when the daily snapshot is not yet present.
old_style_balance = '    style(balance, "5-2. Daily Banking-system Liquidity", height=450, right_axis=True)\n'
new_style_balance = '    style(balance, "5-2. Daily Banking-system Liquidity" if _daily_snapshot_available() else "5-2. Banking-system Liquidity · monthly fallback", height=450, right_axis=True)\n'
if old_style_balance in text:
    text = text.replace(old_style_balance, new_style_balance, 1)

old_balance_title = '        balance.update_layout(title_text=f"5-2. Daily Banking-system Liquidity · latest {banking_latest}")\n'
new_balance_title = '        balance_label = "5-2. Daily Banking-system Liquidity" if _daily_snapshot_available() else "5-2. Banking-system Liquidity · monthly fallback"\n        balance.update_layout(title_text=f"{balance_label} · latest {banking_latest}")\n'
if old_balance_title in text:
    text = text.replace(old_balance_title, new_balance_title, 1)

old_funding_style = '    style(funding, "5-3. HKD Funding", right_axis=True)\n'
new_funding_style = '''    style(funding, "5-3. HKD Funding · Daily" if _daily_snapshot_available() else "5-3. HKD Funding · monthly fallback", right_axis=True)
    if not funding_data.empty:
        funding_latest = funding_data["observation_date"].max().strftime("%Y-%m-%d" if _daily_snapshot_available() else "%Y-%m")
        funding_label = "5-3. HKD Funding · Daily" if _daily_snapshot_available() else "5-3. HKD Funding · monthly fallback"
        funding.update_layout(title_text=f"{funding_label} · latest {funding_latest}")
'''
if old_funding_style in text:
    text = text.replace(old_funding_style, new_funding_style, 1)

HK.write_text(text, encoding='utf-8')
print('wired exact HSTECH snapshot and freshness-aware HK funding charts')
