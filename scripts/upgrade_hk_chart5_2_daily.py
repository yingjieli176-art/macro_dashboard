from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HK = ROOT / "macro_platform" / "hk_liquidity.py"
APP = ROOT / "app.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        if new in text:
            return text
        raise RuntimeError(f"pattern not found for {label}")
    return text.replace(old, new, 1)


def patch_hk() -> None:
    text = HK.read_text(encoding="utf-8")

    if "DAILY_BANKING_SNAPSHOT_PATH" not in text:
        text = replace_once(
            text,
            'SNAPSHOT_PATH = ROOT / "data_snapshots" / "hkma_monetary_statistics.json"\n',
            'SNAPSHOT_PATH = ROOT / "data_snapshots" / "hkma_monetary_statistics.json"\n'
            'DAILY_BANKING_SNAPSHOT_PATH = ROOT / "data_snapshots" / "hkma_banking_liquidity_daily.json"\n'
            'DAILY_BANKING_COLUMNS = [\n'
            '    "observation_date",\n'
            '    "Opening Aggregate Balance",\n'
            '    "Closing Aggregate Balance",\n'
            '    "Forecast Aggregate Balance T+1",\n'
            '    "Outstanding EFBN",\n'
            '    "EFBN Held by Licensed Banks",\n'
            ']\n',
            "daily snapshot constants",
        )

    if "def load_hk_banking_liquidity_daily" not in text:
        loader = r'''

def load_hk_banking_liquidity_daily() -> pd.DataFrame:
    """Load daily HK banking-system liquidity from the repository snapshot.

    Values are converted from HK$ million to HK$ billion. If the daily snapshot
    is unavailable, fall back to the monthly Aggregate Balance so Chart 5-2
    remains usable instead of failing the entire Hong Kong liquidity section.
    """
    try:
        payload = json.loads(DAILY_BANKING_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        rows = payload.get("records") if isinstance(payload, dict) else payload
        frame = pd.DataFrame(rows or [])
    except Exception:
        frame = pd.DataFrame()

    if frame.empty or "end_of_date" not in frame.columns:
        monthly = load_hk_liquidity()
        if monthly.empty:
            return pd.DataFrame(columns=DAILY_BANKING_COLUMNS)
        fallback = monthly[["observation_date", "Aggregate Balance"]].dropna().copy()
        fallback = fallback.rename(columns={"Aggregate Balance": "Closing Aggregate Balance"})
        fallback["Opening Aggregate Balance"] = fallback["Closing Aggregate Balance"]
        fallback["Forecast Aggregate Balance T+1"] = fallback["Closing Aggregate Balance"]
        fallback["Outstanding EFBN"] = pd.NA
        fallback["EFBN Held by Licensed Banks"] = pd.NA
        return fallback[DAILY_BANKING_COLUMNS]

    frame["observation_date"] = pd.to_datetime(frame["end_of_date"], errors="coerce")
    mapping = {
        "opening_balance": "Opening Aggregate Balance",
        "closing_balance": "Closing Aggregate Balance",
        "forecast_aggregate_bal_t1": "Forecast Aggregate Balance T+1",
        "outstanding_efbn": "Outstanding EFBN",
        "ow_lb_bf_disc_win": "EFBN Held by Licensed Banks",
    }
    for source, target in mapping.items():
        frame[target] = pd.to_numeric(frame.get(source), errors="coerce") / 1000.0
    frame = (
        frame.dropna(subset=["observation_date"])
        .sort_values("observation_date")
        .drop_duplicates("observation_date", keep="last")
    )
    return frame[DAILY_BANKING_COLUMNS]
'''
        text = replace_once(text, "\ndef snapshot_metadata() -> dict[str, Any]:\n", loader + "\n\ndef snapshot_metadata() -> dict[str, Any]:\n", "daily loader")

    text = replace_once(
        text,
        "    data = _slice_range(all_data, date_range)\n    meta = snapshot_metadata()\n",
        "    data = _slice_range(all_data, date_range)\n    banking_data = _slice_range(load_hk_banking_liquidity_daily(), date_range)\n    meta = snapshot_metadata()\n",
        "banking data slice",
    )

    old_balance = '''    # 5-2 · Banking-system liquidity.\n    balance = go.Figure()\n    add_line(balance, data, "Aggregate Balance", "Aggregate Balance", COLORS["balance"], 2.8, unit=" HK$ bn")\n    balance.update_yaxes(\n        title_text="HK$ bn", showgrid=True, gridcolor="#e5e7eb", griddash="dot",\n        zeroline=False, fixedrange=True,\n    )\n    style(balance, "5-2. Banking-system Liquidity")\n'''
    new_balance = '''    # 5-2 · Daily banking-system liquidity and monetary-base structure.\n    balance = make_subplots(specs=[[{"secondary_y": True}]])\n    add_line(balance, banking_data, "Opening Aggregate Balance", "Opening Aggregate Balance", "#64748b", 1.7, "dot", unit=" HK$ bn", secondary_y=False)\n    add_line(balance, banking_data, "Closing Aggregate Balance", "Closing Aggregate Balance", COLORS["balance"], 2.9, unit=" HK$ bn", secondary_y=False)\n    add_line(balance, banking_data, "Forecast Aggregate Balance T+1", "Forecast Aggregate Balance T+1", "#0284c7", 2.0, "dash", unit=" HK$ bn", secondary_y=False)\n    add_line(balance, banking_data, "Outstanding EFBN", "Outstanding EFBN (R)", "#7c3aed", 2.0, unit=" HK$ bn", secondary_y=True)\n    add_line(balance, banking_data, "EFBN Held by Licensed Banks", "EFBN Held by Licensed Banks (R)", "#c026d3", 1.8, "dash", unit=" HK$ bn", secondary_y=True)\n    balance.update_yaxes(\n        title_text="Aggregate Balance (HK$ bn)", secondary_y=False,\n        showgrid=True, gridcolor="#e5e7eb", griddash="dot",\n        zeroline=False, fixedrange=True,\n    )\n    balance.update_yaxes(\n        title_text="EFBN (HK$ bn)", secondary_y=True,\n        showgrid=False, zeroline=False, fixedrange=True,\n    )\n    style(balance, "5-2. Daily Banking-system Liquidity", height=450, right_axis=True)\n    if not banking_data.empty:\n        banking_latest = banking_data["observation_date"].max().strftime("%Y-%m-%d")\n        balance.update_layout(title_text=f"5-2. Daily Banking-system Liquidity · latest {banking_latest}")\n'''
    text = replace_once(text, old_balance, new_balance, "5-2 daily chart")

    HK.write_text(text, encoding="utf-8")


