from pathlib import Path
import re

APP = Path("app.py")
text = APP.read_text(encoding="utf-8")

old_css = '''.market-groups { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 7px; margin-bottom: 0.45rem; }
.market-group { border: 1px solid #e5e7eb; border-radius: 8px; padding: 6px 8px 5px; background: #fff; min-width: 0; min-height: 96px; box-sizing: border-box; }
.market-group-title { color: #374151; font-size: 0.88rem; font-weight: 650; margin-bottom: 5px; }
.market-group-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 4px; min-height: 66px; align-items: start; }
.market-group-row.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.market-item { min-width: 0; height: 66px; min-height: 66px; max-height: 66px; padding-right: 4px; border-right: 1px solid #f0f0f0; box-sizing: border-box; overflow: hidden; }
.market-item:last-child { border-right: none; }
.market-name { color: #6b7280; font-size: 0.78rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.market-price { color: #111827; font-size: 0.98rem; font-weight: 650; margin-top: 1px; white-space: nowrap; }
.market-change { font-size: 0.76rem; white-space: nowrap; }
.market-meta { color: #9ca3af; font-size: 0.66rem; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }'''

new_css = '''/* Market overview · compact professional index tape */
.market-groups { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin:2px 0 10px; }
.market-group { border:1px solid #dde3ea; border-radius:10px; padding:0; background:#fff; min-width:0; overflow:hidden; box-shadow:0 1px 2px rgba(15,23,42,.035); }
.market-group-title { color:#475569; font-size:.70rem; font-weight:750; letter-spacing:.08em; text-transform:uppercase; padding:8px 11px 7px; margin:0; background:#f8fafc; border-bottom:1px solid #edf1f5; }
.market-group-row { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:0; align-items:stretch; }
.market-group-row.two { grid-template-columns:repeat(2,minmax(0,1fr)); }
.market-item { min-width:0; min-height:82px; padding:9px 11px 8px; border-right:1px solid #edf1f5; box-sizing:border-box; overflow:hidden; transition:background .15s ease; }
.market-item:hover { background:#fbfdff; }
.market-item:last-child { border-right:none; }
.market-name { color:#64748b; font-size:.70rem; font-weight:650; line-height:1.2; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.market-price { color:#0f172a; font-size:1.13rem; line-height:1.15; font-weight:740; letter-spacing:-.02em; margin-top:5px; white-space:nowrap; font-variant-numeric:tabular-nums; }
.market-change { display:inline-flex; align-items:center; margin-top:4px; padding:1px 6px; border-radius:999px; font-size:.68rem; font-weight:700; line-height:1.5; white-space:nowrap; font-variant-numeric:tabular-nums; }
.market-change.up { color:#047857; background:#ecfdf5; }
.market-change.down { color:#b91c1c; background:#fef2f2; }
.market-change.flat { color:#64748b; background:#f1f5f9; }
.market-meta { color:#94a3b8; font-size:.60rem; margin-top:4px; line-height:1.25; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
@media (max-width:1100px) { .market-groups { grid-template-columns:1fr; } }'''

if old_css not in text:
    raise RuntimeError("market overview CSS anchor not found")
text = text.replace(old_css, new_css, 1)

# Remove the later generic override so the dedicated market-tape geometry wins.
text = text.replace('.market-group { border-radius: 12px; padding: 9px 10px 8px; }\n', '', 1)

pattern = re.compile(r'''def _market_item_html\(name, price, change_pct, meta=""\):\n    price_text = .*?\n    return f'<div class="market-item"><div class="market-name">\{html\.escape\(name\)\}</div><div class="market-price">\{html\.escape\(price_text\)\}</div><div class="market-change">\{html\.escape\(change_text\)\}</div><div class="market-meta">\{html\.escape\(meta\)\}</div></div>' ''', re.S | re.X)

replacement = '''def _market_item_html(name, price, change_pct, meta=""):
    price_text = "--" if price is None else f"{price:,.2f}"
    change_text = "--" if change_pct is None else f"{change_pct:+.2f}%"
    change_class = "flat" if change_pct is None or change_pct == 0 else ("up" if change_pct > 0 else "down")
    return (
        '<div class="market-item">'
        f'<div class="market-name">{html.escape(name)}</div>'
        f'<div class="market-price">{html.escape(price_text)}</div>'
        f'<div class="market-change {change_class}">{html.escape(change_text)}</div>'
        f'<div class="market-meta">{html.escape(meta)}</div>'
        '</div>'
    )'''

text, n = pattern.subn(replacement, text, count=1)
if n != 1:
    # Fall back to the exact compact implementation used by the current app.
    old_fn = '''def _market_item_html(name, price, change_pct, meta=""):
    price_text = "--" if price is None else f"{price:,.2f}"; change_text = "--" if change_pct is None else f"{change_pct:+.2f}%"
    return f'<div class="market-item"><div class="market-name">{html.escape(name)}</div><div class="market-price">{html.escape(price_text)}</div><div class="market-change">{html.escape(change_text)}</div><div class="market-meta">{html.escape(meta)}</div></div>'
'''
    if old_fn not in text:
        raise RuntimeError("market item renderer anchor not found")
    text = text.replace(old_fn, replacement + "\n", 1)

text = text.replace(
    '<div class="section-title">市场概览</div><div class="section-description">美股、港股与 A 股主要指数 · 报价时间来自行情源 · 交易状态按市场时段与报价日期判定 · 60 秒刷新</div>',
    '<div class="section-title">市场概览</div><div class="section-description">主要指数行情带 · 当前价格 / 涨跌幅 / 市场状态 / 报价时间 · 60 秒刷新</div>',
    1,
)

APP.write_text(text, encoding="utf-8")
print("Refined market overview only; dashboard structure unchanged.")
