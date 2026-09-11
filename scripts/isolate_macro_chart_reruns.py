from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"


def main() -> None:
    text = APP.read_text(encoding="utf-8")
    old = "compact_mode = False\n\ndef render_core_charts():"
    new = "compact_mode = False\n\n@st.fragment\ndef render_core_charts():"
    if new in text:
        print("macro charts already isolated")
        return
    if old not in text:
        raise RuntimeError("render_core_charts marker changed")
    text = text.replace(old, new, 1)
    APP.write_text(text, encoding="utf-8")
    print("macro chart controls now rerun only the chart fragment")


if __name__ == "__main__":
    main()
