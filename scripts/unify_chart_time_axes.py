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


def patch_app() -> None:
    text = APP.read_text(encoding="utf-8")

    if "from macro_platform.chart_axes import apply_time_axis" not in text:
        text = replace_once(
            text,
            "from macro_platform.hk_liquidity import build_hk_liquidity_figure, build_hk_liquidity_figures, load_hk_liquidity\n",
            "from macro_platform.hk_liquidity import build_hk_liquidity_figure, build_hk_liquidity_figures, load_hk_liquidity\n"
            "from macro_platform.chart_axes import apply_time_axis\n",
            "app axis import",
        )

    text = replace_once(
        text,
        "    base_top = 115 if compact_mode else 105\n",
        "    # Reserve separate vertical bands for the top year axis and legend.\n"
        "    base_top = 128 if compact_mode else 124\n",
        "app top margin",
    )

    text = replace_once(
        text,
        '            orientation="h", yanchor="bottom", y=1.08, xanchor="left", x=0,\n',
        '            orientation="h", yanchor="bottom", y=1.17, xanchor="left", x=0,\n',
        "app legend position",
    )

    text = replace_once(
        text,
        "    fig.update_xaxes(fixedrange=True)\n    fig.update_yaxes(fixedrange=True)\n    return fig\n",
        "    fig.update_xaxes(fixedrange=True)\n"
        "    fig.update_yaxes(fixedrange=True)\n"
        "    # Shared adaptive lower axis + centered upper year axis for charts 1-4.\n"
        "    return apply_time_axis(fig, date_range)\n",
        "app shared time-axis call",
    )

    start = text.index("def apply_hk_chart_range(fig, date_range):")
    end = text.index("\ndef build_fig1(date_range):", start)
    replacement = '''def apply_hk_chart_range(fig, date_range):
    """Apply the same dashboard-wide adaptive time axis to charts 5-8."""
    return apply_time_axis(fig, date_range)
'''
    text = text[:start] + replacement + text[end:]

    APP.write_text(text, encoding="utf-8")


def patch_hk() -> None:
    text = HK.read_text(encoding="utf-8")

    if "from macro_platform.chart_axes import apply_time_axis" not in text:
        text = replace_once(
            text,
            "from plotly.subplots import make_subplots\n",
            "from plotly.subplots import make_subplots\n\nfrom macro_platform.chart_axes import apply_time_axis\n",
            "HK axis import",
        )

    text = replace_once(
        text,
        "            margin=dict(l=62, r=82 if right_axis else 28, t=96, b=44, pad=2),\n",
        "            # Top margin has two dedicated rows: centered year labels, then legend.\n"
        "            margin=dict(l=62, r=82 if right_axis else 28, t=124, b=54, pad=2),\n",
        "HK top margin",
    )

    text = replace_once(
        text,
        '                orientation="h", yanchor="bottom", y=1.08, xanchor="left", x=0,\n',
        '                orientation="h", yanchor="bottom", y=1.17, xanchor="left", x=0,\n',
        "HK legend position",
    )

    style_start = text.index("    def style(fig: go.Figure, title: str, height: int = 430, right_axis: bool = False) -> go.Figure:")
    style_end = text.index("\n    # 5-1", style_start)
    style_block = text[style_start:style_end]
    if "return apply_time_axis(fig, date_range)" not in style_block:
        if style_block.count("        return fig") != 1:
            raise RuntimeError("HK style return: expected one return fig")
        style_block = style_block.replace(
            "        return fig",
            "        # Initialize charts 5-8 with the same two-level time axis as charts 1-4.\n"
            "        return apply_time_axis(fig, date_range)",
            1,
        )
        text = text[:style_start] + style_block + text[style_end:]

    HK.write_text(text, encoding="utf-8")


def main() -> None:
    patch_app()
    patch_hk()
    print("unified adaptive time axes across charts 1-8")


if __name__ == "__main__":
    main()
