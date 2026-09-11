from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"
DECORATOR = "@st.cache_data(ttl=300, show_spinner=False)\n"


def add_cache(text: str, func_name: str) -> str:
    marker = f"def {func_name}("
    pos = text.find(marker)
    if pos < 0:
        raise RuntimeError(f"missing function: {func_name}")
    line_start = text.rfind("\n", 0, pos) + 1
    before = text[max(0, line_start - len(DECORATOR)):line_start]
    if DECORATOR in before:
        return text
    return text[:line_start] + DECORATOR + text[line_start:]


def main() -> None:
    text = APP.read_text(encoding="utf-8")

    # Cache rendered Plotly figures briefly. The underlying macro series already
    # have longer data caches; this prevents every Streamlit widget rerun from
    # rebuilding all charts and re-running merges / styling work.
    for func_name in (
        "build_fig1", "build_fig2", "build_fig3", "build_fig4", "build_fig5",
        "build_fig9", "build_fig10", "build_fig11",
    ):
        text = add_cache(text, func_name)

    # HK charts 5-8 are currently produced together by build_fig5. The page calls
    # that wrapper once per HK panel; caching it collapses four identical 1Y/Raw
    # builds on initial load into one build and makes later range reruns cheap.
    text = add_cache(text, "get_hk_liquidity")

    # Plotly does not need responsive transitions/animations for this monitoring
    # dashboard. Disabling transitions reduces browser work when a cached figure
    # is replaced after a range switch.
    old = 'PLOTLY_CONFIG = {"displayModeBar": False, "scrollZoom": False, "doubleClick": False, "editable": False, "displaylogo": False}'
    new = 'PLOTLY_CONFIG = {"displayModeBar": False, "scrollZoom": False, "doubleClick": False, "editable": False, "displaylogo": False, "responsive": True}'
    if old in text:
        text = text.replace(old, new, 1)
    elif new not in text:
        raise RuntimeError("PLOTLY_CONFIG marker changed")

    APP.write_text(text, encoding="utf-8")
    print("dashboard runtime caches applied")


if __name__ == "__main__":
    main()
