from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
DATA = ROOT / "data.py"
HK = ROOT / "macro_platform" / "hk_liquidity.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing block: {label}")
    return text.replace(old, new, 1)


def patch_app() -> None:
    text = APP.read_text(encoding="utf-8")

    # A quote status and the large displayed number must refer to the same session.
    old_context = re.search(r"def _quote_session_context\(row, market=\"\"\):\n.*?\n\ndef _market_state_text", text, flags=re.S)
    if not old_context:
        raise RuntimeError("quote session context not found")
    new_context = '''def _us_overnight_window_now():
    ny = datetime.now(ZoneInfo("America/New_York"))
    minute = ny.hour * 60 + ny.minute
    # Overnight US equity venues generally cover Sunday-Thursday evenings
    # and the following weekday early-morning session. Source market-state and
    # a fresh overnight timestamp are still required before displaying a quote.
    return (ny.weekday() in {6, 0, 1, 2, 3} and minute >= 20 * 60) or (ny.weekday() in {0, 1, 2, 3, 4} and minute < 4 * 60)


def _quote_session_context(row, market=""):
    market = str(market or "").upper()
    state = str(row.get("market_state") or "").upper()
    now_ts = time.time()

    if market == "US":
        regular_ts = _valid_market_timestamp(row.get("regular_market_time"))
        pre_ts = _valid_market_timestamp(row.get("pre_market_time"))
        post_ts = _valid_market_timestamp(row.get("post_market_time"))
        overnight_ts = _valid_market_timestamp(row.get("overnight_market_time"))
        overnight_fresh = (
            row.get("overnight_price") is not None
            and overnight_ts is not None
            and 0 <= now_ts - overnight_ts <= 18 * 3600
        )
        overnight_active = overnight_fresh and (
            state in {"PREPRE", "POSTPOST"} or (state == "CLOSED" and _us_overnight_window_now())
        )
        if overnight_active:
            return "夜盘", overnight_ts
        if state in {"PREPRE", "POSTPOST"}:
            return "夜盘时段 · 正常盘最近价", regular_ts
        if state == "PRE":
            if row.get("pre_price") is not None:
                return "盘前", pre_ts
            return "盘前时段 · 正常盘最近价", regular_ts
        if state == "REGULAR":
            return "交易中", regular_ts
        if state == "POST":
            if row.get("post_price") is not None:
                return "盘后", post_ts
            return "盘后时段 · 正常盘最近价", regular_ts
        if state == "CLOSED":
            candidates = [x for x in (post_ts, regular_ts) if x is not None]
            return "休市", max(candidates) if candidates else None
        candidates = [x for x in (overnight_ts, pre_ts, post_ts, regular_ts) if x is not None]
        return "状态未知", max(candidates) if candidates else None

    quote_ts = _valid_market_timestamp(row.get("regular_market_time"))
    return _asia_session_state(market, quote_ts), quote_ts


def _market_state_text'''
    text = text[: old_context.start()] + new_context + text[old_context.end():]

    old_meta = '''    if delayed not in (None, 0, "0") and source == "Yahoo Finance":
        parts.append(f"延迟{delayed}分")
    elif source:
        parts.append(source)'''
    new_meta = '''    if source:
        parts.append(source)
    if delayed not in (None, 0, "0") and source == "Yahoo Finance":
        parts.append(f"延迟{delayed}分")'''
    text = replace_once(text, old_meta, new_meta, "quote source and delay disclosure")

    # Watchlist session lines use the same validated session context as overview.
    old_session = re.search(r"    session_text = \"\"\n    if item.get\(\"market\"\) == \"US\":\n.*?\n\n    meta = _quote_meta", text, flags=re.S)
    if not old_session:
        raise RuntimeError("watchlist session block not found")
    new_session = '''    session_text = ""
    if item.get("market") == "US":
        pp, pc = row.get("post_price"), row.get("post_change_pct")
        pre_price, pre_change = row.get("pre_price"), row.get("pre_change_pct")
        overnight_price, overnight_change = row.get("overnight_price"), row.get("overnight_change_pct")
        state_label, _ = _quote_session_context(row, "US")
        if state_label == "夜盘" and overnight_price is not None:
            time_label = _market_time_label(row.get("overnight_market_time"))
            session_text = f'夜盘 {overnight_price:,.2f} · {"--" if overnight_change is None else f"{overnight_change:+.2f}%"}' + (f" · {time_label}" if time_label else "")
        elif state_label == "盘前" and pre_price is not None:
            time_label = _market_time_label(row.get("pre_market_time"))
            session_text = f'盘前 {pre_price:,.2f} · {"--" if pre_change is None else f"{pre_change:+.2f}%"}' + (f" · {time_label}" if time_label else "")
        elif state_label == "盘后" and pp is not None:
            time_label = _market_time_label(row.get("post_market_time"))
            session_text = f'盘后 {pp:,.2f} · {"--" if pc is None else f"{pc:+.2f}%"}' + (f" · {time_label}" if time_label else "")

    meta = _quote_meta'''
    text = text[: old_session.start()] + new_session + text[old_session.end():]

    # Keep observed source lines at their native frequency. Forward filling is
    # allowed only in the calculation table used for the mixed-frequency proxy.
    fig4 = re.search(r"def build_fig4\(date_range\):\n.*?\n\ndef build_fig3\(date_range\):", text, flags=re.S)
    if not fig4:
        raise RuntimeError("build_fig4 not found")
    new_fig4 = '''def build_fig4(date_range):
    specs = [(get_wresbal, "WRESBAL"), (get_tga_daily, "TGA_DAILY"), (get_rrp_daily, "RRPONTSYD")]
    raw_series = {}
    tga_is_fallback = False
    for getter, column in specs:
        try:
            frame = getter().copy()
            if column == "TGA_DAILY":
                tga_is_fallback = bool(frame.attrs.get("is_fallback", False))
            frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="coerce")
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
            frame = frame.dropna(subset=["observation_date", column]).sort_values("observation_date")[["observation_date", column]]
            if not frame.empty:
                raw_series[column] = frame
        except Exception:
            continue
    if not raw_series:
        return apply_chart_style(go.Figure(), chart_height(340, 500), date_range)

    aligned = None
    for frame in raw_series.values():
        aligned = frame.copy() if aligned is None else aligned.merge(frame, on="observation_date", how="outer")
    aligned = aligned.sort_values("observation_date")
    value_cols = [c for c in ["WRESBAL", "TGA_DAILY", "RRPONTSYD"] if c in aligned.columns]
    calc = aligned.copy()
    calc[value_cols] = calc[value_cols].ffill()
    if all(c in calc.columns for c in ["WRESBAL", "TGA_DAILY", "RRPONTSYD"]):
        calc["NetLiquidity"] = calc["WRESBAL"] - calc["TGA_DAILY"] - calc["RRPONTSYD"]
    calc = filter_range(calc, date_range)

    fig = go.Figure()
    net_name = "Net Liquidity Proxy · weekly TGA fallback" if tga_is_fallback else "Net Liquidity Proxy · mixed frequency"
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
            continue
        add_line(fig, filter_range(frame, date_range), column, observed_names[column], width_map[column], dash_map[column], unit=" T")
    fig.update_layout(yaxis_title="$T")
    return apply_chart_style(fig, chart_height(340, 500), date_range)


def build_fig3(date_range):'''
    text = text[: fig4.start()] + new_fig4 + text[fig4.end():]

    text = replace_once(
        text,
        '1. Net Liquidity Proxy：Reserve Balances − TGA − ON RRP 的组合指标，用于描述美国金融体系中可观察的流动性变化方向；不是美联储官方指标。<br>2. Reserve Balances：存款机构存放在美联储的准备金余额，属于银行体系流动性的重要组成部分。',
        '1. Net Liquidity Proxy：Reserve Balances − TGA − ON RRP 的组合指标，用于描述美国金融体系中可观察的流动性变化方向；不是美联储官方指标。该代理为混合频率计算，周频准备金余额只在代理计算内部沿用至下一次公布，不代表每天都有新的准备金观测。<br>2. Reserve Balances：存款机构存放在美联储的准备金余额；WRESBAL 为周频公布，图中的原始线只保留实际周频观测，不再用前值填充伪装成日频。',
        "US liquidity description",
    )

    APP.write_text(text, encoding="utf-8")


