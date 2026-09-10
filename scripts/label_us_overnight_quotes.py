from pathlib import Path

path = Path("app.py")
text = path.read_text(encoding="utf-8")

old = 'def _empty_quote():\n    return {"price": None, "change_pct": None, "market_state": "", "currency": "", "post_price": None, "post_change_pct": None, "pre_price": None, "pre_change_pct": None, "overnight_price": None, "overnight_change_pct": None, "regular_market_time": None, "post_market_time": None, "pre_market_time": None, "quote_source": "", "delayed_by": None, "data_source": ""}'
new = 'def _empty_quote():\n    return {"price": None, "change_pct": None, "market_state": "", "currency": "", "post_price": None, "post_change_pct": None, "pre_price": None, "pre_change_pct": None, "overnight_price": None, "overnight_change_pct": None, "overnight_market_time": None, "regular_market_time": None, "post_market_time": None, "pre_market_time": None, "quote_source": "", "delayed_by": None, "data_source": ""}'
if old in text:
    text = text.replace(old, new, 1)

old = '            price = item.get("overnightMarketPrice")\n            pct = item.get("overnightChangePercent")\n            if price is not None:\n                if pct is None and previous not in (None, 0):\n                    pct = (price - previous) / previous * 100\n                return price, pct\n        except Exception:\n            continue\n    return None, None'
new = '            price = item.get("overnightMarketPrice")\n            pct = item.get("overnightChangePercent")\n            market_time = item.get("overnightMarketTime")\n            if price is not None:\n                if pct is None and previous not in (None, 0):\n                    pct = (price - previous) / previous * 100\n                return price, pct, market_time\n        except Exception:\n            continue\n    return None, None, None'
if old not in text:
    raise SystemExit("overnight fetch block not found")
text = text.replace(old, new, 1)

old = '            overnight_price, overnight_change_pct = _get_yahoo_overnight_safe(symbol, previous)'
new = '            overnight_price, overnight_change_pct, overnight_market_time = _get_yahoo_overnight_safe(symbol, previous)'
if old not in text:
    raise SystemExit("overnight call not found")
text = text.replace(old, new, 1)

old = '                "overnight_price": overnight_price,\n                "overnight_change_pct": overnight_change_pct,\n                "regular_market_time": meta.get("regularMarketTime"),'
new = '                "overnight_price": overnight_price,\n                "overnight_change_pct": overnight_change_pct,\n                "overnight_market_time": overnight_market_time,\n                "regular_market_time": meta.get("regularMarketTime"),'
if old not in text:
    raise SystemExit("row overnight fields not found")
text = text.replace(old, new, 1)

old = '        overnight_price, overnight_change = row.get("overnight_price"), row.get("overnight_change_pct")\n        market_state = row.get("market_state")\n        if market_state in ("POSTPOST", "CLOSED") and overnight_price is not None:\n            session_text = f\'夜盘 {overnight_price:,.2f} · {"--" if overnight_change is None else f"{overnight_change:+.2f}%"}\''
new = '        overnight_price, overnight_change = row.get("overnight_price"), row.get("overnight_change_pct")\n        overnight_time = row.get("overnight_market_time")\n        market_state = row.get("market_state")\n        overnight_fresh = True\n        if overnight_time not in (None, ""):\n            try:\n                overnight_fresh = 0 <= time.time() - float(overnight_time) <= 18 * 3600\n            except (TypeError, ValueError):\n                overnight_fresh = False\n        if market_state in ("POSTPOST", "CLOSED") and overnight_price is not None and overnight_fresh:\n            time_label = ""\n            if overnight_time not in (None, ""):\n                try:\n                    time_label = " · " + datetime.fromtimestamp(float(overnight_time), DASHBOARD_TZ).strftime("%H:%M HKT")\n                except (TypeError, ValueError, OSError):\n                    pass\n            session_text = f\'夜盘 {overnight_price:,.2f} · {"--" if overnight_change is None else f"{overnight_change:+.2f}%"}{time_label}\''
if old not in text:
    raise SystemExit("overnight render block not found")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("overnight quote labeling and freshness guard applied")
