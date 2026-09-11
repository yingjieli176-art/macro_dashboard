from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
HK = ROOT / "macro_platform" / "hk_liquidity.py"


def rep(text: str, old: str, new: str, label: str, count: int = 1) -> str:
    found = text.count(old)
    if found < count:
        raise RuntimeError(f"{label}: expected at least {count}, found {found}")
    return text.replace(old, new, count)


def update_app() -> None:
    text = APP.read_text(encoding="utf-8")

    text = rep(text, '    base_right = 76 if has_secondary else 20', '    base_right = 60 if has_secondary else 20', 'shared right margin')

    # Charts 2-3: right-axis notation belongs in the series label, not in a long axis title.
    text = rep(text, '10Y Real (R)', '10Y Real (R1)', 'chart2 real labels', 2)
    text = rep(text, '10Y Breakeven (R)', '10Y Breakeven (R1)', 'chart2 breakeven labels', 2)
    text = rep(text, 'yaxis2=dict(title="Real / Breakeven (%)", overlaying="y", side="right", anchor="free", position=1.0, showgrid=False, zeroline=False, fixedrange=True, automargin=True, tickfont=dict(size=9))', 'yaxis2=dict(title="", overlaying="y", side="right", anchor="free", position=0.99, showgrid=False, zeroline=False, fixedrange=True, automargin=False, tickfont=dict(size=9), ticks="outside", ticklen=3)', 'chart2 axis')

    text = rep(text, '10Y−2Y (R)', '10Y−2Y (R1)', 'chart3 10y2y labels', 4)
    text = rep(text, '10Y−3M (R)', '10Y−3M (R1)', 'chart3 10y3m labels', 4)
    text = rep(text, 'yaxis2=dict(title="Spread (%)", overlaying="y", side="right", anchor="free", position=1.0, showgrid=False, zeroline=True, zerolinecolor="#9ca3af", fixedrange=True, automargin=True, tickfont=dict(size=9))', 'yaxis2=dict(title="", overlaying="y", side="right", anchor="free", position=0.99, showgrid=False, zeroline=True, zerolinecolor="#9ca3af", fixedrange=True, automargin=False, tickfont=dict(size=9), ticks="outside", ticklen=3)', 'chart3 axis')

    # Chart 4: two compact tick columns; R1/R2 are carried by legend labels.
    text = rep(text, '"WRESBAL", "Reserve Balances", 2.4, yaxis="y2"', '"WRESBAL", "Reserve Balances (R1)", 2.4, yaxis="y2"', 'chart4 reserve legend')
    text = rep(text, 'tga_name = "TGA · Weekly fallback" if tga_is_fallback else "TGA"', 'tga_name = "TGA · Weekly fallback (R1)" if tga_is_fallback else "TGA (R1)"', 'chart4 tga legend')
    text = rep(text, '"RRPONTSYD", "ON RRP", 2.2, "dot", "y3", " B"', '"RRPONTSYD", "ON RRP (R2)", 2.2, "dot", "y3", " B"', 'chart4 rrp legend')
    axis_pair = 'yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.86),\n        yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.97),'
    compact_pair = 'yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.925),\n        yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.99),'
    text = rep(text, axis_pair, compact_pair, 'chart4 positions')
    text = rep(text, 'margin=dict(l=64, r=164, t=72, b=34, pad=2)', 'margin=dict(l=64, r=92, t=72, b=34, pad=2)', 'chart4 margin')
    text = rep(text, 'xaxis=dict(domain=[0.0, 0.82])', 'xaxis=dict(domain=[0.0, 0.91])', 'chart4 domain')
    text = rep(text, 'title="R1 · Reserve / TGA · USD T",\n            overlaying="y", side="right", anchor="free", position=0.86,\n            showgrid=False, zeroline=False, fixedrange=True,\n            tickformat=".1f", tickfont=dict(size=10),', 'title="",\n            overlaying="y", side="right", anchor="free", position=0.925,\n            showgrid=False, zeroline=False, fixedrange=True,\n            tickformat=".1f", tickfont=dict(size=9), ticks="outside", ticklen=3,', 'chart4 r1 axis')
    text = rep(text, 'title="R2 · ON RRP · USD B",\n            overlaying="y", side="right", anchor="free", position=0.97,\n            showgrid=False, zeroline=True, zerolinecolor="#94a3b8",\n            zerolinewidth=1, fixedrange=True, tickformat=".0f",\n            tickfont=dict(size=10),', 'title="",\n            overlaying="y", side="right", anchor="free", position=0.99,\n            showgrid=False, zeroline=True, zerolinecolor="#94a3b8",\n            zerolinewidth=1, fixedrange=True, tickformat=".0f",\n            tickfont=dict(size=9), ticks="outside", ticklen=3,', 'chart4 r2 axis')

    # Chart 9: same two-axis convention.
    text = rep(text, axis_pair, compact_pair, 'chart9 positions')
    text = rep(text, 'margin=dict(l=62, r=144, t=68, b=36, pad=2)', 'margin=dict(l=62, r=92, t=68, b=36, pad=2)', 'chart9 margin')
    text = rep(text, 'xaxis=dict(domain=[0.0, 0.84])', 'xaxis=dict(domain=[0.0, 0.91])', 'chart9 domain')
    text = rep(text, 'title="R1 · S&P 500",\n            overlaying="y", side="right", anchor="free", position=0.86,\n            showgrid=False, zeroline=False, fixedrange=True, tickfont=dict(size=10),', 'title="",\n            overlaying="y", side="right", anchor="free", position=0.925,\n            showgrid=False, zeroline=False, fixedrange=True, tickfont=dict(size=9), ticks="outside", ticklen=3,', 'chart9 r1 axis')
    text = rep(text, 'title="R2 · VIX3M−VIX",\n            overlaying="y", side="right", anchor="free", position=0.97,\n            showgrid=False, zeroline=True, zerolinecolor="#94a3b8",\n            zerolinewidth=1, fixedrange=True, tickfont=dict(size=10),', 'title="",\n            overlaying="y", side="right", anchor="free", position=0.99,\n            showgrid=False, zeroline=True, zerolinecolor="#94a3b8",\n            zerolinewidth=1, fixedrange=True, tickfont=dict(size=9), ticks="outside", ticklen=3,', 'chart9 r2 axis')

    # Chart 10: mirror the compact convention already used by Chart 11.
    text = rep(text, '"GoldSilverRatio", "Gold/Silver Ratio", 2.2, "dash", "y2", "x"', '"GoldSilverRatio", "Gold/Silver Ratio (R1)", 2.2, "dash", "y2", "x"', 'metals rebased ratio')
    text = rep(text, '"GVZCLS", "Gold Volatility · GVZ", 2.2, "dot", "y3", ""', '"GVZCLS", "Gold Volatility · GVZ (R2)", 2.2, "dot", "y3", ""', 'metals rebased gvz')
    text = rep(text, 'yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.87),\n            yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.98),', 'yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.925),\n            yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.99),', 'metals rebased positions')
    text = rep(text, 'margin=dict(l=62, r=150, t=72, b=34, pad=2)', 'margin=dict(l=62, r=92, t=72, b=34, pad=2)', 'metals rebased margin')
    text = rep(text, 'xaxis=dict(domain=[0.0, 0.84])', 'xaxis=dict(domain=[0.0, 0.91])', 'metals rebased domain')
    text = rep(text, 'yaxis2=dict(title="R1 · Gold/Silver Ratio", overlaying="y", side="right", anchor="free", position=0.87, showgrid=False, fixedrange=True, tickformat=".1f")', 'yaxis2=dict(title="", overlaying="y", side="right", anchor="free", position=0.925, showgrid=False, fixedrange=True, tickformat=".1f", tickfont=dict(size=9), ticks="outside", ticklen=3)', 'metals rebased r1')
    text = rep(text, 'yaxis3=dict(title="R2 · GVZ", overlaying="y", side="right", anchor="free", position=0.98, showgrid=False, fixedrange=True, tickformat=".1f")', 'yaxis3=dict(title="", overlaying="y", side="right", anchor="free", position=0.99, showgrid=False, fixedrange=True, tickformat=".1f", tickfont=dict(size=9), ticks="outside", ticklen=3)', 'metals rebased r2')

    text = rep(text, '"Silver", "Silver", 2.5, None, "y2", " USD/oz"', '"Silver", "Silver (R1)", 2.5, None, "y2", " USD/oz"', 'metals raw silver')
    text = rep(text, '"GoldSilverRatio", "Gold/Silver Ratio", 2.2, "dash", "y3", "x"', '"GoldSilverRatio", "Gold/Silver Ratio (R2)", 2.2, "dash", "y3", "x"', 'metals raw ratio')
    text = rep(text, '"GVZCLS", "Gold Volatility · GVZ", 2.2, "dot", "y4", ""', '"GVZCLS", "Gold Volatility · GVZ (R3)", 2.2, "dot", "y4", ""', 'metals raw gvz')
    text = rep(text, 'yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.78),\n        yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.88),\n        yaxis4=dict(overlaying="y", side="right", anchor="free", position=0.98),', 'yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.86),\n        yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.93),\n        yaxis4=dict(overlaying="y", side="right", anchor="free", position=0.99),', 'metals raw positions')
    text = rep(text, 'margin=dict(l=68, r=220, t=72, b=34, pad=2)', 'margin=dict(l=68, r=132, t=72, b=34, pad=2)', 'metals raw margin')
    text = rep(text, 'xaxis=dict(domain=[0.0, 0.75])', 'xaxis=dict(domain=[0.0, 0.84])', 'metals raw domain')
    text = rep(text, 'yaxis2=dict(title="R1 · Silver · USD/oz", overlaying="y", side="right", anchor="free", position=0.78, showgrid=False, fixedrange=True, tickformat=".1f")', 'yaxis2=dict(title="", overlaying="y", side="right", anchor="free", position=0.86, showgrid=False, fixedrange=True, tickformat=".1f", tickfont=dict(size=9), ticks="outside", ticklen=3)', 'metals raw r1')
    text = rep(text, 'yaxis3=dict(title="R2 · Gold/Silver", overlaying="y", side="right", anchor="free", position=0.88, showgrid=False, fixedrange=True, tickformat=".1f")', 'yaxis3=dict(title="", overlaying="y", side="right", anchor="free", position=0.93, showgrid=False, fixedrange=True, tickformat=".1f", tickfont=dict(size=9), ticks="outside", ticklen=3)', 'metals raw r2')
    text = rep(text, 'yaxis4=dict(title="R3 · GVZ", overlaying="y", side="right", anchor="free", position=0.98, showgrid=False, fixedrange=True, tickformat=".1f")', 'yaxis4=dict(title="", overlaying="y", side="right", anchor="free", position=0.99, showgrid=False, fixedrange=True, tickformat=".1f", tickfont=dict(size=9), ticks="outside", ticklen=3)', 'metals raw r3')

    # Remaining visible captions / methodology that still used generic (R).
    text = rep(text, 'Aggregate Balance · Outstanding EFBN (R) · EFBN Held by Licensed Banks (R)', 'Aggregate Balance · Outstanding EFBN (R1) · EFBN Held by Licensed Banks (R1)', 'chart6 subtitle')
    text = rep(text, 'O/N HIBOR · 3M HIBOR · HKMA Base Rate · O/N−3M Spread (R)', 'O/N HIBOR · 3M HIBOR · HKMA Base Rate · O/N−3M Spread (R1)', 'chart7 subtitle')
    text = rep(text, 'O/N−3M Spread（R）：', 'O/N−3M Spread（R1）：', 'generic hk parameter r1')
    text = rep(text, 'Outstanding EFBN（R）：', 'Outstanding EFBN（R1）：', 'hk banking desc efbn')
    text = rep(text, 'EFBN Held by Licensed Banks（R）：', 'EFBN Held by Licensed Banks（R1）：', 'hk banking desc held')

    APP.write_text(text, encoding="utf-8")


