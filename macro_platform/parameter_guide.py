"""Display-only Chinese glossary for chart series; never transforms observations."""
import html
import re


# key: Chinese name, original unit, interpretation / calculation
TERMS = {
    "IORB": ("准备金余额利率", "年化%", "美联储付给合资格银行的准备金利息。"),
    "ON RRP": ("隔夜逆回购操作利率", "年化%", "图1为机构把资金隔夜存入美联储工具的利率；与逆回购余额不同。"),
    "EFFR": ("有效联邦基金利率", "年化%", "银行等机构之间无抵押隔夜美元资金的实际成交利率。"),
    "SOFR": ("有担保隔夜融资利率", "年化%", "以美国国债作抵押的隔夜美元融资成本。"),
    "SRF": ("常备回购工具操作利率", "年化%", "合资格机构向美联储抵押融资的工具利率；线条表示价格。"),
    "SRF 实际用量": ("常备回购当日实际接受金额", "十亿美元", "深青色柱；合计当日各场、三类抵押品。1＝10亿美元；0为已公布零成交，缺失不补0；不是未偿余额。"),
    "10年期名义收益率（DGS10）": ("美国10年期普通国债收益率", "年化%", "包含实际利率和通胀补偿的名义收益率。"),
    "10年期实际收益率（TIPS · DFII10，右轴）": ("美国10年期通胀保值国债实际收益率", "年化%", "TIPS为通胀保值国债；本金随通胀调整，这条线为实际收益率。"),
    "10年期盈亏平衡通胀率（BEI · T10YIE，右轴）": ("10年期盈亏平衡通胀率", "年化%", "BEI＝同期限名义收益率−实际收益率；含通胀风险和流动性溢价，不是未来通胀的确定预测。"),
    "10Y−2Y": ("美国10年减2年国债利差", "百分点", "上升表示曲线变陡；负值表示倒挂。"),
    "30Y−10Y": ("美国30年减10年国债利差", "百分点", "同日30年收益率−10年收益率；观察长端曲线斜率。"),
    "VIX": ("标普500未来30天隐含波动率", "年化%", "由指数期权推算的预期波动幅度，不能直接判断涨跌。"),
    "VIXEQ": ("标普500成分股篮子隐含波动率", "年化%", "成分股层面的30天预期波动，采用市值加权篮子。"),
    "VIX3M": ("标普500未来约3个月隐含波动率", "年化%", "与VIX对比观察近端及中期波动定价。"),
    "VIXEQ/VIX": ("个股波动率与指数波动率之比", "倍", "同日VIXEQ÷VIX；上升表示个股波动相对指数波动更高。"),
    "VIX/VIX3M": ("近月与3个月隐含波动率之比", "倍", "同日VIX÷VIX3M；大于1表示近端预期波动更高。"),
    "COR3M": ("3个月期隐含相关性指数", "指数点", "观察成分股预期共同波动程度；不是收益率。"),
    "SKEW": ("标普500尾部风险定价指数", "指数点", "衡量期权市场对极端波动的定价，不是暴跌概率。"),
    "VVIX": ("VIX自身的预期波动率指数", "指数点", "由VIX期权反映VIX的预期波动，常称恐慌指数的恐慌指数。"),
    "VVIX/VIX": ("VVIX与VIX指数点之比", "倍", "同日VVIX÷VIX；两个指标对象不同，比值不是涨跌概率。"),
    "9D/30D": ("9天与30天隐含波动率之比", "倍", "同日VIX9D÷VIX；大于1表示超短期波动定价更高。"),
    "SPX P/C": ("标普500看跌与看涨期权成交量比", "倍", "SPX及SPXW当日Put成交量÷Call成交量；不是持仓量比或净看空仓位。"),
    "S&P 500": ("美国标普500指数", "指数点", "约500家美国大型上市公司的市值加权价格指数。"),
    "SPX（标普500市值加权）": ("美国标普500价格指数", "指数点", "市值较大的公司影响更大；价格不含股息再投资。"),
    "RSP（标普500等权ETF）": ("跟踪标普500等权指数的ETF", "美元/份", "成分股权重近似相同，按季再平衡；图中为ETF价格，不是指数点。"),
    "比值：标普500 ÷ 日经225": ("标普500÷日经225点位比值", "倍（点位比）", "分子为标普500、分母为日经225；上升表示美股相对走强，下降表示日股相对走强。"),
    "分子：标普500（S&P 500）": ("分子：美国标普500收盘点位", "指数点", "市值加权；采用真实收盘点位四舍五入为整数，不做归一化。"),
    "分母：日经225（Nikkei 225）": ("分母：日本日经225收盘点位", "指数点", "Nikkei 225＝日经225，东京证券交易所Prime市场225只股票的价格加权指数；点位不是日元金额。"),
    "Nikkei 225": ("日本日经225指数", "指数点", "东京证券交易所Prime市场225只股票的价格加权指数；采用已完成交易日收盘值。"),
    "US−Japan 10Y spread": ("美国减日本10年期国债利差", "百分点", "同日美国10年收益率−日本10年收益率；不是短期借日元成本或可实现套息收益。"),
    "USD/JPY": ("美元兑日元汇率", "日元/美元", "1美元可兑换多少日元；数值上升为日元贬值，下降为日元升值。"),
    "JPY 20-session appreciation": ("日元过去20个交易日升值幅度", "%", "（20个有效交易日前USD/JPY÷当前USD/JPY−1）×100%；正值为日元升值。"),
    "CFTC JPY speculative net": ("日元期货非商业净持仓", "万张合约", "非商业多头−空头；正值净多日元，负值净空日元。周度持仓，不代表全部跨境套息仓位。"),
    "US 5Y Real · TIPS": ("美国5年期TIPS实际收益率", "年化%", "美元中期实际利率；不能与中国名义国债利率直接相减当作套息收益。"),
    "沪深300": ("沪深300价格指数", "指数点", "沪深市场300只规模大、流动性好的代表性证券。"),
    "中证1000": ("中证1000价格指数", "指数点", "中证800之外规模偏小、流动性较好的1000只证券。"),
    "中证2000": ("中证2000价格指数", "指数点", "沪深市场小盘证券代表指数；与中证1000选样范围不同。"),
    "M2 YoY": ("港元广义货币M2同比增速", "%", "与上年同月比较；YoY＝同比，不等于股市资金净流入。"),
    "M2 MoM": ("港元广义货币M2环比增速", "%", "与上个月比较；MoM＝环比，柱状图表示逐月变化。"),
    "Monetary Base YoY": ("香港货币基础同比增速", "%", "货币基础包括负债证明书、政府流通纸币硬币、总结余及外汇基金票据债券。"),
    "Tencent Price": ("腾讯控股股价", "港元/股", "香港上市腾讯控股的价格；不是资金流入量。"),
    "HKEX Price": ("香港交易所股价", "港元/股", "香港交易所公司的股价；不是港股成交额。"),
    "HSTECH Index": ("恒生科技指数", "指数点", "观察香港上市科技主题成分股的表现。"),
    "HSI Index": ("恒生指数", "指数点", "观察香港主要上市公司的综合表现。"),
    "Closing Aggregate Balance": ("香港银行体系收市总结余", "十亿港元", "银行在金管局结算账户的港元余额合计；1＝10亿港元。"),
    "Outstanding EFBN": ("未偿还外汇基金票据及债券", "十亿港元", "EFBN＝外汇基金票据及债券；本图为官方市值口径证券存量。"),
    "EFBN Held by Licensed Banks": ("持牌银行持有的外汇基金票据及债券", "十亿港元", "观察银行持有的该类港元流动证券规模。"),
    "O/N HIBOR": ("隔夜香港银行同业拆息", "年化%", "O/N＝隔夜，HIBOR＝香港银行同业拆息。"),
    "3M HIBOR": ("3个月期香港银行同业拆息", "年化%", "锁定3个月港元同业资金的定盘利率。"),
    "HKMA Base Rate": ("香港金管局基本利率", "年化%", "HKMA＝香港金融管理局；用于贴现窗融资基准。"),
    "O/N−3M Spread": ("隔夜减3个月HIBOR利差", "百分点", "正值表示隔夜资金成本高于3个月资金成本。"),
    "USD/HKD": ("美元兑港元汇率", "港元/美元", "1美元兑换多少港元；数值上升为港元走弱。本图反向左轴，线向上表示港元走强。"),
    "Gold": ("COMEX黄金期货连续合约价格", "美元/金衡盎司", "黄金期货日线收盘，连续合约可能受换月影响。"),
    "Silver": ("COMEX白银期货连续合约价格", "美元/金衡盎司", "白银期货日线收盘，连续合约可能受换月影响。"),
    "Gold/Silver Ratio": ("金银价格比", "倍", "同日黄金÷白银；上升为黄金相对白银走强。"),
    "Gold Volatility · GVZ": ("黄金ETF期权隐含波动率指数", "年化%", "由GLD期权反映未来约30天的预期波动，不是黄金价格。"),
    "COMEX 库存": ("美国COMEX仓库铜库存", "千公吨", "COMEX交割仓库报告的铜存量；1千公吨＝1000公吨。"),
    "LME 库存": ("伦敦金属交易所仓库铜库存", "千公吨", "LME＝伦敦金属交易所；与COMEX分别反映不同交割体系的存量。"),
    "LME 3M 铜价": ("伦敦3个月期铜价", "美元/公吨", "3M在这里是3个月交割期限，不是图表显示范围。"),
    "COMEX HG 换算价": ("美国COMEX铜期货换算价格", "美元/公吨", "HG为铜期货代码；美元/磅报价×2204.62262185换算为美元/公吨。"),
    "COMEX−LME 3M 价差": ("美国铜价减伦敦3个月铜价", "美元/公吨", "同日COMEX换算价−LME 3M价格；正值为美国较贵，交割差异使它不等于套利利润。"),
    "WTI 原油": ("美国西得克萨斯中质原油期货", "美元/桶", "WTI为美国原油基准；图中使用近月连续合约代理CL=F。"),
    "铜油比": ("一公吨铜相当于多少桶原油", "桶/公吨", "同日COMEX铜价（美元/公吨）÷WTI（美元/桶）。"),
    "TC 粗炼费 · 周度": ("进口铜精矿现货粗炼加工费", "美元/干吨", "TC＝Treatment Charge；周度报价，可为负，与年度长单基准不同。"),
    "RC 精炼费 · 按方法计算 · 周度": ("铜精矿现货精炼加工费", "美分/磅", "RC＝Refining Charge；本源按TC数值÷10计算，不是另行采样报价。"),
    "BTC · USD": ("比特币美元价格", "美元/枚", "BTC＝比特币，使用已完成日线价格。"),
    "ETH · USD · R1": ("以太币美元价格", "美元/枚", "ETH＝以太币，使用已完成日线价格。"),
    "ETH/BTC 强弱 · R2": ("以太币与比特币价格比", "倍", "同日ETH价格÷BTC价格；上升为ETH相对BTC走强。"),
    "BTC 30D 实际波动率 · R3": ("比特币过去30日实际波动率", "年化%", "由历史日收益率估计、按365天年化；衡量已发生波动，不是未来隐含波动率。"),
    "Net Liquidity": ("美元净流动性代理", "万亿美元", "美联储总资产−TGA−ON RRP余额；是资产负债表代理，不等于流入股票的资金。"),
    "Reserve Balances": ("银行准备金余额", "万亿美元", "存款机构在美联储的准备金存量。"),
    "TGA": ("美国财政部在美联储的账户余额", "万亿美元", "财政现金存量；其他条件相同时余额增加通常抽走银行准备金。"),
}


