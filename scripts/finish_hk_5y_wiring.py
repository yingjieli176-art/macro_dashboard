from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HK = ROOT / "macro_platform" / "hk_liquidity.py"
APP = ROOT / "app.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_hk() -> None:
    text = HK.read_text(encoding="utf-8")

    text = replace_once(
        text,
        'USDHKD_SNAPSHOT_PATH = ROOT / "data_snapshots" / "usdhkd_daily.json"\n',
        'USDHKD_SNAPSHOT_PATH = ROOT / "data_snapshots" / "usdhkd_daily.json"\n'
        'HIBOR_SNAPSHOT_PATH = ROOT / "data_snapshots" / "hkd_hibor_monthly.json"\n'
        'BASE_RATE_SNAPSHOT_PATH = ROOT / "data_snapshots" / "hkma_base_rate_monthly.json"\n',
        "auxiliary snapshot paths",
    )

    text = replace_once(
        text,
        '    "Aggregate Balance",\n    "HIBOR O/N",',
        '    "Aggregate Balance",\n    "Outstanding EFBN",\n    "EFBN Held by Licensed Banks",\n    "HIBOR O/N",',
        "output columns",
    )

    text = replace_once(
        text,
        '        "aggr_balance",\n        "hibor_fixing_overnight",',
        '        "aggr_balance",\n        "ef_bills_notes",\n        "outstanding_efbn",\n        "ow_lb_bf_disc_win",\n        "hibor_fixing_overnight",',
        "numeric source columns",
    )

    text = replace_once(
        text,
        '    monthly["Aggregate Balance"] = monthly["aggr_balance"] / 1000.0\n    monthly["HIBOR O/N"] = monthly["hibor_fixing_overnight"]',
        '    monthly["Aggregate Balance"] = monthly["aggr_balance"] / 1000.0\n'
        '    # Monetary-base structure is stored in HK$ million by HKMA.\n'
        '    # Prefer the dedicated end-period field and fall back to the equivalent\n'
        '    # monetary-statistics EF Bills & Notes field if needed.\n'
        '    monthly["Outstanding EFBN"] = monthly["outstanding_efbn"].combine_first(\n'
        '        monthly["ef_bills_notes"]\n'
        '    ) / 1000.0\n'
        '    monthly["EFBN Held by Licensed Banks"] = monthly["ow_lb_bf_disc_win"] / 1000.0\n'
        '    monthly["HIBOR O/N"] = monthly["hibor_fixing_overnight"]',
        "monthly EFBN derivation",
    )

    banking_helper = '''def load_hk_banking_liquidity_monthly() -> pd.DataFrame:
    """Return real monthly HKMA banking-liquidity history for long windows."""
    monthly = load_hk_liquidity()
    if monthly.empty:
        return pd.DataFrame(columns=DAILY_BANKING_COLUMNS)
    fallback = monthly[[
        "observation_date",
        "Aggregate Balance",
        "Outstanding EFBN",
        "EFBN Held by Licensed Banks",
    ]].copy()
    fallback = fallback.rename(columns={"Aggregate Balance": "Closing Aggregate Balance"})
    # HKMA monthly history does not publish the daily opening balance or T+1
    # forecast. Keep them empty rather than cloning the closing balance.
    fallback["Opening Aggregate Balance"] = pd.NA
    fallback["Forecast Aggregate Balance T+1"] = pd.NA
    value_cols = [
        "Closing Aggregate Balance",
        "Outstanding EFBN",
        "EFBN Held by Licensed Banks",
    ]
    fallback = fallback.dropna(how="all", subset=value_cols)
    return fallback[DAILY_BANKING_COLUMNS]


'''
    text = replace_once(
        text,
        'def load_hk_banking_liquidity_daily() -> pd.DataFrame:\n',
        banking_helper + 'def load_hk_banking_liquidity_daily() -> pd.DataFrame:\n',
        "banking monthly helper",
    )

    old_fallback = '''        monthly = load_hk_liquidity()
        if monthly.empty:
            return pd.DataFrame(columns=DAILY_BANKING_COLUMNS)
        fallback = monthly[["observation_date", "Aggregate Balance"]].dropna().copy()
        fallback = fallback.rename(columns={"Aggregate Balance": "Closing Aggregate Balance"})
        fallback["Opening Aggregate Balance"] = fallback["Closing Aggregate Balance"]
        fallback["Forecast Aggregate Balance T+1"] = fallback["Closing Aggregate Balance"]
        fallback["Outstanding EFBN"] = pd.NA
        fallback["EFBN Held by Licensed Banks"] = pd.NA
        return fallback[DAILY_BANKING_COLUMNS]'''
    text = replace_once(
        text,
        old_fallback,
        '        return load_hk_banking_liquidity_monthly()',
        "banking daily fallback",
    )

    funding_helper = '''def load_hk_funding_monthly() -> pd.DataFrame:
    """Build a continuous monthly HKD funding history from persisted official data.

    O/N and 3M HIBOR come from the C&SD monthly-digest snapshot (underlying
    HKAB/HKMA sources). The HKMA Base Rate comes from the dedicated HKMA
    Discount Window end-of-period snapshot. Recent values in the core HKMA
    monetary snapshot remain a fallback for months not yet present upstream.
    """
    columns = ["observation_date", "HIBOR O/N", "HIBOR 3M", "HKMA Base Rate", "O/N-3M Spread"]
    core = load_hk_liquidity()
    if core.empty:
        funding = pd.DataFrame(columns=columns[:-1]).set_index("observation_date")
    else:
        funding = core[["observation_date", "HIBOR O/N", "HIBOR 3M", "HKMA Base Rate"]].copy()
        funding = funding.set_index("observation_date").sort_index()

    try:
        payload = json.loads(HIBOR_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        rows = payload.get("records") if isinstance(payload, dict) else payload
        hibor = pd.DataFrame(rows or [])
    except Exception:
        hibor = pd.DataFrame()
    if not hibor.empty and "end_of_month" in hibor.columns:
        hibor["observation_date"] = pd.to_datetime(hibor["end_of_month"], format="%Y-%m", errors="coerce")
        hibor["HIBOR O/N"] = pd.to_numeric(hibor.get("hibor_overnight"), errors="coerce")
        hibor["HIBOR 3M"] = pd.to_numeric(hibor.get("hibor_3m"), errors="coerce")
        hibor = hibor.dropna(subset=["observation_date"]).set_index("observation_date")[["HIBOR O/N", "HIBOR 3M"]]
        union = funding.index.union(hibor.index)
        funding = funding.reindex(union)
        for col in ("HIBOR O/N", "HIBOR 3M"):
            funding[col] = hibor[col].reindex(union).combine_first(funding[col])

    try:
        payload = json.loads(BASE_RATE_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        rows = payload.get("records") if isinstance(payload, dict) else payload
        base_rate = pd.DataFrame(rows or [])
    except Exception:
        base_rate = pd.DataFrame()
    if not base_rate.empty and "end_of_month" in base_rate.columns:
        base_rate["observation_date"] = pd.to_datetime(base_rate["end_of_month"], format="%Y-%m", errors="coerce")
        base_rate["HKMA Base Rate"] = pd.to_numeric(base_rate.get("disc_win_base_rate"), errors="coerce")
        base_rate = base_rate.dropna(subset=["observation_date"]).set_index("observation_date")[["HKMA Base Rate"]]
        union = funding.index.union(base_rate.index)
        funding = funding.reindex(union)
        funding["HKMA Base Rate"] = base_rate["HKMA Base Rate"].reindex(union).combine_first(funding["HKMA Base Rate"])

    funding = funding.sort_index()
    funding["O/N-3M Spread"] = (funding["HIBOR O/N"] - funding["HIBOR 3M"]) * 100.0
    funding.index.name = "observation_date"
    return funding.reset_index()[columns]


'''
    text = replace_once(
        text,
        'def load_hk_funding_daily() -> pd.DataFrame:\n',
        funding_helper + 'def load_hk_funding_daily() -> pd.DataFrame:\n',
        "funding monthly helper",
    )

    text = replace_once(
        text,
        '''    monthly = load_hk_liquidity()
    if monthly.empty:
        return pd.DataFrame(columns=columns)
    return monthly[columns].copy()''',
        '    return load_hk_funding_monthly()',
        "funding daily fallback",
    )

    text = replace_once(
        text,
        '''    banking_data = _slice_range(load_hk_banking_liquidity_daily(), date_range)
    funding_data = _slice_range(load_hk_funding_daily(), date_range)''',
        '''    banking_source = load_hk_banking_liquidity_monthly() if date_range == "5Y" else load_hk_banking_liquidity_daily()
    funding_source = load_hk_funding_monthly() if date_range == "5Y" else load_hk_funding_daily()
    banking_data = _slice_range(banking_source, date_range)
    funding_data = _slice_range(funding_source, date_range)''',
        "long-window source selection",
    )

    HK.write_text(text, encoding="utf-8")


