from __future__ import annotations

from pathlib import Path
import re


APP = Path(__file__).resolve().parents[1] / "app.py"


def main() -> None:
    text = APP.read_text(encoding="utf-8")

    old_import = "get_wresbal, get_wtre_gen, get_tga_daily, get_rrp_daily, _fred_series)"
    new_import = "get_walcl, get_wresbal, get_wtre_gen, get_tga_daily, get_rrp_daily, _fred_series)"
    if old_import not in text and new_import not in text:
        raise RuntimeError("data import anchor not found")
    text = text.replace(old_import, new_import, 1)

    new_fig4 = '''def build_fig4(date_range):
    """US liquidity dashboard in consistent USD-trillion units.

    Net Liquidity uses WALCL - TGA - ON RRP. Reserve balances are displayed as
    a separate banking-liquidity series rather than used as the proxy base.
    """
    # FRED publishes WALCL/WRESBAL in USD millions and RRPONTSYD in USD
    # billions. TGA_DAILY is already normalized to USD trillions by data.py.
    specs = [
        (get_walcl, "WALCL", 1_000_000.0),
        (get_wresbal, "WRESBAL", 1_000_000.0),
        (get_tga_daily, "TGA_DAILY", 1.0),
        (get_rrp_daily, "RRPONTSYD", 1_000.0),
    ]
    raw_series = {}
    tga_is_fallback = False
    for getter, column, divisor in specs:
        try:
            frame = getter().copy()
            if column == "TGA_DAILY":
                tga_is_fallback = bool(frame.attrs.get("is_fallback", False))
            frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
            frame[column] = pd.to_numeric(frame[column], errors="coerce") / divisor
            frame = frame.dropna(subset=["observation_date", column]).sort_values("observation_date")[["observation_date", column]]
            if not frame.empty:
                raw_series[column] = frame
        except Exception:
            continue

    if not raw_series:
        fig = go.Figure()
        for name in ("Net Liquidity Proxy", "Reserve Balances · Weekly", "TGA", "ON RRP · Daily"):
            _mark_missing_series(fig, name)
        return apply_chart_style(fig, chart_height(310, 420), date_range)

    # Forward-fill only inside the mixed-frequency calculation. The displayed
    # component lines retain their actual publication frequency.
    calc = None
    for column in ("WALCL", "TGA_DAILY", "RRPONTSYD"):
        frame = raw_series.get(column)
        if frame is None:
            continue
        calc = frame.copy() if calc is None else calc.merge(frame, on="observation_date", how="outer")
    calc = pd.DataFrame(columns=["observation_date"]) if calc is None else calc.sort_values("observation_date")
    component_cols = [c for c in ("WALCL", "TGA_DAILY", "RRPONTSYD") if c in calc.columns]
    if component_cols:
        calc[component_cols] = calc[component_cols].ffill()
    if all(c in calc.columns for c in ("WALCL", "TGA_DAILY", "RRPONTSYD")):
        calc["NetLiquidity"] = calc["WALCL"] - calc["TGA_DAILY"] - calc["RRPONTSYD"]
    calc = filter_range(calc, date_range)

    fig = go.Figure()
    net_name = "Net Liquidity · WALCL−TGA−ON RRP"
    net_name += " · weekly TGA fallback" if tga_is_fallback else " · mixed frequency"
    add_line(fig, calc, "NetLiquidity", net_name, 3.0, unit=" T")

    observed_names = {
        "WRESBAL": "Reserve Balances · Weekly",
        "TGA_DAILY": "TGA · Weekly fallback" if tga_is_fallback else "TGA · Daily",
        "RRPONTSYD": "ON RRP · Daily",
    }
    dash_map = {"WRESBAL": None, "TGA_DAILY": "dash", "RRPONTSYD": "dot"}
    width_map = {"WRESBAL": 2.3, "TGA_DAILY": 2.1, "RRPONTSYD": 2.1}
    for column in ("WRESBAL", "TGA_DAILY", "RRPONTSYD"):
        frame = raw_series.get(column)
        if frame is None:
            _mark_missing_series(fig, observed_names[column])
            continue
        add_line(fig, filter_range(frame, date_range), column, observed_names[column], width_map[column], dash_map[column], unit=" T")

    # Force human-readable trillion ticks; raw FRED millions must never leak
    # through as Plotly's misleading 1M/2M/3M axis labels.
    fig.update_layout(yaxis_title="USD trillions", yaxis_tickformat=".1f")
    return apply_chart_style(fig, chart_height(310, 420), date_range)
'''

    pattern = r"def build_fig4\(date_range\):\n.*?\n\ndef build_fig3\(date_range\):"
    replacement = new_fig4 + "\n\ndef build_fig3(date_range):"
    text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"build_fig4 replacement count={count}")

    old_desc = "1. Net Liquidity Proxy：Reserve Balances − TGA − ON RRP 的组合指标，用于描述美国金融体系中可观察的流动性变化方向；不是美联储官方指标。该代理为混合频率计算，周频准备金余额只在代理计算内部沿用至下一次公布，不代表每天都有新的准备金观测。"
    new_desc = "1. Net Liquidity Proxy：WALCL（美联储总资产）− TGA − ON RRP 的常用资产负债表流动性代理，单位统一为 USD trillion；不是美联储官方指标。WALCL 为周频，计算时只在代理内部沿用至下一次公布。"
    if old_desc not in text:
        raise RuntimeError("chart-4 description anchor not found")
    text = text.replace(old_desc, new_desc, 1)

    old_sources = '[("Reserve Balances (WRESBAL)", "https://fred.stlouisfed.org/series/WRESBAL"), ("TGA · Daily Treasury Statement", "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/operating-cash-balance"),'
    new_sources = '[("Fed Total Assets (WALCL)", "https://fred.stlouisfed.org/series/WALCL"), ("Reserve Balances (WRESBAL)", "https://fred.stlouisfed.org/series/WRESBAL"), ("TGA · Daily Treasury Statement", "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/operating-cash-balance"),'
    if old_sources not in text:
        raise RuntimeError("chart-4 source anchor not found")
    text = text.replace(old_sources, new_sources, 1)

    APP.write_text(text, encoding="utf-8")

    # Static invariants and representative scale checks.
    required = [
        '(get_walcl, "WALCL", 1_000_000.0)',
        '(get_wresbal, "WRESBAL", 1_000_000.0)',
        '(get_rrp_daily, "RRPONTSYD", 1_000.0)',
        'calc["NetLiquidity"] = calc["WALCL"] - calc["TGA_DAILY"] - calc["RRPONTSYD"]',
        'yaxis_tickformat=".1f"',
    ]
    current = APP.read_text(encoding="utf-8")
    missing = [item for item in required if item not in current]
    if missing:
        raise RuntimeError(f"missing post-patch invariants: {missing}")

    walcl = 6_737_204 / 1_000_000
    reserves = 2_894_531 / 1_000_000
    tga = 800_000 / 1_000_000
    rrp = 3.347 / 1_000
    net = walcl - tga - rrp
    if not (5.0 < net < 6.5 and 2.0 < reserves < 4.0):
        raise RuntimeError(f"unit sanity failed: net={net}, reserves={reserves}")
    print("US liquidity patch OK", round(net, 3), round(reserves, 3), round(tga, 3), round(rrp, 4))


if __name__ == "__main__":
    main()
