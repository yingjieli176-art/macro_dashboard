"""Short parenthetical display labels, without changing series identities or data."""
import re

HINTS = {'IORB': '准备金利率', 'ON RRP': '隔夜逆回购利率', 'EFFR': '联邦基金实际利率', 'SOFR': '隔夜抵押融资利率', 'SRF': '常备回购利率', 'SRF 实际用量': '实际成交金额', '10年期名义收益率（DGS10）': '美国10年期普通国债收益率', '10年期实际收益率（TIPS · DFII10，右轴）': '美国10年期通胀保值国债实际收益率', '10年期盈亏平衡通胀率（BEI · T10YIE，右轴）': '10年期盈亏平衡通胀率', '10Y−2Y': '美国10年减2年国债利差', '30Y−10Y': '美国30年减10年国债利差', 'VIX': '30天预期波动', 'VIXEQ': '成分股预期波动', 'VIX3M': '3个月预期波动', 'VIXEQ/VIX': '个股与指数波动比', 'VIX/VIX3M': '近月与3个月波动比', 'COR3M': '3个月隐含相关性', 'SKEW': '尾部风险指数', 'VVIX': 'VIX自身预期波动', 'VVIX/VIX': '波动指数比', '9D/30D': '9天与30天波动比', 'SPX P/C': '看跌与看涨成交量比', 'S&P 500': '标普500', 'SPX（标普500市值加权）': '市值加权标普500', 'RSP（标普500等权ETF）': '标普500等权ETF', '比值：标普500 ÷ 日经225': '美日指数点位比', '分子：标普500（S&P 500）': '美国标普500', '分母：日经225（Nikkei 225）': '日本日经225', 'Nikkei 225': '日经225', 'US−Japan 10Y spread': '美日10年国债利差', 'USD/JPY': '美元兑日元', 'JPY 20-session appreciation': '日元20日升值幅度', 'CFTC JPY speculative net': '日元期货投机净仓', 'US 5Y Real · TIPS': '美国5年实际利率', '沪深300': 'A股大盘指数', '中证1000': 'A股小盘指数', '中证2000': 'A股小微盘指数', 'M2 YoY': '港元M2同比', 'M2 MoM': '港元M2环比', 'Monetary Base YoY': '香港货币基础同比', 'Tencent Price': '腾讯股价', 'HKEX Price': '港交所股价', 'HSTECH Index': '恒生科技指数', 'HSI Index': '恒生指数', 'Closing Aggregate Balance': '银行收市总结余', 'Outstanding EFBN': '未偿外汇基金票据债券', 'EFBN Held by Licensed Banks': '银行持有外汇基金票据债券', 'O/N HIBOR': '港元隔夜拆息', '3M HIBOR': '港元3个月拆息', 'HKMA Base Rate': '香港基本利率', 'O/N−3M Spread': '隔夜减3个月拆息', 'USD/HKD': '美元兑港元', 'Gold': '黄金期货', 'Silver': '白银期货', 'Gold/Silver Ratio': '金银比', 'Gold Volatility · GVZ': '黄金预期波动', 'COMEX 库存': '美国铜库存', 'LME 库存': '伦敦铜库存', 'LME 3M 铜价': '伦敦3个月铜价', 'COMEX HG 换算价': '美国铜价换算', 'COMEX−LME 3M 价差': '美国减伦敦铜价', 'WTI 原油': '美国原油期货', '铜油比': '铜价除以油价', 'TC 粗炼费 · 周度': '铜精矿粗炼费', 'RC 精炼费 · 按方法计算 · 周度': '精炼费，TC数值÷10', 'BTC · USD': '比特币', 'ETH · USD · R1': '以太币', 'ETH/BTC 强弱 · R2': '以太币与比特币价格比', 'BTC 30D 实际波动率 · R3': '比特币30日历史波动', 'Net Liquidity': '美元净流动性代理', 'Reserve Balances': '银行准备金余额', 'TGA': '美国财政账户余额'}

