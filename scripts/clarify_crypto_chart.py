from pathlib import Path

path = Path("app.py")
text = path.read_text(encoding="utf-8")

replacements = [
    (
        '        add_line(fig, data, "BTC_R100", "BTC · R100", 2.9, unit="")\n'
        '        add_line(fig, data, "ETH_R100", "ETH · R100", 2.6, unit="")\n'
        '        add_line(fig, data, "ETHBTC", "ETH/BTC (R1)", 2.2, "dash", "y2", "")\n'
        '        add_line(fig, data, "BTC_VOL_30D", "BTC 30D Realized Vol (R2)", 2.2, "dot", "y3", "%")',
        '        add_line(fig, data, "BTC_R100", "BTC · 起点100", 2.9, unit="")\n'
        '        add_line(fig, data, "ETH_R100", "ETH · 起点100", 2.6, unit="")\n'
        '        add_line(fig, data, "ETHBTC", "ETH/BTC 强弱 · R1", 2.2, "dash", "y2", "")\n'
        '        add_line(fig, data, "BTC_VOL_30D", "BTC 30D 实际波动率 · R2", 2.2, "dot", "y3", "%")',
    ),
    (
        '            yaxis=dict(title="BTC / ETH · Rebased 100", tickformat=".1f"),',
        '            yaxis=dict(title="BTC / ETH · 起点=100", tickformat=".1f"),',
    ),
    (
        '    add_line(fig, data, "BTC", "BTC", 2.9, unit=" USD")\n'
        '    add_line(fig, data, "ETH", "ETH (R1)", 2.6, None, "y2", " USD")\n'
        '    add_line(fig, data, "ETHBTC", "ETH/BTC (R2)", 2.2, "dash", "y3", "")\n'
        '    add_line(fig, data, "BTC_VOL_30D", "BTC 30D Realized Vol (R3)", 2.2, "dot", "y4", "%")',
        '    add_line(fig, data, "BTC", "BTC · USD", 2.9, unit=" USD")\n'
        '    add_line(fig, data, "ETH", "ETH · USD · R1", 2.6, None, "y2", " USD")\n'
        '    add_line(fig, data, "ETHBTC", "ETH/BTC 强弱 · R2", 2.2, "dash", "y3", "")\n'
        '    add_line(fig, data, "BTC_VOL_30D", "BTC 30D 实际波动率 · R3", 2.2, "dot", "y4", "%")',
    ),
    (
        "CRYPTO_MARKET_DESCRIPTION = (\n"
        "    '<b>参数概念：</b><br>'\n"
        "    '1. BTC / ETH：比特币与以太坊美元价格；默认 Rebased 100 共用左轴。Raw 模式中 BTC 使用左轴、ETH 使用 R1。<br>'\n"
        "    '2. ETH/BTC：ETH 价格除以 BTC 价格；Rebased 100 使用 R1，Raw 使用 R2。上升表示 ETH 相对 BTC 走强。<br>'\n"
        "    '3. BTC 30D Realized Vol：BTC 日收益率计算的 30 日年化实际波动率；Rebased 100 使用 R2，Raw 使用 R3，不是期权隐含波动率。<br><br>'\n"
        "    '<b>读取提示：</b>默认优先看 Rebased 100 的 BTC / ETH 强弱，再结合 ETH/BTC 判断风险偏好是否从 BTC 向 ETH 扩散；波动率快速抬升意味着仓位风险同步放大。'\n"
        ")",
        "CRYPTO_MARKET_DESCRIPTION = (\n"
        "    '<b>4 个参数分别看什么：</b><br>'\n"
        "    '1. BTC：默认 Rebased 100 把所选区间第一个有效价格设为 100，只表示相对涨跌，不是 BTC 的美元价格；使用左轴。Raw 模式显示真实美元价格。<br>'\n"
        "    '2. ETH：与 BTC 一样把起点设为 100，因此可直接比较谁涨得更多、跌得更少；Rebased 100 使用左轴，Raw 模式使用 R1。<br>'\n"
        "    '3. ETH/BTC：ETH 价格 ÷ BTC 价格；上升表示 ETH 相对 BTC 走强，下降表示 BTC 相对更强；Rebased 100 使用 R1，Raw 使用 R2。<br>'\n"
        "    '4. BTC 30D Realized Vol：根据 BTC 日收益率计算的过去 30 日年化实际波动率；只表示“波动有多大”，不表示上涨或下跌方向；Rebased 100 使用 R2，Raw 使用 R3。<br><br>'\n"
        "    '<b>最简单的读取顺序：</b>① 蓝线 vs 红线：BTC 和 ETH 谁跑赢；② 绿线：ETH 相对 BTC 是变强还是变弱；③ 紫色虚线：BTC 最近是否进入高波动状态。<br>'\n"
        "    '<b>轴编号说明：</b>R1 / R2 / R3 只是不同的右侧纵轴编号，不是额外指标。'\n"
        ")",
    ),
    (
        '<div class="section-description">BTC / ETH · ETH/BTC Ratio (R1) · BTC 30D Realized Volatility (R2/R3)</div>',
        '<div class="section-description">4 个指标 · BTC / ETH 相对表现 · ETH/BTC 强弱 · BTC 30D 实际波动率</div>',
    ),
]

for old, new in replacements:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one match, found {count}: {old[:100]!r}")
    text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("Updated crypto chart legend, axis wording, and 4-item explanation.")
