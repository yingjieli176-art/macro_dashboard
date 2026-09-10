from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
DATA = ROOT / "data.py"
HK = ROOT / "macro_platform" / "hk_liquidity.py"


def require_replace(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing expected block: {label}")
    return text.replace(old, new, 1)


def patch_app() -> None:
    text = APP.read_text(encoding="utf-8")

    text = require_replace(
        text,
        'def get_start_date(date_range):\n    end = pd.Timestamp.today().normalize(); return {"5Y": end - pd.DateOffset(years=5), "1Y": end - pd.DateOffset(years=1), "6M": end - pd.DateOffset(months=6), "3M": end - pd.DateOffset(months=3), "1M": end - pd.DateOffset(months=1)}[date_range]',
        'def get_start_date(date_range):\n    end = pd.Timestamp.now(tz="Asia/Hong_Kong").tz_localize(None).normalize()\n    return {"5Y": end - pd.DateOffset(years=5), "1Y": end - pd.DateOffset(years=1), "6M": end - pd.DateOffset(months=6), "3M": end - pd.DateOffset(months=3), "1M": end - pd.DateOffset(months=1)}[date_range]',
        "dashboard range timezone",
    )

    old_fig4 = re.search(r"def build_fig4\(date_range\):\n.*?\n\ndef build_fig3\(date_range\):", text, flags=re.S)
    if not old_fig4:
        raise RuntimeError("build_fig4 block not found")
    new_fig4 = '''def build_fig4(date_range):
    specs = [(get_wresbal, "WRESBAL"), (get_tga_daily, "TGA_DAILY"), (get_rrp_daily, "RRPONTSYD")]
    series = []
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
                series.append(frame)
        except Exception:
            continue
    if not series:
        return apply_chart_style(go.Figure(), chart_height(340, 500), date_range)
    data = series[0]
    for frame in series[1:]:
        data = data.merge(frame, on="observation_date", how="outer")
    data = data.sort_values("observation_date")
    value_cols = [c for c in ["WRESBAL", "TGA_DAILY", "RRPONTSYD"] if c in data.columns]
    data[value_cols] = data[value_cols].ffill()
    if all(c in data.columns for c in ["WRESBAL", "TGA_DAILY", "RRPONTSYD"]):
        data["NetLiquidity"] = data["WRESBAL"] - data["TGA_DAILY"] - data["RRPONTSYD"]
    data = filter_range(data, date_range)
    fig = go.Figure()
    net_name = "Net Liquidity Proxy · weekly TGA fallback" if tga_is_fallback else "Net Liquidity Proxy"
    tga_name = "TGA · Weekly fallback" if tga_is_fallback else "TGA · Daily"
    for column, name, width, dash in [
        ("NetLiquidity", net_name, 3.0, None),
        ("WRESBAL", "Reserve Balances", 2.3, None),
        ("TGA_DAILY", tga_name, 2.1, "dash"),
        ("RRPONTSYD", "ON RRP", 2.1, "dot"),
    ]:
        add_line(fig, data, column, name, width, dash, unit=" T")
    fig.update_layout(yaxis_title="$T")
    return apply_chart_style(fig, chart_height(340, 500), date_range)


def build_fig3(date_range):'''
    text = text[: old_fig4.start()] + new_fig4 + text[old_fig4.end() :]

    helper = '''\n\ndef _active_quote_values(row, market=""):\n    """Return price/change from the same session named by the status label."""\n    market = str(market or "").upper()\n    if market == "US":\n        state, _ = _quote_session_context(row, market)\n        if state == "夜盘" and row.get("overnight_price") is not None:\n            return row.get("overnight_price"), row.get("overnight_change_pct")\n        if state == "盘前" and row.get("pre_price") is not None:\n            return row.get("pre_price"), row.get("pre_change_pct")\n        if state == "盘后" and row.get("post_price") is not None:\n            return row.get("post_price"), row.get("post_change_pct")\n    return row.get("price"), row.get("change_pct")\n'''
    marker = "\ndef render_market_groups():"
    if "def _active_quote_values(" not in text:
        if marker not in text:
            raise RuntimeError("render_market_groups marker not found")
        text = text.replace(marker, helper + marker, 1)

    group_pattern = re.compile(r"    q = snapshot\n    groups = \[.*?\]\n    cards = \[\]", flags=re.S)
    group_match = group_pattern.search(text)
    if not group_match:
        raise RuntimeError("market overview group block not found")
    group_block = '''    q = snapshot

    def overview_item(name, row, market):
        price, change = _active_quote_values(row, market)
        return _market_item_html(name, price, change, _quote_meta(row, market))

    groups = [
        ("🇺🇸 美股", [overview_item("纳斯达克", q["nasdaq"], "US"), overview_item("标普500", q["sp500"], "US"), overview_item("道琼斯", q["dow"], "US")], "three"),
        ("🇭🇰 港股", [overview_item("恒生指数", q["hsi"], "HK"), overview_item("恒生科技", q["hstech"], "HK")], "two"),
        ("🇨🇳 A股", [overview_item("上证指数", q["sh"], "CN"), overview_item("深证成指", q["sz"], "CN"), overview_item("沪深300", q["csi300"], "CN")], "three"),
    ]
    cards = []'''
    text = text[: group_match.start()] + group_block + text[group_match.end() :]

    text = require_replace(
        text,
        '状态与报价时间来自行情源 · 60 秒刷新',
        '报价时间来自行情源 · 交易状态按市场时段与报价日期判定 · 60 秒刷新',
        "market overview truth wording",
    )
    text = require_replace(
        text,
        '东方财富「红字焦点快讯」 · 平台已筛选重点 · 每60秒自动刷新',
        '东方财富「红字焦点快讯」 · 源端焦点流 · 每60秒自动刷新',
        "news source wording",
    )
    if '@st.fragment(run_every="60s")\ndef render_news_panel():' not in text:
        text = require_replace(
            text,
            'def render_news_panel():',
            '@st.fragment(run_every="60s")\ndef render_news_panel():',
            "news fragment",
        )

    APP.write_text(text, encoding="utf-8")


def patch_data() -> None:
    text = DATA.read_text(encoding="utf-8")

    text = require_replace(
        text,
        '        return frame[["observation_date", "TGA_DAILY"]].sort_values("observation_date")',
        '        result = frame[["observation_date", "TGA_DAILY"]].sort_values("observation_date")\n        result.attrs.update({"source": "U.S. Treasury Daily Treasury Statement", "frequency": "daily", "is_fallback": False})\n        return result',
        "daily TGA metadata",
    )
    text = require_replace(
        text,
        '        return weekly[["observation_date", "TGA_DAILY"]].dropna().sort_values("observation_date")',
        '        result = weekly[["observation_date", "TGA_DAILY"]].dropna().sort_values("observation_date")\n        result.attrs.update({"source": "FRED WTREGEN", "frequency": "weekly", "is_fallback": True})\n        return result',
        "weekly TGA fallback metadata",
    )

    match = re.search(r"def _extract_time\(item\):\n.*?\n\ndef _extract_url\(item\):", text, flags=re.S)
    if not match:
        raise RuntimeError("news time parser block not found")
    replacement = '''def _extract_time(item):
    text = _clean_text(_get_field(item, ["showTime", "ShowTime", "time", "Time", "createTime", "CreateTime", "create_time", "updateTime", "UpdateTime", "publishTime", "PublishTime", "ctime", "Ctime"]))
    if not text:
        return ""

    now_hkt = pd.Timestamp.now(tz="Asia/Hong_Kong")

    # Some feeds return Unix seconds/milliseconds. Convert them before display
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
            pass

    # Preserve the source date. The old parser discarded it, which could make
    # a prior-day item look as if it had been published today.
    full = re.search(r"(\\d{4}[-/.]\\d{1,2}[-/.]\\d{1,2})[ T]+(\\d{1,2}:\\d{2}(?::\\d{2})?)", text)
    if full:
        normalized = full.group(1).replace("/", "-").replace(".", "-") + " " + full.group(2)
        dt = pd.to_datetime(normalized, errors="coerce")
        if not pd.isna(dt):
            return dt.strftime("%H:%M:%S") if dt.date() == now_hkt.date() else dt.strftime("%m-%d %H:%M")

    short = re.search(r"(\\d{1,2}[-/.]\\d{1,2})[ T]+(\\d{1,2}:\\d{2}(?::\\d{2})?)", text)
    if short:
        date_part = short.group(1).replace("/", "-").replace(".", "-")
        return f"{date_part} {short.group(2)[:5]}"

    clock = re.search(r"(\\d{1,2}:\\d{2}(?::\\d{2})?)", text)
    return clock.group(1) if clock else text


def _extract_url(item):'''
    text = text[: match.start()] + replacement + text[match.end() :]
    DATA.write_text(text, encoding="utf-8")


def patch_hk() -> None:
    text = HK.read_text(encoding="utf-8")

    marker = "\ndef build_hk_liquidity_figures("
    helper = '''\n\ndef _frame_is_daily(frame: pd.DataFrame) -> bool:\n    if frame is None or frame.empty or "observation_date" not in frame.columns:\n        return False\n    dates = pd.to_datetime(frame["observation_date"], errors="coerce").dropna().drop_duplicates().sort_values()\n    if len(dates) < 3:\n        return False\n    gaps = dates.diff().dropna().dt.total_seconds() / 86400.0\n    if gaps.empty:\n        return False\n    return float(gaps.median()) <= 7.0 and float((gaps <= 7.0).mean()) >= 0.60\n'''
    if "def _frame_is_daily(" not in text:
        if marker not in text:
            raise RuntimeError("build_hk_liquidity_figures marker not found")
        text = text.replace(marker, helper + marker, 1)

    source_old = '    banking_source = load_hk_banking_liquidity_monthly() if date_range == "5Y" else load_hk_banking_liquidity_daily()\n    funding_source = load_hk_funding_monthly() if date_range == "5Y" else load_hk_funding_daily()\n    banking_data = _slice_range(banking_source, date_range)\n    funding_data = _slice_range(funding_source, date_range)'
    source_new = '    banking_source = load_hk_banking_liquidity_monthly() if date_range == "5Y" else load_hk_banking_liquidity_daily()\n    funding_source = load_hk_funding_monthly() if date_range == "5Y" else load_hk_funding_daily()\n    banking_is_daily = _frame_is_daily(banking_source)\n    funding_is_daily = _frame_is_daily(funding_source)\n    banking_data = _slice_range(banking_source, date_range)\n    funding_data = _slice_range(funding_source, date_range)'
    text = require_replace(text, source_old, source_new, "HK source frequency detection")

    text = require_replace(
        text,
        '    style(balance, "6. Daily Banking-system Liquidity" if _daily_snapshot_available() else "6. Banking-system Liquidity · monthly fallback", height=450, right_axis=True)\n    if not banking_data.empty:\n        banking_latest = banking_data["observation_date"].max().strftime("%Y-%m-%d")\n        balance_label = "6. Daily Banking-system Liquidity" if _daily_snapshot_available() else "6. Banking-system Liquidity · monthly fallback"',
        '    banking_frequency_label = "Daily" if banking_is_daily else ("Monthly" if date_range == "5Y" else "Monthly fallback")\n    style(balance, f"6. Banking-system Liquidity · {banking_frequency_label}", height=450, right_axis=True)',
        "HK banking frequency title",
    )
    text = require_replace(
        text,
        '    style(funding, "7. HKD Funding · Daily" if _daily_snapshot_available() else "7. HKD Funding · monthly fallback", right_axis=True)\n    if not funding_data.empty:\n        funding_latest = funding_data["observation_date"].max().strftime("%Y-%m-%d" if _daily_snapshot_available() else "%Y-%m")\n        funding_label = "7. HKD Funding · Daily" if _daily_snapshot_available() else "7. HKD Funding · monthly fallback"',
        '    funding_frequency_label = "Daily" if funding_is_daily else ("Monthly" if date_range == "5Y" else "Monthly fallback")\n    style(funding, f"7. HKD Funding · {funding_frequency_label}", right_axis=True)',
        "HK funding frequency title",
    )
    text = require_replace(
        text,
        'text=f"Hong Kong Liquidity · {state[\'label\']} · latest {latest_text}",',
        'text=f"Hong Kong Liquidity · monthly signal {state[\'label\']} · through {latest_text}",',
        "monthly liquidity signal title",
    )
    text = require_replace(
        text,
        '<div><span>Latest</span><strong>{latest}</strong></div>',
        '<div><span>HKMA monthly through</span><strong>{latest}</strong></div>',
        "monthly liquidity strip label",
    )

    HK.write_text(text, encoding="utf-8")


def main() -> None:
    patch_app()
    patch_data()
    patch_hk()
    print("truth/freshness audit patch applied")


if __name__ == "__main__":
    main()