def patch_data() -> None:
    text = DATA.read_text(encoding="utf-8")
    old = '''    # Some feeds return Unix seconds/milliseconds. Convert them before display
    # instead of leaking a raw epoch value into the UI.
    if re.fullmatch(r"\\d{10,13}", text):
        try:
            raw = int(text)
            unit = "ms" if len(text) >= 13 else "s"
            dt = pd.to_datetime(raw, unit=unit, utc=True, errors="coerce")
            if not pd.isna(dt):
                dt = dt.tz_convert("Asia/Hong_Kong")
                return dt.strftime("%H:%M:%S") if dt.date() == now_hkt.date() else dt.strftime("%m-%d %H:%M")
        except Exception:
            pass'''
    new = '''    # Numeric time fields are treated as Unix timestamps only. Reject epoch-zero,
    # corrupt or implausible values instead of printing them as if they were a clock.
    if re.fullmatch(r"\\d+", text):
        if len(text) not in {10, 13}:
            return ""
        try:
            raw = int(text)
            unit = "ms" if len(text) == 13 else "s"
            dt = pd.to_datetime(raw, unit=unit, utc=True, errors="coerce")
            if pd.isna(dt):
                return ""
            dt = dt.tz_convert("Asia/Hong_Kong")
            if dt.year < 2000 or dt > now_hkt + pd.Timedelta(days=1):
                return ""
            return dt.strftime("%H:%M:%S") if dt.date() == now_hkt.date() else dt.strftime("%m-%d %H:%M")
        except Exception:
            return ""'''
    text = replace_once(text, old, new, "news numeric timestamp validation")
    DATA.write_text(text, encoding="utf-8")


def patch_hk() -> None:
    text = HK.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '    return float(gaps.median()) <= 7.0 and float((gaps <= 7.0).mean()) >= 0.60',
        '    # Business-daily observations usually have 1-3 day gaps; a weekly\n    # series must never be promoted to "Daily" merely because its gap is 7 days.\n    return float(gaps.median()) <= 4.0 and float((gaps <= 4.0).mean()) >= 0.80',
        "strict daily-frequency test",
    )
    text = replace_once(
        text,
        '    fx_source = fx_daily if not fx_daily.empty else data[["observation_date", "USD/HKD"]].dropna().copy()\n    add_line(fx, fx_source, "USD/HKD", "USD/HKD", COLORS["fx"], 2.6, unit="", secondary_y=False)',
        '    fx_is_daily = not fx_daily.empty\n    fx_source = fx_daily if fx_is_daily else data[["observation_date", "USD/HKD"]].dropna().copy()\n    fx_trace_name = "USD/HKD" if fx_is_daily else "USD/HKD · Monthly fallback"\n    add_line(fx, fx_source, "USD/HKD", fx_trace_name, COLORS["fx"], 2.6, unit="", secondary_y=False)',
        "USDHKD fallback label",
    )
    HK.write_text(text, encoding="utf-8")


def main() -> None:
    patch_app()
    patch_data()
    patch_hk()
    print("truth audit v2 applied")


if __name__ == "__main__":
    main()
