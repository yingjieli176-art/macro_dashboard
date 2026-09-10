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

    old_fallback = '''        fallback = monthly[["observation_date", "Aggregate Balance"]].dropna().copy()
        fallback = fallback.rename(columns={"Aggregate Balance": "Closing Aggregate Balance"})
        fallback["Opening Aggregate Balance"] = fallback["Closing Aggregate Balance"]
        fallback["Forecast Aggregate Balance T+1"] = fallback["Closing Aggregate Balance"]
        fallback["Outstanding EFBN"] = pd.NA
        fallback["EFBN Held by Licensed Banks"] = pd.NA
        return fallback[DAILY_BANKING_COLUMNS]'''
    new_fallback = '''        fallback = monthly[[
            "observation_date",
            "Aggregate Balance",
            "Outstanding EFBN",
            "EFBN Held by Licensed Banks",
        ]].copy()
        fallback = fallback.rename(columns={"Aggregate Balance": "Closing Aggregate Balance"})
        # Monthly history has no daily opening balance or T+1 forecast. Leave those
        # fields empty instead of fabricating them from the closing balance.
        fallback["Opening Aggregate Balance"] = pd.NA
        fallback["Forecast Aggregate Balance T+1"] = pd.NA
        value_cols = [
            "Closing Aggregate Balance",
            "Outstanding EFBN",
            "EFBN Held by Licensed Banks",
        ]
        fallback = fallback.dropna(how="all", subset=value_cols)
        return fallback[DAILY_BANKING_COLUMNS]'''
    text = replace_once(text, old_fallback, new_fallback, "banking monthly fallback")

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
