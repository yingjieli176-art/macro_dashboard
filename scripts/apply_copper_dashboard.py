from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"

IMPORT_ANCHOR = "from macro_platform.us_equity_risk import load_vixeq_snapshot\n"
LEGACY_COPPER_IMPORT = "from macro_platform.copper import build_comex_copper_figure, build_lme_copper_figure\n"
COPPER_IMPORT = "from macro_platform.copper import build_copper_flow_spread_figure\n"
RENDER_MARKER = "\nst.markdown('<div id=\"macro-charts\" class=\"section-anchor\"></div><div class=\"section-kicker\">MACRO CHARTS</div>', unsafe_allow_html=True)"
OLD_SECTION_TITLE = "12. COMEX Copper Inventory & Price"
COMBINED_SECTION_TITLE = "12. Copper Flow & COMEX–LME Spread"

COPPER_SECTION = r'''
    st.markdown(
        '<div class="section-kicker">INDUSTRIAL METALS · COPPER</div>'
        '<div class="section-title">12. Copper Flow & COMEX–LME Spread</div>'
        '<div class="section-description">LME / COMEX inventories (L) · normalized copper prices (R1) · COMEX−LME 3M spread (R2)</div>',
        unsafe_allow_html=True,
    )
    copper_flow_range = st.radio(
        "时间范围", RANGES, horizontal=True, index=1,
        key="copper_flow_spread_range", label_visibility="collapsed",
    )
    st.plotly_chart(
        build_copper_flow_spread_figure(copper_flow_range),
        use_container_width=True,
        config=PLOTLY_CONFIG,
    )
    st.markdown(
        '<div class="mini-description"><b>读取方法：</b>COMEX 与 LME 库存放在同一左轴（千吨，kt），直接观察交易所可见库存的相对迁移；'
        'COMEX HG 先按 1 公吨 = 2,204.6226 磅换算为 USD/t，再与 LME 3M 放在同一价格轴；R2 直接显示 COMEX−LME 3M 价差。'
        '若 COMEX 库存上升、LME 库存下降且价差同步走阔，通常可视作库存/交割需求向美国端迁移的信号；反向组合则相反。'
        '该价差使用 HG 近月连续代理与 LME 3M，期限并非严格匹配，因此用于方向与压力监测，不是可直接执行的无风险套利报价。</div>',
        unsafe_allow_html=True,
    )
    add_sources([
        ("CME · COMEX Warehouse & Depository Stocks", "https://www.cmegroup.com/solutions/clearing/operations-and-deliveries/nymex-delivery-notices.html"),
        ("Yahoo Finance · COMEX Copper HG=F", "https://finance.yahoo.com/quote/HG=F/history/"),
        ("LME Copper", "https://www.lme.com/copper"),
        ("LME Warehouse & Stocks Reports", "https://www.lme.com/Market-data/Reports-and-data/Warehouse-and-stocks-reports"),
        ("Westmetall · LME Copper Daily Table", "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Cu_cash"),
        ("COCHILCO · Copper Inventories", "https://boletin.cochilco.cl/estadisticas/inventarios.asp"),
    ])
    st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)
'''


def _replace_copper_section(text: str) -> str:
    if COMBINED_SECTION_TITLE in text:
        return text

    marker_index = text.find(RENDER_MARKER)
    if marker_index < 0:
        raise RuntimeError("macro render marker not found")

    if OLD_SECTION_TITLE in text:
        section_start_marker = (
            "    st.markdown(\n"
            "        '<div class=\"section-kicker\">INDUSTRIAL METALS · COPPER</div>'"
        )
        section_start = text.find(section_start_marker)
        if section_start < 0 or section_start > marker_index:
            raise RuntimeError("legacy copper section start not found")
        return text[:section_start] + COPPER_SECTION.rstrip() + text[marker_index:]

    return text[:marker_index] + "\n" + COPPER_SECTION.rstrip() + text[marker_index:]


def main() -> None:
    text = APP.read_text(encoding="utf-8")

    if LEGACY_COPPER_IMPORT in text:
        text = text.replace(LEGACY_COPPER_IMPORT, COPPER_IMPORT, 1)
    elif COPPER_IMPORT not in text:
        if IMPORT_ANCHOR not in text:
            raise RuntimeError("app import anchor not found")
        text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + COPPER_IMPORT, 1)

    text = _replace_copper_section(text)

    APP.write_text(text, encoding="utf-8")
    print("combined copper dashboard integration applied")


if __name__ == "__main__":
    main()
