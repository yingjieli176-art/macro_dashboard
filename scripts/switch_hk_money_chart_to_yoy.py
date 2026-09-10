from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HK = ROOT / "macro_platform" / "hk_liquidity.py"
APP = ROOT / "app.py"


def replace_required(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing expected block: {label}")
    return text.replace(old, new)


def main() -> None:
    hk = HK.read_text(encoding="utf-8")

    # Legacy composite builder: keep it semantically aligned if it is used elsewhere.
    hk = replace_required(
        hk,
        '    add_trace(1, "M2 MoM", "M2 MoM", COLORS["m2"], 2.8)\n'
        '    add_trace(1, "M3 MoM", "M3 MoM", COLORS["m3"], 2.3, "dash")\n'
        '    add_trace(1, "Monetary Base MoM", "Monetary Base MoM", COLORS["base"], 1.8, "dot")',
        '    add_trace(1, "M2 YoY", "M2 YoY", COLORS["m2"], 2.8)\n'
        '    add_trace(1, "M3 YoY", "M3 YoY", COLORS["m3"], 2.3, "dash")\n'
        '    add_trace(1, "Monetary Base YoY", "Monetary Base YoY", COLORS["base"], 1.8, "dot")',
        "legacy chart money traces",
    )
    hk = replace_required(
        hk,
        'fig.update_yaxes(title_text="MoM (%)", row=1, col=1, zeroline=True, zerolinecolor="#cbd5e1", **grid)',
        'fig.update_yaxes(title_text="YoY (%)", row=1, col=1, zeroline=True, zerolinecolor="#cbd5e1", **grid)',
        "legacy chart y-axis",
    )

    # Independent Chart 5: YoY is better for structural trend; MoM remains in the data model/scoring.
    hk = replace_required(
        hk,
        '    add_line(money, data, "M2 MoM", "M2 MoM", COLORS["m2"], 2.8, secondary_y=False)\n'
        '    add_line(money, data, "M3 MoM", "M3 MoM", COLORS["m3"], 2.3, "dash", secondary_y=False)\n'
        '    add_line(money, data, "Monetary Base MoM", "Monetary Base MoM", COLORS["base"], 1.8, "dot", secondary_y=False)',
        '    add_line(money, data, "M2 YoY", "M2 YoY", COLORS["m2"], 2.8, secondary_y=False)\n'
        '    add_line(money, data, "M3 YoY", "M3 YoY", COLORS["m3"], 2.3, "dash", secondary_y=False)\n'
        '    add_line(money, data, "Monetary Base YoY", "Monetary Base YoY", COLORS["base"], 1.8, "dot", secondary_y=False)',
        "Chart 5 money traces",
    )
    hk = replace_required(
        hk,
        '        title_text="Money MoM (%)", secondary_y=False,',
        '        title_text="Money YoY (%)", secondary_y=False,',
        "Chart 5 y-axis",
    )

    # Clarify why both transforms remain in the model.
    hk = hk.replace(
        '# MoM is the primary dashboard signal because it reacts faster to marginal liquidity changes.',
        '# MoM remains the fast signal used by the liquidity-state logic because it reacts quickly to marginal changes.',
    )
    hk = hk.replace(
        '# Keep YoY in the data model for context / future switchable views, but do not use it as the primary chart signal.',
        '# YoY is the primary Chart 5 display because it is smoother and better suited to medium-term money-growth trends.',
    )
    HK.write_text(hk, encoding="utf-8")

    app = APP.read_text(encoding="utf-8")
    app = replace_required(
        app,
        '<b>参数概念：</b><br>1. HKD M2 MoM：港元 M2 月环比增速，用来观察广义港元货币的边际扩张或收缩；主图采用月环比以提高对当前流动性变化的敏感度。<br>2. HKD M3 MoM：港元 M3 月环比增速，统计口径较 M2 更广，用于交叉确认广义货币边际变化。<br>3. Monetary Base MoM：香港货币基础总量月环比变化，用于观察基础货币层面的边际扩张与收缩。',
        '<b>参数概念：</b><br>1. HKD M2 YoY：港元 M2 同比增速，M2 覆盖公众持有的现金、活期/储蓄/定期存款及相应货币工具，用于观察广义港元货币的中期扩张趋势。<br>2. HKD M3 YoY：港元 M3 同比增速，M3 在 M2 基础上进一步纳入限制牌照银行及接受存款公司的相关存款与可转让存款证，因此口径更广，但通常与 M2 高度同步。<br>3. Monetary Base YoY：香港货币基础总量同比变化，用于观察基础货币层面的中期扩张与收缩。',
        "combined HK description",
    )
    app = replace_required(
        app,
        '<b>读取提示：</b>M2/M3 为月度统计，公布存在时滞；主图使用 MoM 观察边际变化，流动性评分使用最近 3 个月 M2/M3 MoM 均值降低单月噪声。YoY 保留在数据层供后续切换与中期趋势判断。',
        '<b>读取提示：</b>M2/M3 为月度统计，公布存在时滞；图 5 使用 YoY 观察中期货币趋势并降低单月噪声。流动性评分内部仍使用最近 3 个月 M2/M3 MoM 均值，以保留对边际拐点的敏感度。',
        "combined HK reading hint",
    )
    app = replace_required(
        app,
        '<b>参数概念：</b><br>1. HKD M2 MoM：港元 M2 月环比增速，用来观察广义港元货币的边际扩张或收缩。<br>2. HKD M3 MoM：港元 M3 月环比增速，统计口径较 M2 更广，用于交叉确认广义货币边际变化。<br>3. Monetary Base MoM：香港货币基础总量月环比变化。',
        '<b>参数概念：</b><br>1. HKD M2 YoY：港元 M2 同比增速，用来观察广义港元货币的中期扩张或收缩趋势。<br>2. HKD M3 YoY：港元 M3 同比增速；M3 比 M2 口径更广，但两者在香港通常高度同步，因此主要用于交叉确认货币趋势而不是作为独立方向信号。<br>3. Monetary Base YoY：香港货币基础总量同比变化，用于观察基础货币的中期扩张与收缩。',
        "Chart 5 parameter description",
    )
    # Current market histories are daily/weekly adaptive, not month-end-only.
    app = app.replace('港交所 0388.HK 月末收盘价', '港交所 0388.HK 市场价格')
    app = app.replace('恒生科技指数 HSTECH.HK 月末指数点位', '恒生科技指数 HSTECH 市场点位')
    app = app.replace('恒生指数月末指数点位', '恒生指数市场点位')
    APP.write_text(app, encoding="utf-8")

    print("switched Hong Kong money display from MoM to YoY; scoring remains MoM-based")


if __name__ == "__main__":
    main()