def update_hk() -> None:
    text = HK.read_text(encoding="utf-8")
    text = rep(text, 'margin=dict(l=62, r=82 if right_axis else 28, t=96, b=40, pad=2)', 'margin=dict(l=62, r=64 if right_axis else 28, t=96, b=40, pad=2)', 'hk shared right margin')

    for old, new, label in (
        ('"Tencent (R)"', '"Tencent (R1)"', 'hk tencent rebased'),
        ('"HKEX (R)"', '"HKEX (R1)"', 'hk hkex rebased'),
        ('"HSTECH (R)"', '"HSTECH (R1)"', 'hk hstech rebased'),
        ('"HSI (R)"', '"HSI (R1)"', 'hk hsi rebased'),
    ):
        text = rep(text, old, new, label, 2)

    raw_block = '''        money.update_layout(
            margin=dict(l=62, r=142, t=96, b=40, pad=2),
            xaxis=dict(domain=[0.0, 0.84]),
            yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.86, title="R1 · HKD Price", showgrid=False, fixedrange=True, tickfont=dict(size=10)),
            yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.97, title="R2 · Index Level", showgrid=False, fixedrange=True, tickfont=dict(size=10)),
        )'''
    raw_new = '''        money.update_layout(
            margin=dict(l=62, r=92, t=96, b=40, pad=2),
            xaxis=dict(domain=[0.0, 0.91]),
            yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.925, title="", showgrid=False, fixedrange=True, tickfont=dict(size=9), ticks="outside", ticklen=3),
            yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.99, title="", showgrid=False, fixedrange=True, tickfont=dict(size=9), ticks="outside", ticklen=3),
        )'''
    text = rep(text, raw_block, raw_new, 'hk chart5 raw block')

    fx_raw_block = raw_block.replace('money.update_layout', 'fx.update_layout')
    fx_raw_new = raw_new.replace('money.update_layout', 'fx.update_layout')
    text = rep(text, fx_raw_block, fx_raw_new, 'hk chart8 raw block')

    rebased_block = '''        money.update_layout(
            margin=dict(l=62, r=94, t=96, b=40, pad=2),
            xaxis=dict(domain=[0.0, 0.91]),
            yaxis2=dict(title="Market · Rebased 100", showgrid=False, fixedrange=True),
        )'''
    rebased_new = '''        money.update_layout(
            margin=dict(l=62, r=64, t=96, b=40, pad=2),
            xaxis=dict(domain=[0.0, 0.95]),
            yaxis2=dict(title="", overlaying="y", side="right", anchor="free", position=0.99, showgrid=False, fixedrange=True, tickfont=dict(size=9), ticks="outside", ticklen=3),
        )'''
    text = rep(text, rebased_block, rebased_new, 'hk chart5 rebased block')
    text = rep(text, rebased_block.replace('money.update_layout', 'fx.update_layout'), rebased_new.replace('money.update_layout', 'fx.update_layout'), 'hk chart8 rebased block')

    text = rep(text, 'title_text="R1 · HKD Price" if raw_market else "Market · Rebased 100", secondary_y=True,', 'title_text="", secondary_y=True,', 'hk market secondary title', 2)

    text = rep(text, '"Outstanding EFBN (R)"', '"Outstanding EFBN (R1)"', 'hk chart6 efbn')
    text = rep(text, '"EFBN Held by Licensed Banks (R)"', '"EFBN Held by Licensed Banks (R1)"', 'hk chart6 held')
    text = rep(text, 'title_text="EFBN (HK$ bn)", secondary_y=True,\n        showgrid=False, zeroline=False, fixedrange=True,', 'title_text="", secondary_y=True,\n        showgrid=False, zeroline=False, fixedrange=True, tickfont=dict(size=9), ticks="outside", ticklen=3,', 'hk chart6 axis')

    # Replace both the legacy and current funding labels/titles so every path follows R1.
    text = rep(text, 'O/N−3M Spread (R)', 'O/N−3M Spread (R1)', 'hk funding labels', 2)
    text = rep(text, 'title_text="Spread (bp)"', 'title_text=""', 'hk funding titles', 2)

    HK.write_text(text, encoding="utf-8")


def main() -> None:
    update_app()
    update_hk()
    print("right-axis notation unified v2")


if __name__ == "__main__":
    main()
