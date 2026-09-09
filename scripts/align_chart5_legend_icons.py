from pathlib import Path

PATH = Path("macro_platform/hk_liquidity.py")
text = PATH.read_text(encoding="utf-8")
original = text

old = '''                mode="lines+markers",\n                line=line,\n                marker=dict(symbol="circle", size=4.5, color=color),\n'''
new = '''                mode="lines",\n                line=line,\n'''

if old in text:
    text = text.replace(old, new, 1)
elif 'mode="lines",\n                line=line,' in text:
    print("Chart 5 legend icons already match charts 1-4")
else:
    raise RuntimeError("Chart 5 trace style target not found")

if text != original:
    PATH.write_text(text, encoding="utf-8")
    print("Chart 5 legend icons aligned to charts 1-4")
