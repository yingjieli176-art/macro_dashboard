from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HK = ROOT / "macro_platform" / "hk_liquidity.py"
APP = ROOT / "app.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    hk = HK.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")

    hk = replace_once(
        hk,
        '    "m2": "#2563eb",\n    "m3": "#7c3aed",',
        '    "m2": "#2563eb",\n    "m2_mom": "#0ea5e9",\n    "m3": "#7c3aed",',
        "add M2 MoM color",
    )

    hk = replace_once(
        hk,
        '    add_trace(1, "M2 YoY", "M2 YoY", COLORS["m2"], 2.8)\n'
        '    add_trace(1, "M3 YoY", "M3 YoY", COLORS["m3"], 2.3, "dash")\n'
        '    add_trace(1, "Monetary Base YoY", "Monetary Base YoY", COLORS["base"], 1.8, "dot")',
        '    add_trace(1, "M2 YoY", "M2 YoY", COLORS["m2"], 2.8)\n'
        '    add_trace(1, "M2 MoM", "M2 MoM", COLORS["m2_mom"], 2.1, "dash")\n'
        '    add_trace(1, "Monetary Base YoY", "Monetary Base YoY", COLORS["base"], 1.8, "dot")',
        "legacy money traces",
    )
    hk = replace_once(
        hk,
        '    fig.update_yaxes(title_text="YoY (%)", row=1, col=1, zeroline=True, zerolinecolor="#cbd5e1", **grid)',
        '    fig.update_yaxes(title_text="Money Growth (%)", row=1, col=1, zeroline=True, zerolinecolor="#cbd5e1", **grid)',
        "legacy money axis title",
    )

    hk = replace_once(
        hk,
        '    add_line(money, data, "M2 YoY", "M2 YoY", COLORS["m2"], 2.8, secondary_y=False)\n'
        '    add_line(money, data, "M3 YoY", "M3 YoY", COLORS["m3"], 2.3, "dash", secondary_y=False)\n'
        '    add_line(money, data, "Monetary Base YoY", "Monetary Base YoY", COLORS["base"], 1.8, "dot", secondary_y=False)',
        '    add_line(money, data, "M2 YoY", "M2 YoY", COLORS["m2"], 2.8, secondary_y=False)\n'
        '    add_line(money, data, "M2 MoM", "M2 MoM", COLORS["m2_mom"], 2.1, "dash", secondary_y=False)\n'
        '    add_line(money, data, "Monetary Base YoY", "Monetary Base YoY", COLORS["base"], 1.8, "dot", secondary_y=False)',
        "chart 5 money traces",
    )
    hk = replace_once(
        hk,
        '        title_text="Money YoY (%)", secondary_y=False,',
        '        title_text="Money Growth (%)", secondary_y=False,',
        "chart 5 money axis title",
    )

    app = replace_once(
        app,
        '<div class="section-description">HKD M2 / M3 / Monetary Base MoM · Tencent / HKEX (R1) · HSTECH / HSI (R2)</div>',
        '<div class="section-description">M2 YoY / M2 MoM / Monetary Base YoY · Tencent / HKEX (R1) · HSTECH / HSI (R2)</div>',
        "chart 5 section description",
    )

    old_hk_desc = (
        '<b>参数概念：</b><br>1. HKD M2 YoY：港元 M2 同比增速，用来观察广义港元货币的中期扩张或收缩趋势。'
        '<br>2. HKD M3 YoY：港元 M3 同比增速；M3 比 M2 口径更广，但两者在香港通常高度同步，因此主要用于交叉确认货币趋势而不是作为独立方向信号。'
        '<br>3. Monetary Base YoY：香港货币基础总量同比变化，用于观察基础货币的中期扩张与收缩。'
        '<br>4. HKEX Price（R1）：港交所 0388.HK 市场价格，右轴单位 HKD；用于观察香港交易所股价与货币流动性变化之间的市场映射。'
        '<br>5. HSTECH Index（R2）：恒生科技指数 HSTECH 市场点位，右轴单位 points；市场历史独立拉取 5Y，不再被 HKMA 月度快照长度裁断。'
        '<br>6. HSI Index（R2）：恒生指数市场点位，右轴单位 points；使用 ^HSI 的 5Y 市场历史，用于对照香港大盘与流动性变化。'
        '<br>7. Tencent Price（R1）：腾讯控股 0700.HK 股价，Raw 模式与港交所共用 R1 港元价格轴；Rebased 100 模式把可视区间首个有效值归一到 100，便于比较相对弹性。'
        '<br><br><b>市场显示：</b>Raw 模式把股票价格放在 R1、指数点位放在 R2；Rebased 100 模式把 Tencent / HKEX / HSTECH / HSI 统一归一化，用于比较涨跌幅而不是绝对点位。'
    )
    new_hk_desc = (
        '<b>参数概念：</b><br>1. HKD M2 YoY：港元 M2 同比增速，作为主趋势线，用来观察广义港元货币的中期扩张或收缩；相比 MoM 更平滑。'
        '<br>2. HKD M2 MoM：港元 M2 月环比增速，作为边际动量线，用来观察最近一个月货币扩张/收缩是否加速；波动会明显高于 YoY。'
        '<br>3. Monetary Base YoY：香港货币基础总量同比变化，用于观察基础货币的中期扩张与收缩。'
        '<br>4. HKEX Price（R1）：港交所 0388.HK 市场价格，右轴单位 HKD；用于观察香港交易所股价与货币流动性变化之间的市场映射。'
        '<br>5. HSTECH Index（R2）：恒生科技指数 HSTECH 市场点位，右轴单位 points；市场历史独立拉取 5Y，不再被 HKMA 月度快照长度裁断。'
        '<br>6. HSI Index（R2）：恒生指数市场点位，右轴单位 points；使用 ^HSI 的 5Y 市场历史，用于对照香港大盘与流动性变化。'
        '<br>7. Tencent Price（R1）：腾讯控股 0700.HK 股价，Raw 模式与港交所共用 R1 港元价格轴；Rebased 100 模式把可视区间首个有效值归一到 100，便于比较相对弹性。'
        '<br><br><b>读取提示：</b>默认只保留 M2 的同比与环比：YoY 看趋势，MoM 看边际拐点。M3 YoY 仍保留在底层数据中，但因与 M2 YoY 高度同步，不再默认绘制，减少重复信息。'
        '<br><br><b>市场显示：</b>Raw 模式把股票价格放在 R1、指数点位放在 R2；Rebased 100 模式把 Tencent / HKEX / HSTECH / HSI 统一归一化，用于比较涨跌幅而不是绝对点位。'
    )
    app = replace_once(app, old_hk_desc, new_hk_desc, "chart 5 parameter description")

    HK.write_text(hk, encoding="utf-8")
    APP.write_text(app, encoding="utf-8")
    print("refined Chart 5 to M2 YoY + M2 MoM + Monetary Base YoY; M3 YoY retained in data model only")


if __name__ == "__main__":
    main()
