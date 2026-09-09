from pathlib import Path

PATH = Path('macro_platform/hk_liquidity.py')
text = PATH.read_text(encoding='utf-8')

old = 'HSTECH_SNAPSHOT_PATH = ROOT / "data_snapshots" / "hstech_monthly.json"\n'
new = old + 'USDHKD_SNAPSHOT_PATH = ROOT / "data_snapshots" / "usdhkd_daily.json"\n'
if 'USDHKD_SNAPSHOT_PATH' not in text:
    if old not in text:
        raise SystemExit('HSTECH constant anchor missing')
    text = text.replace(old, new, 1)

anchor = '''def _fred_daily_series(series_id: str, label: str) -> pd.DataFrame:\n    """Load a public FRED daily series without requiring an API key."""\n'''
helper = '''def _usdhkd_snapshot_daily(label: str) -> pd.DataFrame:\n    """Load repository-persisted USD/HKD daily history.\n\n    The snapshot is refreshed from Yahoo HKD=X by GitHub Actions so the chart\n    does not depend on a live FRED request during a Streamlit page render.\n    """\n    try:\n        payload = json.loads(USDHKD_SNAPSHOT_PATH.read_text(encoding="utf-8"))\n        rows = payload.get("records") if isinstance(payload, dict) else payload\n        frame = pd.DataFrame(rows or [])\n    except Exception:\n        return pd.DataFrame(columns=["observation_date", label])\n    if frame.empty or "observation_date" not in frame.columns or "value" not in frame.columns:\n        return pd.DataFrame(columns=["observation_date", label])\n    frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")\n    frame[label] = pd.to_numeric(frame["value"], errors="coerce")\n    frame = (\n        frame.dropna(subset=["observation_date", label])\n        .sort_values("observation_date")\n        .drop_duplicates("observation_date", keep="last")\n    )\n    return frame[["observation_date", label]]\n\n\ndef _fred_daily_series(series_id: str, label: str) -> pd.DataFrame:\n    """Load a daily series, preferring a repository snapshot for USD/HKD."""\n    if series_id == "DEXHKUS":\n        snapshot = _usdhkd_snapshot_daily(label)\n        if len(snapshot) >= 1000:\n            cutoff = snapshot["observation_date"].max() - pd.DateOffset(years=5)\n            return snapshot.loc[snapshot["observation_date"] >= cutoff].copy()\n'''
if '_usdhkd_snapshot_daily' not in text:
    if anchor not in text:
        raise SystemExit('FRED function anchor missing')
    text = text.replace(anchor, helper, 1)

PATH.write_text(text, encoding='utf-8')
print('wired USDHKD repository snapshot into HK liquidity core')
