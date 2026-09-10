from pathlib import Path

APP = Path("app.py")
text = APP.read_text(encoding="utf-8")

old = '''        divisor = 1 if str(symbol).upper() in ("^HSI", "HSTECH.HK", "^HSTECH", "000001.SS", "399001.SZ", "000300.SS") else 100
        price = float(price_raw) / divisor; previous = None if prev_raw in (None, "-") else float(prev_raw) / divisor
'''
new = '''        # fltt=2 asks Eastmoney to return formatted decimal values already in
        # native price units. Do not divide stock prices by 100 a second time.
        price = float(price_raw)
        previous = None if prev_raw in (None, "-") else float(prev_raw)
'''
if old in text:
    text = text.replace(old, new, 1)
elif "Do not divide stock prices by 100 a second time" not in text:
    raise RuntimeError("Eastmoney price scaling block not found")

old_currency = '''"currency": ("HKD" if str(symbol).upper().endswith(".HK") else "CNY")'''
new_currency = '''"currency": ("HKD" if str(symbol).upper().endswith(".HK") or str(symbol).upper() in ("^HSI", "^HSTECH", "HSTECH.HK") else "CNY")'''
if old_currency in text:
    text = text.replace(old_currency, new_currency, 1)

APP.write_text(text, encoding="utf-8")
print("fixed Eastmoney fltt=2 quote scaling")