def short_parameter_label(name):
    name = str(name)
    key = re.sub(r"\s*\(R\d+\)$", "", name).strip()
    if name == "ON RRP (R2)":
        return "ON RRP（隔夜逆回购余额）"
    direct = {
        "NASDAQ-100": "NASDAQ-100（纳斯达克100）",
        "US 10Y - Japan 10Y": "US 10Y - Japan 10Y（美日10年国债利差）",
        "HY OAS": "HY OAS（美国高收益债利差，%）",
        "10年期名义收益率（DGS10）": "DGS10（10年名义美债）",
        "10年期实际收益率（TIPS · DFII10，右轴）": "DFII10（10年实际利率）",
        "10年期盈亏平衡通胀率（BEI · T10YIE，右轴）": "T10YIE（10年通胀补偿）",
        "分子：标普500（S&P 500）": "S&P 500（标普500）",
        "分母：日经225（Nikkei 225）": "Nikkei 225（日经225）",
        "比值：标普500 ÷ 日经225": "SPX/Nikkei（美日点位比）",
        "SPX（标普500市值加权）": "SPX（市值加权标普500）",
        "RSP（标普500等权ETF）": "RSP（标普500等权ETF）",
        "SRF 实际用量": "SRF用量（实际成交金额）",
        "BTC · USD": "BTC（比特币）", "ETH · USD · R1": "ETH（以太币）",
        "ETH/BTC 强弱 · R2": "ETH/BTC（相对强弱）",
        "BTC 30D 实际波动率 · R3": "BTC 30D（30日历史波动）",
    }
    if key in direct:
        return direct[key]
    if key in ("3M", "2Y", "10Y", "30Y"):
        return key + "（" + {"3M":"3个月美债", "2Y":"2年美债", "10Y":"10年美债", "30Y":"30年美债"}[key] + "）"
    if match := re.fullmatch(r"(Japan|China) (2Y|10Y|30Y|10Y−2Y|30Y−10Y)", key):
        return match[1] + " " + match[2] + "（" + {"Japan":"日本", "China":"中国"}[match[1]] + ("国债利差" if "−" in match[2] else "国债利率") + "）"
    if match := re.fullmatch(r"(NVIDIA|AMD|Alphabet|Microsoft|Oracle) 5Y.*", key):
        company={"NVIDIA":"英伟达", "AMD":"超威半导体", "Alphabet":"谷歌", "Microsoft":"微软", "Oracle":"甲骨文"}[match[1]]
        return match[1] + " 5Y（" + company + "违约利差）"
    if "回撤比例" in key:
        return key.replace(" 回撤比例", "") + "（区间高点回撤）"
    hint = HINTS.get(key)
    if hint:
        base = key.split(" · ")[0] if key.startswith(("TC ", "RC ")) else key
        return base + "（" + hint + "）"
    return name

def compact_parameter_labels(option):
    names = [s["name"] for s in option.get("series", [])]
    names += ["SPX 回撤比例", "RSP 回撤比例", "沪深300 回撤比例", "中证1000 回撤比例", "中证2000 回撤比例"]
    return {name: short_parameter_label(name) for name in names}


