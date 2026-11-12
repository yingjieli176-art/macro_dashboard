"""Stable chart identities, ordered by US, Japan, China/Hong Kong, then assets."""

MACRO_DISPLAY_ORDER = (
    1, 2, 3, 9, 10, "us_drawdown", "nvidia_cds",
    4, "japan_corridor", 15, 16, "japan_holdings",
    14, "cn_drawdown", 5, 6, 7, 8,
    11, 13, "copper_tcrc", 12,
)
MACRO_DISPLAY_NUMBER = {key: index for index, key in enumerate(MACRO_DISPLAY_ORDER, 1)}
DISPLAY_US_CREDIT_JP_CORRIDOR_CN_21_ORDER = tuple(key for key in MACRO_DISPLAY_ORDER if key != "japan_holdings")
PREVIOUS_DISPLAY_ORDER = tuple(key for key in DISPLAY_US_CREDIT_JP_CORRIDOR_CN_21_ORDER if key != "japan_corridor")
CHART_NUMBERING = "display_us_credit_jp_holdings_cn_22"

# Captured source reports before this release used these display positions.
DISPLAY_US_JP_CN_20_ORDER = (1, 2, 3, 9, 10, "us_drawdown", 4, 15, 16,
                            14, "cn_drawdown", 5, 6, 7, 8, 11, 13, "copper_tcrc", 12, "nvidia_cds")
LEGACY_DISPLAY_ORDER = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, "us_drawdown",
                        "cn_drawdown", 14, 15, 11, 13, 12, 16)
LEGACY_TO_DISPLAY = {index: MACRO_DISPLAY_NUMBER[key]
                     for index, key in enumerate(LEGACY_DISPLAY_ORDER, 1)}


def legacy_chart_numbers(numbers):
    return sorted({LEGACY_TO_DISPLAY[number] for number in numbers})

# Runtime builder identities are independent of displayed chart numbers.
NUMERIC_CHART_IDS = tuple(sorted(key for key in MACRO_DISPLAY_ORDER if isinstance(key, int)))
HK_CHART_IDS = (5, 6, 7, 8)
