from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
HK = ROOT / "macro_platform" / "hk_liquidity.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_hk() -> None:
    text = HK.read_text(encoding="utf-8")

    # Match charts 1-4: titles live outside Plotly. The chart canvas only owns
    # axes, traces and the legend, so the legend can never collide with a title.
    text = replace_once(
        text,
        '            title=dict(text=f"{title} · latest {latest_text}", x=0.01, xanchor="left", font=dict(size=16)),\n',
        '',
        'remove internal Plotly title',
    )

    # Remove all later title overrides. Freshness remains represented by the
    # underlying series and parameter/source text, rather than competing for
    # the same top margin as the legend.
    title_override_lines = [
        '        money.update_layout(title_text=f"5-1. HK Money Supply & Market Pulse · market latest {market_latest}")\n',
        '        balance.update_layout(title_text=f"{balance_label} · latest {banking_latest}")\n',
        '        funding.update_layout(title_text=f"{funding_label} · latest {funding_latest}")\n',
        '        fx.update_layout(title_text=f"5-4. USD/HKD Convertibility Band & Market · FX latest {fx_latest}")\n',
    ]
    for line in title_override_lines:
        if line not in text:
            raise RuntimeError(f"missing title override: {line.strip()}")
        text = text.replace(line, '', 1)

    # Renumber the internal labels too, so future maintenance does not re-create
    # the old 5-1/5-2/5-3/5-4 naming convention.
    replacements = {
        '"5-1. HK Money Supply & Market Pulse"': '"5. HK Money Supply & Market Pulse"',
        '"5-2. Daily Banking-system Liquidity"': '"6. Daily Banking-system Liquidity"',
        '"5-2. Banking-system Liquidity · monthly fallback"': '"6. Banking-system Liquidity · monthly fallback"',
        '"5-3. HKD Funding · Daily"': '"7. HKD Funding · Daily"',
        '"5-3. HKD Funding · monthly fallback"': '"7. HKD Funding · monthly fallback"',
        '"5-4. USD/HKD Convertibility Band & Market"': '"8. USD/HKD Convertibility Band & Market"',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    # The title argument is intentionally retained for backwards compatibility,
    # but is no longer rendered inside Plotly.
    HK.write_text(text, encoding="utf-8")


def patch_app() -> None:
    text = APP.read_text(encoding="utf-8")

    old = '''    st.markdown('<div class="section-title">5. Hong Kong Liquidity</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-description">Money supply / HKEX price & HSTECH index / Daily banking liquidity & EFBN / HIBOR / USD-HKD / 7.75–7.85 LERS band</div>', unsafe_allow_html=True)
    # Build the full data set once; each 5-x panel controls only its own visible X-axis window.
    hk_figures = build_fig5("5Y")
    hk_range_keys = [
        "hk_5_1_range",
        "hk_5_2_range",
        "hk_5_3_range",
        "hk_5_4_range",
    ]
    for hk_index, hk_figure in enumerate(hk_figures):
        hk_range = st.radio(
            "时间范围",
            RANGES,
            horizontal=True,
            index=1,
            key=hk_range_keys[hk_index],
            label_visibility="collapsed",
        )
        st.plotly_chart(
            apply_hk_chart_range(hk_figure, hk_range),
            use_container_width=True,
            config=PLOTLY_CONFIG,
        )
        show_hk_parameter_description(hk_index)
        if hk_index < len(hk_figures) - 1:
            st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)
    add_sources([
        ("HKMA Monetary Statistics", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/financial/monetary-statistics/"),
        ("HKMA Daily Interbank Liquidity", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/daily-monetary-statistics/daily-figures-interbank-liquidity/"),
        ("HKMA Daily Monetary Base", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/daily-monetary-statistics/daily-figures-monetary-base/"),
        ("HKMA Open API", "https://apidocs.hkma.gov.hk/"),
        ("Hang Seng Indexes · HSTECH", "https://www.hsi.com.hk/eng/indexes/all-indexes/hstech"),
        ("FRED DEXHKUS · Daily USD/HKD", "https://fred.stlouisfed.org/series/DEXHKUS"),
        ("Yahoo Finance Market History", "https://finance.yahoo.com/"),
    ])
'''

    new = '''    st.markdown('<div class="section-kicker">HONG KONG LIQUIDITY</div>', unsafe_allow_html=True)
    # Build the full Hong Kong data set once. Charts 5-8 then behave exactly
    # like charts 1-4: external title, description, independent range control,
    # chart, local parameter notes, local sources, divider.
    hk_figures = build_fig5("5Y")
    hk_configs = [
        (
            '<div class="section-title">5. HK Money Supply & Market Pulse</div>',
            '<div class="section-description">HKD M2 / M3 / Monetary Base MoM · HKEX Price (R) · HSTECH Index (R)</div>',
            "hk_5_range",
            [
                ("HKMA Monetary Statistics", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/financial/monetary-statistics/"),
                ("Hang Seng Indexes · HSTECH", "https://www.hsi.com.hk/eng/indexes/all-indexes/hstech"),
                ("Yahoo Finance Market History", "https://finance.yahoo.com/"),
            ],
        ),
        (
            '<div class="section-title">6. Banking-system Liquidity</div>',
            '<div class="section-description">Aggregate Balance · Outstanding EFBN (R) · EFBN Held by Licensed Banks (R)</div>',
            "hk_6_range",
            [
                ("HKMA Monetary Base", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/monetary-operation/monetary-base-endperiod/"),
                ("HKMA Daily Interbank Liquidity", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/daily-monetary-statistics/daily-figures-interbank-liquidity/"),
            ],
        ),
        (
            '<div class="section-title">7. HKD Funding</div>',
            '<div class="section-description">O/N HIBOR · 3M HIBOR · HKMA Base Rate · O/N−3M Spread (R)</div>',
            "hk_7_range",
            [
                ("HKMA Open API", "https://apidocs.hkma.gov.hk/"),
                ("HKMA Base Rate", "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/monetary-operation/disc-win-liquid-adj-win-rates-endperiod/"),
            ],
        ),
        (
            '<div class="section-title">8. USD/HKD Convertibility Band & Market</div>',
            '<div class="section-description">USD/HKD · Strong-side 7.75 · Center 7.80 · Weak-side 7.85 · HKEX / HSTECH (R)</div>',
            "hk_8_range",
            [
                ("HKMA Linked Exchange Rate System", "https://www.hkma.gov.hk/eng/key-functions/money/linked-exchange-rate-system/"),
                ("Yahoo Finance Market History", "https://finance.yahoo.com/"),
                ("Hang Seng Indexes · HSTECH", "https://www.hsi.com.hk/eng/indexes/all-indexes/hstech"),
            ],
        ),
    ]

    for hk_index, (title, description, key, sources) in enumerate(hk_configs):
        st.markdown(title, unsafe_allow_html=True)
        st.markdown(description, unsafe_allow_html=True)
        hk_range = st.radio(
            "时间范围",
            RANGES,
            horizontal=True,
            index=1,
            key=key,
            label_visibility="collapsed",
        )
        st.plotly_chart(
            apply_hk_chart_range(hk_figures[hk_index], hk_range),
            use_container_width=True,
            config=PLOTLY_CONFIG,
        )
        show_hk_parameter_description(hk_index)
        add_sources(sources)
        st.markdown('<div class="chart-divider"></div>', unsafe_allow_html=True)
'''

    text = replace_once(text, old, new, 'Hong Kong chart render block')
    APP.write_text(text, encoding="utf-8")


def main() -> None:
    patch_hk()
    patch_app()
    print("renumbered Hong Kong charts 5-8 and aligned layout with charts 1-4")


if __name__ == "__main__":
    main()
