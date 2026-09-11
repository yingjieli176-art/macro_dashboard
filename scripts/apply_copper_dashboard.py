from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"

IMPORT_ANCHOR = "from macro_platform.us_equity_risk import load_vixeq_snapshot\n"
COPPER_IMPORT = "from macro_platform.copper import build_comex_copper_figure, build_lme_copper_figure\n"
RENDER_MARKER = "\nst.markdown('<div id=\"macro-charts\" class=\"section-anchor\"></div><div class=\"section-kicker\">MACRO CHARTS</div>', unsafe_allow_html=True)"

COPPER_SECTION = r'''
    st.markdown(
        '<div class="section-kicker">INDUSTRIAL METALS · COPPER</div>'
        '<div class="section-title">12. COMEX Copper Inventory & Price</div>'
        '<div class="section-description">COMEX total warehouse inventory (L) · HG copper futures price (R1)</div>',
        unsafe_allow_html=True,
    )
    comex_copper_range = st.radio(
        "时间范围", RANGES, horizontal=True, index=1,
        key="comex_copper_range", label_visibility="collapsed",
    )
    st.plotly_chart(
        build_comex_copper_figure(comex_copper_range),
        use_container_width=True,
        config=PLOTLY_CONFIG,
    )
    st.markdown(
        '<div class="mini-description"><b>读取方法：</b>左轴看 COMEX 交易所认可仓库的铜总库存（千吨，kt），右轴看 HG 铜期货美元/磅。'
        '库存下降而价格上升通常代表可见库存趋紧；库存上升而价格走弱通常代表可见供给更宽松。库存与价格频率/发布时间不同，不对缺失日做线性插值。</div>',
        unsafe_allow_html=True,
    )
    add_sources([
        ("CME · COMEX Warehouse & Depository Stocks", "https://www.cmegroup.com/solutions/clearing/operations-and-deliveries/nymex-delivery-notices.html"),
        ("COCHILCO · Copper Inventories", "https://boletin.cochilco.cl/estadisticas/inventarios.asp"),
        ("Yahoo Finance · COMEX Copper HG=F", "https://finance.yahoo.com/quote/HG=F/history/"),
    ])
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)

    st.markdown(
        '<div class="section-title">13. LME Copper Inventory & Price</div>'
        '<div class="section-description">LME copper warehouse stock (L) · Cash / 3M copper prices (R1)</div>',
        unsafe_allow_html=True,
    )
    lme_copper_range = st.radio(
        "时间范围", RANGES, horizontal=True, index=1,
        key="lme_copper_range", label_visibility="collapsed",
    )
    st.plotly_chart(
        build_lme_copper_figure(lme_copper_range),
        use_container_width=True,
        config=PLOTLY_CONFIG,
    )
    st.markdown(
        '<div class="mini-description"><b>读取方法：</b>左轴为 LME 可见仓库铜库存（千吨，kt）；右轴同时显示 Cash 与 3M 铜价（美元/吨）。'
        'Cash 高于 3M 为现货升水/反向市场特征之一，常与近端供给偏紧同时出现；库存只是交易所可见库存，不等于全球全部铜库存。</div>',
        unsafe_allow_html=True,
    )
    add_sources([
        ("LME Copper", "https://www.lme.com/copper"),
        ("LME Warehouse & Stocks Reports", "https://www.lme.com/Market-data/Reports-and-data/Warehouse-and-stocks-reports"),
        ("Westmetall · LME Copper Daily Table", "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Cu_cash"),
        ("COCHILCO · Copper Inventories", "https://boletin.cochilco.cl/estadisticas/inventarios.asp"),
    ])
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)
'''


def main() -> None:
    text = APP.read_text(encoding="utf-8")

    if COPPER_IMPORT not in text:
        if IMPORT_ANCHOR not in text:
            raise RuntimeError("app import anchor not found")
        text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + COPPER_IMPORT, 1)

    if "12. COMEX Copper Inventory & Price" not in text:
        if RENDER_MARKER not in text:
            raise RuntimeError("macro render marker not found")
        text = text.replace(RENDER_MARKER, "\n" + COPPER_SECTION.rstrip() + RENDER_MARKER, 1)

    APP.write_text(text, encoding="utf-8")
    print("copper dashboard integration applied")


if __name__ == "__main__":
    main()