def patch_app() -> None:
    text = APP.read_text(encoding="utf-8")

    start = text.index("def apply_hk_chart_range(fig, date_range):")
    end = text.index("def build_fig1(date_range):", start)
    new_range = '''def apply_hk_chart_range(fig, date_range):\n    """Apply an independent viewport using the newest observation in that figure."""\n    latest_candidates = []\n    for trace in fig.data:\n        values = getattr(trace, "x", None)\n        if values is None:\n            continue\n        parsed = pd.to_datetime(list(values), errors="coerce")\n        parsed = parsed[~pd.isna(parsed)]\n        if len(parsed):\n            latest_candidates.append(parsed.max())\n    if not latest_candidates:\n        return fig\n    latest = max(latest_candidates)\n    offsets = {\n        "5Y": pd.DateOffset(years=5),\n        "1Y": pd.DateOffset(years=1),\n        "6M": pd.DateOffset(months=6),\n        "3M": pd.DateOffset(months=3),\n        "1M": pd.DateOffset(months=1),\n    }\n    start = latest - offsets.get(date_range, offsets["1Y"])\n    fig.update_xaxes(range=[start, latest])\n    return fig\n\n'''
    text = text[:start] + new_range + text[end:]

    pattern = re.compile(r"    '<b>参数概念：</b><br>1\. Aggregate Balance：[^\n]*',\n")
    replacement = (
        "    '<b>参数概念：</b><br>1. Opening Aggregate Balance：每日开市银行体系总结余，单位 HK$ billion。<br>"
        "2. Closing Aggregate Balance：每日收市银行体系总结余，是观察即时港元银行体系流动性的核心指标。<br>"
        "3. Forecast Aggregate Balance T+1：HKMA 公布的下一交易日预计总结余，用于提前观察已知外汇交易、市场操作及贴现窗逆转后的流动性变化。<br>"
        "4. Outstanding EFBN（R）：外汇基金票据及债券未偿还总额，右轴单位 HK$ billion；EFBN 是香港货币基础的重要组成部分。<br>"
        "5. EFBN Held by Licensed Banks（R）：其中由持牌银行持有的 EFBN，右轴单位 HK$ billion，用于观察银行体系持有的高流动性港元资产规模。<br><br>"
        "<b>读取提示：</b>5-2 改为 HKMA 每日数据；Opening 与 Closing 的差异反映当日总结余变化，Forecast T+1 提供前瞻信息，EFBN 两条线用于观察货币基础结构。',\n"
    )
    text, count = pattern.subn(replacement, text, count=1)
    if count != 1 and "Opening Aggregate Balance：每日开市" not in text:
        raise RuntimeError("5-2 parameter description pattern not found")

    text = text.replace(
        "Money supply / HKEX price & HSTECH index / Aggregate Balance / HIBOR / USD-HKD / 7.75–7.85 LERS band",
        "Money supply / HKEX price & HSTECH index / Daily banking liquidity & EFBN / HIBOR / USD-HKD / 7.75–7.85 LERS band",
        1,
    )

    if "HKMA Daily Interbank Liquidity" not in text:
        marker = '        ("HKMA Monetary Statistics", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/financial/monetary-statistics/"),\n'
        addition = marker + '        ("HKMA Daily Interbank Liquidity", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/daily-monetary-statistics/daily-figures-interbank-liquidity/"),\n        ("HKMA Daily Monetary Base", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/daily-monetary-statistics/daily-figures-monetary-base/"),\n'
        text = replace_once(text, marker, addition, "daily sources")

    APP.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_hk()
    patch_app()
    print("upgraded Chart 5-2 to daily banking-system liquidity")