# Chart-specific definitions and calculation rules. Provider links are shown separately.
CHART_PARAMETER_GUIDES = {
    "normal_corridor_range": (
        ("IORB", "美联储支付给合资格银行的准备金余额利率，单位为年化%。"),
        ("ON RRP", "美联储隔夜逆回购工具利率，单位为年化%。"),
        ("EFFR", "无抵押隔夜联邦基金交易的有效利率，单位为年化%。"),
        ("SOFR", "以美国国债为抵押的隔夜回购融资利率，单位为年化%。"),
        ("SRF 利率", "常备回购工具的操作利率，单位为年化%。"),
        ("SRF 实际用量（R1）", "当日已完成的常备回购操作实际接受金额，右轴以十亿美元显示。各场结果齐全才汇总，已公布的零成交保留。"),
    ),
    "normal_yield10_range": (
        ("DGS10", "美国 10 年期名义国债收益率，单位为年化%。"),
        ("DFII10（R1）", "美国 10 年期通胀保值国债实际收益率，单位为年化%。"),
        ("T10YIE（R1）", "10 年期盈亏平衡通胀率，按同期限名义收益率减实际收益率，衡量平均通胀补偿，单位为年化%。"),
    ),
    "normal_treasury_range": (
        ("3M / 2Y / 10Y / 30Y", "美国 3 个月、2 年、10 年及 30 年期名义国债收益率，单位为年化%。"),
        ("10Y−2Y / 30Y−10Y（R1）", "同日长端收益率减短端收益率，单位为百分点。负值表示相应期限倒挂。"),
        ("NASDAQ-100（R2）", "纳斯达克 100 指数日收盘，单位为指数点。"),
    ),
    "us_equity_risk": (
        ("VIX", "标普 500 指数期权反映的未来 30 天年化隐含波动率。"),
        ("VIXEQ", "标普 500 成分股篮子的市值加权 30 天隐含波动率。"),
        ("S&P 500（R1）", "标普 500 指数日收盘，单位为指数点。"),
        ("VIXEQ/VIX（R2）", "同日成分股篮子隐含波动率除以指数隐含波动率，单位为倍。"),
        ("COR3M（R3）", "3 个月期隐含相关性指数，衡量成分股预期共同波动程度，单位为指数点。"),
    ),
    "vix_term_structure": (
        ("VIX / VIX3M", "标普 500 指数约未来 30 天和 3 个月的年化隐含波动率。"),
        ("VIX/VIX3M（R1）", "同日 VIX 除以 VIX3M。大于 1 表示近端隐含波动率更高。"),
        ("9D/30D（R1）", "同日 VIX9D 除以 VIX，比较约 9 天和 30 天的隐含波动率。"),
        ("SPX P/C（R1）", "SPX 与 SPXW 当日看跌期权成交量除以看涨期权成交量，包含周度期权。"),
        ("SKEW（R2）", "标普 500 期权的尾部风险定价指数，单位为指数点。"),
        ("VVIX（R3）", "VIX 自身的隐含波动率指数，单位为指数点。"),
        ("VVIX/VIX（R4）", "同日 VVIX 除以 VIX，单位为倍。"),
    ),
    "us_equity_drawdown": (
        ("SPX / RSP", "标普 500 市值加权指数（左轴，点）和标普 500 等权 ETF（右轴，美元）的日收盘。RSP 收盘价按拆股调整。"),
        ("区间高点 / 最新收盘", "点线标记所选区间的最高收盘价，虚线标记最新收盘价。"),
        ("回撤比例", "从所选区间的最高收盘日开始，按（当日收盘 ÷ 区间最高收盘 − 1）× 100% 计算。调整时间区间会重选高点。"),
    ),
    "nvidia_cds": (
        ("公司 5Y CDS", "五家公司 4.4–5.6 年剩余期限组的日度成交利差中位数，左轴以 bp 显示。100 bp 等于 1 个百分点。谷歌使用母公司 Alphabet 的 CDS。"),
        ("实际观测与覆盖率", "圆点表示可计价观测，缺数日期留空。覆盖率按有效观测日数除以源日历天数计算。"),
        ("HY OAS（R1）", "ICE BofA 美国高收益债指数相对美国国债即期曲线的期权调整利差，采用日收盘观测，右轴以百分比显示。"),
    ),
    "sp500_nikkei_ratio": (
        ("标普 500 / 日经 225", "分别使用两地的指数日收盘点位，标普用 R1，日经用 R2。"),
        ("相对强弱比值", "只在两地同一日期都有有效收盘时计算标普点位 ÷ 日经点位。比值按原始点位计算，未换汇。"),
    ),
    "japan_rates": (
        ("Japan 2Y / 10Y / 30Y", "日本 2 年、10 年及 30 年期国债收益率，单位为年化%。"),
        ("10Y−2Y / 30Y−10Y（R1）", "同日长端收益率减短端收益率，单位为百分点。"),
        ("Nikkei 225（R2）", "日经 225 指数日收盘，单位为指数点。"),
        ("USD/JPY（R3）", "1 美元兑换的日元数。数值上升表示日元相对美元走弱。"),
    ),
    "yen_carry": (
        ("美日 10Y 利差", "同日美国 10 年期国债收益率减日本 10 年期国债收益率，单位为百分点。"),
        ("USD/JPY（R1）", "1 美元兑换的日元数，使用日线收盘。"),
        ("日元 20 交易日升值幅度（R2）", "（20 个有效交易日前的 USD/JPY ÷ 当前 USD/JPY − 1）× 100%。正值表示日元升值。"),
        ("CFTC 日元投机净仓位（R3）", "日元期货非商业多头减非商业空头，采用 Legacy Futures Only 周度数据，单位为万张。"),
        ("TOPIX（R4）", "日本东证指数日收盘，单位为指数点。"),
    ),
    "china_rates": (
        ("China 2Y / 10Y", "中国 2 年及 10 年期名义国债收益率，单位为年化%。"),
        ("US 5Y Real · TIPS", "美国 5 年期通胀保值国债实际收益率，单位为年化%。"),
        ("China 10Y−2Y（R1）", "同日中国 10 年期国债收益率减 2 年期国债收益率，单位为百分点。"),
    ),
    "china_equity_drawdown": (
        ("沪深 300 / 中证 1000 / 中证 2000", "三只 A 股宽基价格指数的日收盘，单位为指数点。"),
        ("区间高点 / 最新收盘", "点线标记所选区间的最高收盘价，虚线标记最新收盘价。"),
        ("回撤比例", "各指数从所选区间的最高收盘日开始，按（当日收盘 ÷ 区间最高收盘 − 1）× 100% 计算。调整时间区间会重选高点。"),
    ),
    "hk_5_range": (
        ("M2 YoY / M2 MoM", "港元广义货币 M2 相比上年同月和上月的增速，单位为%。"),
        ("Monetary Base YoY", "香港货币基础相比上年同月的增速，单位为%。"),
        ("腾讯 / 港交所（R1）", "两家公司的日收盘股价，单位为港元。"),
        ("恒生科技 / 恒生指数（R2）", "两只指数的日收盘，单位为指数点。"),
    ),
    "hk_6_range": (
        ("Closing Aggregate Balance", "银行在金管局结算账户的收市总结余，单位为十亿港元。"),
        ("Outstanding EFBN（R1）", "未偿还外汇基金票据及债券的存量，单位为十亿港元。"),
        ("EFBN Held by Licensed Banks（R1）", "持牌银行持有的外汇基金票据及债券，单位为十亿港元。"),
    ),
    "hk_7_range": (
        ("O/N HIBOR / 3M HIBOR", "港元隔夜及 3 个月银行同业拆息，单位为年化%。历史序列以可用的官方月末观测补充。"),
        ("HKMA Base Rate", "香港金管局贴现窗基本利率，单位为年化%。"),
        ("O/N−3M Spread（R1）", "同日隔夜 HIBOR 减 3 个月 HIBOR，单位为百分点。"),
    ),
    "hk_8_range": (
        ("USD/HKD", "1 美元兑换的港元数。左轴反向，曲线向上表示港元走强。"),
        ("7.75 / 7.80 / 7.85", "分别为强方兑换保证、区间中点和弱方兑换保证。"),
        ("腾讯 / 港交所（R1）", "两家公司的日收盘股价，单位为港元。"),
        ("恒生科技 / 恒生指数（R2）", "两只指数的日收盘，单位为指数点。"),
    ),
    "precious_metals": (
        ("Gold / Silver（R1）", "COMEX 黄金与白银连续期货的日收盘，单位为美元/金衡盎司。黄金用左轴，白银用 R1。"),
        ("Gold/Silver Ratio（R2）", "同日黄金期货价格除以白银期货价格，表示一盎司黄金相当于多少盎司白银。"),
        ("GVZ（R3）", "GLD 期权反映的未来约 30 天年化隐含波动率。"),
    ),
    "copper_flow": (
        ("COMEX / LME 库存", "各自交割仓库体系报告的铜库存，单位为千公吨。"),
        ("LME 3M / COMEX HG（R1）", "LME 三个月期铜价及 COMEX 铜期货价，统一以美元/公吨显示。"),
        ("COMEX−LME 3M（R2）", "同日 COMEX 换算铜价减 LME 三个月期铜价，单位为美元/公吨。"),
        ("WTI（R3）", "WTI 近月期货日收盘，单位为美元/桶。"),
        ("铜油比（R4）", "同日 COMEX 铜价（美元/公吨）除以 WTI（美元/桶），单位为桶/公吨。"),
    ),
    "copper_tcrc": (
        ("TC 粗炼费", "进口干净铜精矿现货周度粗炼费，单位为美元/干吨。"),
        ("RC 精炼费（R1）", "按发布方方法取 TC 数值 ÷ 10，单位为美分/磅。"),
    ),
    "crypto_market": (
        ("BTC / ETH（R1）", "比特币和以太币的美元日线价格。BTC 用左轴，ETH 用 R1。"),
        ("ETH/BTC（R2）", "同日以太币价格除以比特币价格。上升表示 ETH 相对走强。"),
        ("BTC 30D 实际波动率（R3）", "用过去 30 天的日收益率标准差估算，至少需要 20 个有效样本，按 365 天年化并以百分比显示。"),
    ),
}