def describe(name, axis="y"):
    key = re.sub(r"\s*\(R\d+\)$", "", str(name)).strip()
    entry = TERMS.get(key)
    if str(name) == "ON RRP (R2)":
        entry = ("美联储隔夜逆回购余额", "十亿美元", "机构存入该工具的资金存量；与图1的ON RRP操作利率不同。")
    if entry is None and key in ("3M", "2Y", "10Y", "30Y"):
        term = {"3M": "3个月", "2Y": "2年", "10Y": "10年", "30Y": "30年"}[key]
        entry = (f"美国{term}期国债收益率", "年化%", "M＝月，Y＝年；这里是债券期限。")
    if entry is None and (match := re.fullmatch(r"(Japan|China) (2Y|10Y|30Y|10Y−2Y|30Y−10Y)", key)):
        country = {"Japan": "日本", "China": "中国"}[match[1]]
        term = match[2].replace("Y", "年")
        spread = "−" in term
        entry = (country + term + ("国债利差" if spread else "期国债收益率"),
                 "百分点" if spread else "年化%", "同日长端减短端；负值为倒挂。" if spread else "该国本币国债的市场利率。")
    if entry is None and "回撤比例" in key:
        entry = (key, "%", "（当日收盘÷所选区间最高收盘−1）×100%；高点当日为0，高点前不画线。")
    if entry is None and (match := re.fullmatch(r"(Oracle|Intel|AMD|NVIDIA|CoreWeave|Alphabet|Microsoft|Nebius|CDX IG) (1Y|5Y)(.*)", key)):
        company = {"Oracle": "甲骨文", "Intel": "英特尔", "AMD": "超威半导体", "NVIDIA": "英伟达", "Alphabet": "谷歌母公司Alphabet", "Microsoft": "微软", "Nebius": "Nebius（NBIS）", "CoreWeave": "CoreWeave云算力公司", "CDX IG": "投资级公司信用指数"}[match[1]]
        years = "1年" if match[2] == "1Y" else "5年"
        entry = (company + years + ("信用指数利差" if match[1] == "CDX IG" else "信用违约掉期利差（CDS）"), "基点bp",
                 "100bp＝1%/年；走高表示信用保护变贵，不是股价保险。" + ("带*为由预付款推算的隐含利差。" if "*" in key else ""))
    if entry is None:
        return None
    axis_name = "左轴" if axis in (None, "y") else "右轴R" + str(int(axis[1:]) - 1)
    return {"图例参数": str(name), "中文名称": entry[0], "单位／坐标": entry[1] + " · " + axis_name, "含义与读法": entry[2]}