def patch_app() -> None:
    text = APP.read_text(encoding="utf-8")
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == "HK_PARAMETER_DESCRIPTIONS = [")
    except StopIteration as exc:
        raise RuntimeError("HK parameter description block not found") from exc

    string_lines: list[int] = []
    i = start + 1
    while i < len(lines) and lines[i].strip() != "]":
        if lines[i].lstrip().startswith("'"):
            string_lines.append(i)
        i += 1
    if len(string_lines) != 4:
        raise RuntimeError(f"expected four HK description strings, found {len(string_lines)}")

    lines[string_lines[1]] = (
        "    '<b>参数概念：</b><br>1. Closing Aggregate Balance：银行体系期末总结余，单位 HK$ billion；5Y 视图使用 HKMA 月度期末历史，数值下降通常代表可用港元流动性收紧。"
        "<br>2. Outstanding EFBN（R）：外汇基金票据及债券未偿还总额，右轴单位 HK$ billion，是香港货币基础的重要结构项。"
        "<br>3. EFBN Held by Licensed Banks（R）：由持牌银行持有的 EFBN，右轴单位 HK$ billion，用于观察银行体系持有的高流动性港元资产规模。"
        "<br><br><b>读取提示：</b>5Y 历史只展示 HKMA 实际公布的月度期末字段，不再用 Closing Aggregate Balance 复制生成 Opening 或 Forecast。若未来日频快照可用，短周期视图仍可显示真实 Opening / Closing / Forecast T+1。',"
    )

    lines[string_lines[2]] = (
        "    '<b>参数概念：</b><br>1. O/N HIBOR：隔夜港元银行同业拆息，5Y 月度历史来自 C&SD 月刊（底层来源 HKAB / HKMA），反映最短端港元资金价格。"
        "<br>2. 3M HIBOR：3 个月港元银行同业拆息，用来观察更持续的港元融资成本。"
        "<br>3. HKMA Base Rate：香港金管局贴现窗基本利率；5Y 历史直接来自 HKMA 月末官方序列。"
        "<br>4. O/N−3M Spread（R）：隔夜 HIBOR 减 3M HIBOR，右轴单位 bp；显著转正通常代表短端资金压力上升。',"
    )

    # Keep the data-source description aligned with the repository-persisted FX path.
    lines[string_lines[3]] = lines[string_lines[3]].replace(
        "USD/HKD 优先使用 FRED DEXHKUS 日频 5Y 历史，HKMA 月度汇率作为回退。",
        "USD/HKD 优先使用仓库持久化的 Yahoo HKD=X 日频 5Y 快照，HKMA 月度汇率作为回退。",
    )

    APP.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    patch_hk()
    patch_app()
    print("patched Hong Kong 5Y chart wiring and parameter descriptions")


if __name__ == "__main__":
    main()
