from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing block: {label}")
    return text.replace(old, new, 1)


def main() -> None:
    text = APP.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '        add_line(fig, data, "ETHBTC", "ETH/BTC", 2.2, "dash", "y2", "")\n'
        '        add_line(fig, data, "BTC_VOL_30D", "BTC 30D Realized Vol", 2.2, "dot", "y3", "%")\n'
        '        fig.update_layout(\n'
        '            yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.87),\n'
        '            yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.98),\n'
        '        )',
        '        add_line(fig, data, "ETHBTC", "ETH/BTC (R1)", 2.2, "dash", "y2", "")\n'
        '        add_line(fig, data, "BTC_VOL_30D", "BTC 30D Realized Vol (R2)", 2.2, "dot", "y3", "%")\n'
        '        fig.update_layout(\n'
        '            yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.925),\n'
        '            yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.99),\n'
        '        )',
        "rebased legend and positions",
    )

    text = replace_once(
        text,
        '            margin=dict(l=62, r=150, t=72, b=34, pad=2),\n'
        '            legend=dict(y=1.09, x=0.01),\n'
        '            xaxis=dict(domain=[0.0, 0.84]),\n'
        '            yaxis=dict(title="BTC / ETH · Rebased 100", tickformat=".1f"),\n'
        '            yaxis2=dict(title="R1 · ETH/BTC", overlaying="y", side="right", anchor="free", position=0.87, showgrid=False, fixedrange=True, tickformat=".4f"),\n'
        '            yaxis3=dict(title="R2 · BTC 30D Vol (%)", overlaying="y", side="right", anchor="free", position=0.98, showgrid=False, fixedrange=True, tickformat=".0f"),',
        '            margin=dict(l=62, r=92, t=72, b=34, pad=2),\n'
        '            legend=dict(y=1.09, x=0.01),\n'
        '            xaxis=dict(domain=[0.0, 0.91]),\n'
        '            yaxis=dict(title="BTC / ETH · Rebased 100", tickformat=".1f"),\n'
        '            yaxis2=dict(title="", overlaying="y", side="right", anchor="free", position=0.925, showgrid=False, fixedrange=True, tickformat=".4f", tickfont=dict(size=9), ticks="outside", ticklen=3),\n'
        '            yaxis3=dict(title="", overlaying="y", side="right", anchor="free", position=0.99, showgrid=False, fixedrange=True, tickformat=".0f", tickfont=dict(size=9), ticks="outside", ticklen=3),',
        "rebased compact axes",
    )

    text = replace_once(
        text,
        '    add_line(fig, data, "ETH", "ETH", 2.6, None, "y2", " USD")\n'
        '    add_line(fig, data, "ETHBTC", "ETH/BTC", 2.2, "dash", "y3", "")\n'
        '    add_line(fig, data, "BTC_VOL_30D", "BTC 30D Realized Vol", 2.2, "dot", "y4", "%")\n'
        '    fig.update_layout(\n'
        '        yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.78),\n'
        '        yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.88),\n'
        '        yaxis4=dict(overlaying="y", side="right", anchor="free", position=0.98),\n'
        '    )',
        '    add_line(fig, data, "ETH", "ETH (R1)", 2.6, None, "y2", " USD")\n'
        '    add_line(fig, data, "ETHBTC", "ETH/BTC (R2)", 2.2, "dash", "y3", "")\n'
        '    add_line(fig, data, "BTC_VOL_30D", "BTC 30D Realized Vol (R3)", 2.2, "dot", "y4", "%")\n'
        '    fig.update_layout(\n'
        '        yaxis2=dict(overlaying="y", side="right", anchor="free", position=0.86),\n'
        '        yaxis3=dict(overlaying="y", side="right", anchor="free", position=0.93),\n'
        '        yaxis4=dict(overlaying="y", side="right", anchor="free", position=0.99),\n'
        '    )',
        "raw legend and positions",
    )

    text = replace_once(
        text,
        '        margin=dict(l=72, r=220, t=72, b=34, pad=2),\n'
        '        legend=dict(y=1.09, x=0.01),\n'
        '        xaxis=dict(domain=[0.0, 0.75]),\n'
        '        yaxis=dict(title="BTC · USD", tickformat=",.0f"),\n'
        '        yaxis2=dict(title="R1 · ETH · USD", overlaying="y", side="right", anchor="free", position=0.78, showgrid=False, fixedrange=True, tickformat=",.0f"),\n'
        '        yaxis3=dict(title="R2 · ETH/BTC", overlaying="y", side="right", anchor="free", position=0.88, showgrid=False, fixedrange=True, tickformat=".4f"),\n'
        '        yaxis4=dict(title="R3 · BTC 30D Vol (%)", overlaying="y", side="right", anchor="free", position=0.98, showgrid=False, fixedrange=True, tickformat=".0f"),',
        '        margin=dict(l=72, r=132, t=72, b=34, pad=2),\n'
        '        legend=dict(y=1.09, x=0.01),\n'
        '        xaxis=dict(domain=[0.0, 0.84]),\n'
        '        yaxis=dict(title="BTC · USD", tickformat=",.0f"),\n'
        '        yaxis2=dict(title="", overlaying="y", side="right", anchor="free", position=0.86, showgrid=False, fixedrange=True, tickformat=",.0f", tickfont=dict(size=9), ticks="outside", ticklen=3),\n'
        '        yaxis3=dict(title="", overlaying="y", side="right", anchor="free", position=0.93, showgrid=False, fixedrange=True, tickformat=".4f", tickfont=dict(size=9), ticks="outside", ticklen=3),\n'
        '        yaxis4=dict(title="", overlaying="y", side="right", anchor="free", position=0.99, showgrid=False, fixedrange=True, tickformat=".0f", tickfont=dict(size=9), ticks="outside", ticklen=3),',
        "raw compact axes",
    )

    text = replace_once(
        text,
        "    '1. BTC / ETH：比特币与以太坊美元价格；默认 Rebased 100 以可视区间首个有效值归一到 100，重点比较相对强弱。<br>'\n"
        "    '2. ETH/BTC（R1）：ETH 价格除以 BTC 价格；上升表示 ETH 相对 BTC 走强，下降表示资金表现更偏向 BTC。<br>'\n"
        "    '3. BTC 30D Realized Vol（R2/R3）：基于 BTC 日收益率计算的 30 日年化实际波动率，反映已经发生的价格波动强度，不是期权隐含波动率。<br><br>'",
        "    '1. BTC / ETH：比特币与以太坊美元价格；默认 Rebased 100 共用左轴。Raw 模式中 BTC 使用左轴、ETH 使用 R1。<br>'\n"
        "    '2. ETH/BTC：ETH 价格除以 BTC 价格；Rebased 100 使用 R1，Raw 使用 R2。上升表示 ETH 相对 BTC 走强。<br>'\n"
        "    '3. BTC 30D Realized Vol：BTC 日收益率计算的 30 日年化实际波动率；Rebased 100 使用 R2，Raw 使用 R3，不是期权隐含波动率。<br><br>'",
        "description axis notes",
    )

    APP.write_text(text, encoding="utf-8")
    print("crypto axes tightened")


if __name__ == "__main__":
    main()