def parameter_rows(fig):
    rows = [row for trace in fig.data if (row := describe(trace.name, trace.yaxis)) is not None]
    shown = {str(trace.name) for trace in fig.data}
    meta = fig.layout.meta if isinstance(fig.layout.meta, dict) else {}
    for name in meta.get("missing_series", []):
        if name in shown:
            continue
        match = re.search(r"(?:\(R|· R)(\d+)", name)
        axis = "y" + str(int(match[1]) + 1) if match else "y"
        row = describe(name, axis)
        if row is not None:
            row["图例参数"] += "（暂无数据）"
            rows.append(row)
    return rows


def render_parameter_guide(fig, element_key):
    import streamlit as st
    rows = parameter_rows(fig)
    # A complete source outage can leave a figure without even trace metadata.
    # Keep the four crypto definitions available in that state as well.
    if element_key == "crypto_market":
        present = {row["图例参数"].removesuffix("（暂无数据）") for row in rows}
        for name, axis in (("BTC · USD", "y"), ("ETH · USD · R1", "y2"),
                           ("ETH/BTC 强弱 · R2", "y3"), ("BTC 30D 实际波动率 · R3", "y4")):
            if name not in present:
                row = describe(name, axis)
                row["图例参数"] += "（暂无数据）"
                rows.append(row)
    if not rows:
        return
    with st.expander("参数对照：中文名称、单位、坐标与读法", expanded=element_key == "sp500_nikkei_ratio"):
        def safe(value):
            return html.escape(str(value)).replace("|", "&#124;").replace("\n", " ")
        headers = list(rows[0])
        table = "| " + " | ".join(headers) + " |\n| " + " | ".join(["---"] * len(headers)) + " |\n"
        table += "\n".join("| " + " | ".join(safe(row[h]) for h in headers) + " |" for row in rows)
        st.markdown(table)
        st.caption("R1/R2/R3为第1/2/3个独立右轴；%为百分比，百分点为两个百分比之差，100bp＝1个百分点。顶部1M/3M/1Y等按钮只控制显示的历史范围；参数名中的期限由各指标定义。")
