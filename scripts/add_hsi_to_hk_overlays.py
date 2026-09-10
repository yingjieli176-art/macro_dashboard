from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HK = ROOT / "macro_platform" / "hk_liquidity.py"
APP = ROOT / "app.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def patch_hk() -> None:
    text = HK.read_text(encoding="utf-8")

    if 'hsi_index = _market_monthly_close("^HSI", "HSI Index")' not in text:
        text = replace_once(
            text,
            '    hstech_index = _market_monthly_close("HSTECH.HK", "HSTECH Index")\n'
            '    market_data = pd.DataFrame(columns=["observation_date"])\n'
            '    for frame in (hkex_price, hstech_index):\n',
            '    hstech_index = _market_monthly_close("HSTECH.HK", "HSTECH Index")\n'
            '    hsi_index = _market_monthly_close("^HSI", "HSI Index")\n'
            '    market_data = pd.DataFrame(columns=["observation_date"])\n'
            '    for frame in (hkex_price, hstech_index, hsi_index):\n',
            "market data HSI source",
        )

    money_anchor = '    add_line(money, market_data, "HSTECH Index", "HSTECH Index (R)", "#db2777", 2.1, "dash", unit=" pts", secondary_y=True)\n'
    money_hsi = '    add_line(money, market_data, "HSI Index", "HSI Index (R)", "#d97706", 2.0, "dot", unit=" pts", secondary_y=True)\n'
    if money_hsi not in text:
        text = replace_once(text, money_anchor, money_anchor + money_hsi, "Chart 5 HSI trace")

    fx_anchor = '    add_line(fx, market_data, "HSTECH Index", "HSTECH Index (R)", "#db2777", 2.1, "dash", unit=" pts", secondary_y=True)\n'
    fx_hsi = '    add_line(fx, market_data, "HSI Index", "HSI Index (R)", "#d97706", 2.0, "dot", unit=" pts", secondary_y=True)\n'
    if fx_hsi not in text:
        text = replace_once(text, fx_anchor, fx_anchor + fx_hsi, "Chart 8 HSI trace")

    HK.write_text(text, encoding="utf-8")


def patch_app() -> None:
    text = APP.read_text(encoding="utf-8")

    old5 = '<br>5. HSTECH Index（R）：恒生科技指数 HSTECH.HK 月末指数点位，右轴单位 points；市场历史独立拉取 5Y，不再被 HKMA 月度快照长度裁断。'
    new5 = old5 + '<br>6. HSI Index（R）：恒生指数月末指数点位，右轴单位 points；使用 ^HSI 的 5Y 市场历史，用于对照香港大盘与流动性变化。'
    if new5 not in text:
        text = replace_once(text, old5, new5, "Chart 5 HSI description")

    old8 = '<br>6. HSTECH Index（R）：恒生科技指数 HSTECH.HK 月末指数点位，右轴单位 points。'
    new8 = old8 + '<br>7. HSI Index（R）：恒生指数月末指数点位，右轴单位 points。'
    if new8 not in text:
        text = replace_once(text, old8, new8, "Chart 8 HSI description")

    text = text.replace(
        'HKD M2 / M3 / Monetary Base MoM · HKEX Price (R) · HSTECH Index (R)',
        'HKD M2 / M3 / Monetary Base MoM · HKEX Price (R) · HSTECH Index (R) · HSI Index (R)',
        1,
    )
    text = text.replace(
        'USD/HKD · Strong-side 7.75 · Center 7.80 · Weak-side 7.85 · HKEX / HSTECH (R)',
        'USD/HKD · Strong-side 7.75 · Center 7.80 · Weak-side 7.85 · HKEX / HSTECH / HSI (R)',
        1,
    )

    # Add the official Hang Seng Index page next to the existing HSTECH source in both charts.
    hstech_source = '("Hang Seng Indexes · HSTECH", "https://www.hsi.com.hk/eng/indexes/all-indexes/hstech"),\n'
    hsi_source = '                ("Hang Seng Indexes · HSI", "https://www.hsi.com.hk/eng/indexes/all-indexes/hsi"),\n'
    if text.count('("Hang Seng Indexes · HSI",') < 2:
        first = text.find(hstech_source)
        if first == -1:
            raise RuntimeError("HSI source: HSTECH source anchor not found")
        insert_at = first + len(hstech_source)
        text = text[:insert_at] + hsi_source + text[insert_at:]
        second = text.find(hstech_source, insert_at + len(hsi_source))
        if second == -1:
            raise RuntimeError("HSI source: second HSTECH source anchor not found")
        insert_at2 = second + len(hstech_source)
        text = text[:insert_at2] + hsi_source + text[insert_at2:]

    APP.write_text(text, encoding="utf-8")


def main() -> None:
    patch_hk()
    patch_app()
    print("added HSI to Charts 5 and 8")


if __name__ == "__main__":
    main()
