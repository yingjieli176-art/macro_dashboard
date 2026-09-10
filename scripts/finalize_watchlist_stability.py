from pathlib import Path

APP = Path("app.py")
text = APP.read_text(encoding="utf-8")

# Re-running the earlier migration could duplicate this UI hint. Collapse it.
duplicate = '''    if row.get("_stale"): source_text = (source_text + " · 上次有效报价").strip(" ·")
    if row.get("_stale"): source_text = (source_text + " · 上次有效报价").strip(" ·")
'''
single = '''    if row.get("_stale"): source_text = (source_text + " · 上次有效报价").strip(" ·")
'''
while duplicate in text:
    text = text.replace(duplicate, single)

# Market-overview cards use the same last-known-good cache, so disclose stale
# values there as well rather than silently presenting them as live.
old_meta = '''def _quote_meta(row, market=""):
    source = row.get("data_source") or row.get("quote_source") or ""; delayed = row.get("delayed_by"); state = _market_state_text(row); parts = [state] if state else []
    if delayed not in (None, 0, "0") and source == "Yahoo Finance": parts.append(f"延迟{delayed}分")
    elif source: parts.append(source)
    return " · ".join(parts)
'''
new_meta = '''def _quote_meta(row, market=""):
    source = row.get("data_source") or row.get("quote_source") or ""; delayed = row.get("delayed_by"); state = _market_state_text(row); parts = [state] if state else []
    if delayed not in (None, 0, "0") and source == "Yahoo Finance": parts.append(f"延迟{delayed}分")
    elif source: parts.append(source)
    if row.get("_stale"): parts.append("上次有效报价")
    return " · ".join(parts)
'''
if old_meta in text:
    text = text.replace(old_meta, new_meta, 1)
elif 'if row.get("_stale"): parts.append("上次有效报价")' not in text:
    raise RuntimeError("_quote_meta block not found")

APP.write_text(text, encoding="utf-8")
print("finalized watchlist stale-quote disclosure")
