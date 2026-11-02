"""Stable chart identities, regional reading order and source-report numbering."""

# Numeric identities refer to existing builders/session keys, not positions.
DISPLAY_ORDER = (1, 2, 3, 4, "us_drawdown", 9, 10, 11, 13, 12,
                 15, 16, 5, 6, 7, 8, 14, "cn_drawdown")
DISPLAY_NUMBER = {key: index for index, key in enumerate(DISPLAY_ORDER, 1)}
NUMBERING = "regions_us_jp_hk_cn_v1"
REGION_HEADERS = {
    1: "美国与全球市场 / US & GLOBAL MARKETS",
    15: "日本 / JAPAN",
    5: "香港 / HONG KONG",
    14: "中国 / CHINA",
}

# Archived reports and source declarations use the former 18-chart positions.
LEGACY_ORDER = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, "us_drawdown", "cn_drawdown",
                14, 15, 11, 13, 12, 16)
LEGACY_TO_CURRENT = {index: DISPLAY_NUMBER[key] for index, key in enumerate(LEGACY_ORDER, 1)}


def current_chart_numbers(numbers, numbering="display_18"):
    if numbering == NUMBERING:
        return sorted(set(numbers))
    if numbering in {"display_17", "display_18"}:
        return sorted({LEGACY_TO_CURRENT[number] for number in numbers})
    return None
