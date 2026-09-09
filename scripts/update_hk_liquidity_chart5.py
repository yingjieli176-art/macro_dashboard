from pathlib import Path

APP = Path('app.py')
text = APP.read_text(encoding='utf-8')

# Keep Chart 5 data implementation unchanged; standardize all parameter explanations.
# Literal newlines were previously placed inside HTML and therefore collapsed by the browser.
# Use <br> so every numbered concept is rendered on its own line.

start = text.index('PARAM_DESCRIPTIONS = ')
end = text.index('\ndef show_parameter_description', start)
new_desc = '''PARAM_DESCRIPTIONS = [
    '<b>参数概念：</b><br>1. IORB（Interest on Reserve Balances）：美联储向存款机构准备金余额支付的利率，是美国准备金利率体系的重要基准。<br>2. ON RRP（Overnight Reverse Repurchase Agreement）：美联储隔夜逆回购工具利率，金融机构可通过该工具进行隔夜资金配置。<br>3. EFFR（Effective Federal Funds Rate）：美国联邦基金市场实际成交形成的有效隔夜利率，反映银行间短期无担保资金价格。<br>4. SOFR（Secured Overnight Financing Rate）：以美国国债为抵押的隔夜融资利率，是美元有担保短期融资的重要基准。',
    '<b>参数概念：</b><br>1. 10Y Nominal：10 年期美国国债名义收益率，包含实际利率与通胀预期等因素。<br>2. 10Y Real：10 年期美国国债实际收益率，通常由通胀保值国债（TIPS）市场反映。<br>3. 10Y Breakeven：10 年期盈亏平衡通胀率，是名义国债收益率与实际收益率之间的差值，用于观察市场隐含的长期通胀预期。',
    '<b>参数概念：</b><br>1. 3M：3 个月期美国国债收益率，代表较短期限的美元无风险利率。<br>2. 2Y：2 年期美国国债收益率，通常对美联储政策路径及短中期利率预期较敏感。<br>3. 10Y：10 年期美国国债收益率，是全球金融市场重要的长期无风险利率参考。<br>4. 10Y−2Y：10 年期减 2 年期国债收益率利差，用于描述收益率曲线的中长期斜率。<br>5. 10Y−3M：10 年期减 3 个月期国债收益率利差，用于描述长期利率相对短期政策利率的期限结构。',
    '<b>参数概念：</b><br>1. Net Liquidity Proxy：Reserve Balances − TGA − ON RRP 的组合指标，用于描述美国金融体系中可观察的流动性变化方向；不是美联储官方指标。<br>2. Reserve Balances：存款机构存放在美联储的准备金余额，属于银行体系流动性的重要组成部分。<br>3. TGA（Treasury General Account）：美国财政部在美联储的总账户余额，财政资金进出会影响银行体系准备金。<br>4. ON RRP Balance：美联储隔夜逆回购工具的余额，反映资金进入该工具的规模。'
]
'''
text = text[:start] + new_desc + text[end:]

APP.write_text(text, encoding='utf-8')
print('standardized conceptual parameter descriptions')
