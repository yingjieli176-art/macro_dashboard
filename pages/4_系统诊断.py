import streamlit as st
import requests
from datetime import datetime

from data import get_dgs10, get_sina_news, get_wsj_news

st.set_page_config(page_title="System Diagnostics", page_icon="🔧", layout="wide")

st.title("4. System Diagnostics")
st.caption("用于确认 Streamlit 运行、FRED、7×24 新闻源和 WSJ 是否正常。")

rows = []

# Streamlit runtime
rows.append(("Streamlit App", True, "诊断页面已成功执行"))

# FRED
try:
    x = get_dgs10()
    ok = x is not None and not x.empty
    rows.append(("FRED API", ok, f"DGS10 返回 {len(x)} 条数据" if ok else "DGS10 返回空数据"))
except Exception as e:
    rows.append(("FRED API", False, str(e)[:200]))

# Sina 7x24
try:
    x, err = get_sina_news(limit=1)
    rows.append(("Sina 7×24", bool(x), "新浪返回数据" if x else (err or "返回空数据")))
except Exception as e:
    rows.append(("Sina 7×24", False, str(e)[:200]))

# Eastmoney 7x24 direct test
try:
    r = requests.get(
        "https://np-weblist.eastmoney.com/comm/web/getFastNewsList",
        params={
            "client": "web",
            "biz": "web_724",
            "fastColumn": "102",
            "sortEnd": "",
            "pageSize": 1,
            "req_trace": str(int(datetime.now().timestamp() * 1000)),
        },
        timeout=8,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://kuaixun.eastmoney.com/",
        },
    )
    r.raise_for_status()
    items = r.json().get("data", {}).get("fastNewsList", [])
    rows.append(("Eastmoney 7×24", bool(items), "Eastmoney 返回数据" if items else "接口可访问，但返回空数据"))
except Exception as e:
    rows.append(("Eastmoney 7×24", False, str(e)[:200]))

# WSJ
try:
    x, err = get_wsj_news(limit=1)
    rows.append(("WSJ", bool(x), "WSJ headlines 返回数据" if x else (err or "返回空数据")))
except Exception as e:
    rows.append(("WSJ", False, str(e)[:200]))

for name, ok, detail in rows:
    icon = "✅" if ok else "❌"
    st.markdown(f"### {icon} {name}")
    st.write(detail)

st.divider()
st.caption(f"检查时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
st.caption("如果这里能正常显示，说明 Streamlit 页面本身已经执行；再根据各项 ❌ 定位具体数据源问题。")
