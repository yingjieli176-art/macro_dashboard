from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing expected block: {label}")
    return text.replace(old, new, 1)


def main() -> None:
    text = APP.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '.watch-meta { color:#9ca3af; font-size:.64rem; margin-top:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }',
        '.watch-meta { color:#9ca3af; font-size:.64rem; margin-top:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }\n'
        '.crypto-metrics { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:5px 7px; margin-top:8px; padding-top:7px; border-top:1px solid #edf1f5; }\n'
        '.crypto-metric { min-width:0; }\n'
        '.crypto-metric-label { color:#94a3b8; font-size:.58rem; letter-spacing:.04em; line-height:1.2; white-space:nowrap; }\n'
        '.crypto-metric-value { color:#334155; font-size:.70rem; font-weight:680; line-height:1.3; margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-variant-numeric:tabular-nums; }',
        "crypto metric css",
    )

    helper_marker = 'def _render_quote_block(item):\n'
    if helper_marker not in text:
        raise RuntimeError("render quote marker not found")

    helpers = r'''@st.cache_data(ttl=60, show_spinner=False)
def _get_crypto_metrics(symbol):
    """Compact crypto context from Yahoo daily history + quote metadata."""
    symbol = str(symbol or "").upper().strip()
    result_data = {
        "change_7d": None,
        "change_30d": None,
        "realized_vol_30d": None,
        "volume_24h": None,
        "market_cap": None,
    }
    if not symbol.endswith("-USD"):
        return result_data

    try:
        response = requests.get(
            YAHOO_CHART_BASES[0] + symbol,
            params={"range": "2mo", "interval": "1d", "includePrePost": "false", "events": "div,splits"},
            headers={"User-Agent": "Mozilla/5.0 (compatible; MacroDashboard/1.0)"},
            timeout=4.0,
        )
        response.raise_for_status()
        rows = (response.json().get("chart", {}).get("result") or [])
        if rows:
            chart = rows[0]
            timestamps = chart.get("timestamp") or []
            quote = (chart.get("indicators", {}).get("quote") or [{}])[0]
            closes = quote.get("close") or []
            volumes = quote.get("volume") or []
            observations = [
                (int(ts), float(close), volumes[idx] if idx < len(volumes) else None)
                for idx, (ts, close) in enumerate(zip(timestamps, closes))
                if ts is not None and close is not None
            ]
            if observations:
                last_ts, last_close, _ = observations[-1]

                def _change(days):
                    cutoff = last_ts - days * 86400
                    candidates = [close for ts, close, _ in observations if ts <= cutoff]
                    base = candidates[-1] if candidates else None
                    if base in (None, 0):
                        return None
                    return (last_close / base - 1.0) * 100.0

                result_data["change_7d"] = _change(7)
                result_data["change_30d"] = _change(30)
                close_series = pd.Series([close for _, close, _ in observations], dtype="float64")
                returns = close_series.pct_change(fill_method=None).dropna().tail(30)
                if len(returns) >= 10:
                    result_data["realized_vol_30d"] = float(returns.std(ddof=1) * (365.0 ** 0.5) * 100.0)
                valid_volumes = [float(volume) for _, _, volume in observations if volume not in (None, 0)]
                if valid_volumes:
                    result_data["volume_24h"] = valid_volumes[-1]
    except Exception:
        pass

    # The quote endpoint usually exposes market cap and the freshest 24h volume.
    for quote_url in YAHOO_QUOTE_URLS:
        try:
            response = requests.get(
                quote_url,
                params={"symbols": symbol},
                headers={"User-Agent": "Mozilla/5.0 (compatible; MacroDashboard/1.0)"},
                timeout=3.0,
            )
            response.raise_for_status()
            rows = ((response.json() or {}).get("quoteResponse") or {}).get("result") or []
            if not rows:
                continue
            quote = rows[0]
            if quote.get("regularMarketVolume") not in (None, 0):
                result_data["volume_24h"] = float(quote["regularMarketVolume"])
            if quote.get("marketCap") not in (None, 0):
                result_data["market_cap"] = float(quote["marketCap"])
            break
        except Exception:
            continue
    return result_data


@st.cache_data(ttl=60, show_spinner=False)
def _get_eth_btc_ratio():
    try:
        eth = _get_yahoo_quote_safe("ETH-USD").get("price")
        btc = _get_yahoo_quote_safe("BTC-USD").get("price")
        if eth is None or btc in (None, 0):
            return None
        return float(eth) / float(btc)
    except Exception:
        return None


def _compact_usd(value):
    if value is None:
        return "--"
    value = float(value)
    if abs(value) >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value:,.0f}"


def _crypto_metrics_html(symbol):
    metrics = _get_crypto_metrics(symbol)
    def pct(value):
        return "--" if value is None else f"{value:+.1f}%"

    ratio = _get_eth_btc_ratio()
    fields = [
        ("7D", pct(metrics.get("change_7d"))),
        ("30D", pct(metrics.get("change_30d"))),
        ("VOL · 30D", "--" if metrics.get("realized_vol_30d") is None else f'{metrics["realized_vol_30d"]:.0f}%'),
        ("24H VOLUME", _compact_usd(metrics.get("volume_24h"))),
        ("MARKET CAP", _compact_usd(metrics.get("market_cap"))),
        ("ETH / BTC", "--" if ratio is None else f"{ratio:.4f}"),
    ]
    blocks = "".join(
        f'<div class="crypto-metric"><div class="crypto-metric-label">{html.escape(label)}</div><div class="crypto-metric-value">{html.escape(value)}</div></div>'
        for label, value in fields
    )
    return f'<div class="crypto-metrics">{blocks}</div>'


'''
    text = text.replace(helper_marker, helpers + helper_marker, 1)

    text = replace_once(
        text,
        '    change_text = "数据暂缺" if price is None else ("--" if change is None else f"{change:+.2f}%")',
        '    change_text = "数据暂缺" if price is None else ("--" if change is None else f"{change:+.2f}%")\n'
        '    if item.get("market") == "CRYPTO" and price is not None and change is not None:\n'
        '        change_text = f"24H {change:+.2f}%"',
        "crypto 24h label",
    )

    text = replace_once(
        text,
        "    session_html = f'<div class=\"watch-session\">{html.escape(session_text)}</div>' if session_text else ''\n    return (",
        "    session_html = f'<div class=\"watch-session\">{html.escape(session_text)}</div>' if session_text else ''\n"
        "    metrics_html = _crypto_metrics_html(item.get(\"symbol\", \"\")) if item.get(\"market\") == \"CRYPTO\" else \"\"\n"
        "    return (",
        "crypto metrics insertion",
    )

    text = replace_once(
        text,
        "        f'{session_html}<div class=\"watch-meta\">{html.escape(meta)}</div>'\n        '</div>'",
        "        f'{session_html}<div class=\"watch-meta\">{html.escape(meta)}</div>{metrics_html}'\n        '</div>'",
        "crypto metrics render",
    )

    text = replace_once(
        text,
        '核心标的快速监控 · 美股 / 港股 / A股 / Crypto 分组 · Crypto 24/7 Yahoo · 港/A 双源择新 + 分时兜底 · 15 秒自动刷新',
        '核心标的快速监控 · Crypto 显示 24H / 7D / 30D / 30D波动率 / 成交额 / 市值 / ETH-BTC · 港/A 双源择新 + 分时兜底 · 15 秒自动刷新',
        "watchlist description",
    )

    APP.write_text(text, encoding="utf-8")
    print("crypto metrics migration applied")


if __name__ == "__main__":
    main()
