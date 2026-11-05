"""Short parenthetical display labels, without changing series identities or data."""
import re

HINTS = {'IORB': '准备金利率', 'ON RRP': '隔夜逆回购利率', 'EFFR': '联邦基金实际利率', 'SOFR': '隔夜抵押融资利率', 'SRF': '常备回购利率', 'SRF 实际用量': '实际成交金额', '10年期名义收益率（DGS10）': '美国10年期普通国债收益率', '10年期实际收益率（TIPS · DFII10，右轴）': '美国10年期通胀保值国债实际收益率', '10年期盈亏平衡通胀率（BEI · T10YIE，右轴）': '10年期盈亏平衡通胀率', '10Y−2Y': '美国10年减2年国债利差', '30Y−10Y': '美国30年减10年国债利差', 'VIX': '30天预期波动', 'VIXEQ': '成分股预期波动', 'VIX3M': '3个月预期波动', 'VIXEQ/VIX': '个股与指数波动比', 'VIX/VIX3M': '近月与3个月波动比', 'COR3M': '3个月隐含相关性', 'SKEW': '尾部风险指数', 'VVIX': 'VIX自身预期波动', 'VVIX/VIX': '波动指数比', '9D/30D': '9天与30天波动比', 'SPX P/C': '看跌与看涨成交量比', 'S&P 500': '标普500', 'SPX（标普500市值加权）': '市值加权标普500', 'RSP（标普500等权ETF）': '标普500等权ETF', '比值：标普500 ÷ 日经225': '美日指数点位比', '分子：标普500（S&P 500）': '美国标普500', '分母：日经225（Nikkei 225）': '日本日经225', 'Nikkei 225': '日经225', 'US−Japan 10Y spread': '美日10年国债利差', 'USD/JPY': '美元兑日元', 'JPY 20-session appreciation': '日元20日升值幅度', 'CFTC JPY speculative net': '日元期货投机净仓', 'US 5Y Real · TIPS': '美国5年实际利率', '沪深300': 'A股大盘指数', '中证1000': 'A股小盘指数', '中证2000': 'A股小微盘指数', 'M2 YoY': '港元M2同比', 'M2 MoM': '港元M2环比', 'Monetary Base YoY': '香港货币基础同比', 'Tencent Price': '腾讯股价', 'HKEX Price': '港交所股价', 'HSTECH Index': '恒生科技指数', 'HSI Index': '恒生指数', 'Closing Aggregate Balance': '银行收市总结余', 'Outstanding EFBN': '未偿外汇基金票据债券', 'EFBN Held by Licensed Banks': '银行持有外汇基金票据债券', 'O/N HIBOR': '港元隔夜拆息', '3M HIBOR': '港元3个月拆息', 'HKMA Base Rate': '香港基本利率', 'O/N−3M Spread': '隔夜减3个月拆息', 'USD/HKD': '美元兑港元', 'Gold': '黄金期货', 'Silver': '白银期货', 'Gold/Silver Ratio': '金银比', 'Gold Volatility · GVZ': '黄金预期波动', 'COMEX 库存': '美国铜库存', 'LME 库存': '伦敦铜库存', 'LME 3M 铜价': '伦敦3个月铜价', 'COMEX HG 换算价': '美国铜价换算', 'COMEX−LME 3M 价差': '美国减伦敦铜价', 'WTI 原油': '美国原油期货', '铜油比': '铜价除以油价', 'TC 粗炼费 · 周度': '铜精矿粗炼费', 'RC 精炼费 · 按方法计算 · 周度': '精炼费，TC数值÷10', 'BTC · USD': '比特币', 'ETH · USD · R1': '以太币', 'ETH/BTC 强弱 · R2': '以太币与比特币价格比', 'BTC 30D 实际波动率 · R3': '比特币30日历史波动', 'Net Liquidity': '美元净流动性代理', 'Reserve Balances': '银行准备金余额', 'TGA': '美国财政账户余额'}

def short_parameter_label(name):
    name = str(name)
    key = re.sub(r"\s*\(R\d+\)$", "", name).strip()
    if name == "ON RRP (R2)":
        return "ON RRP（隔夜逆回购余额）"
    direct = {
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
