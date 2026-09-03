import streamlit as st

# Temporary clean launcher for verification.
# The original dashboard is preserved as dashboard.py.
original_set_page_config = st.set_page_config
st.set_page_config = lambda *args, **kwargs: None

verify = st.empty()
verify.info("TEST LAUNCHER: app.py is running")

try:
    with open("dashboard.py", "r", encoding="utf-8") as f:
        dashboard_code = f.read()
    exec(compile(dashboard_code, "dashboard.py", "exec"), globals(), globals())
except Exception as exc:
    st.exception(exc)
finally:
    verify.success("BUILD 2026-09-03 · app.py + dashboard.py loaded")
    st.image("test_image.svg", width=160)
