"""Stable chart identities, ordered by US, Japan, China/Hong Kong, then assets."""

MACRO_DISPLAY_ORDER = (1, 2, 3, 9, 10, "us_drawdown", 4, 15, 16,
                       14, "cn_drawdown", 5, 6, 7, 8, 11, 13, 12, "nvidia_cds")
MACRO_DISPLAY_NUMBER = {key: index for index, key in enumerate(MACRO_DISPLAY_ORDER, 1)}
CHART_NUMBERING = "display_us_jp_cn_19"

# Captured source reports before this release used these display positions.
LEGACY_DISPLAY_ORDER = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, "us_drawdown",
                        "cn_drawdown", 14, 15, 11, 13, 12, 16)
LEGACY_TO_DISPLAY = {index: MACRO_DISPLAY_NUMBER[key]
                     for index, key in enumerate(LEGACY_DISPLAY_ORDER, 1)}


def legacy_chart_numbers(numbers):
    return sorted({LEGACY_TO_DISPLAY[number] for number in numbers})

