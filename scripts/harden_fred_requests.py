from pathlib import Path

path = Path("data.py")
text = path.read_text(encoding="utf-8")

if "from io import StringIO" not in text:
    text = text.replace("import time\n", "import time\nfrom io import StringIO\n", 1)

start = text.index("def _fred_series(series_id):")
end = text.index("\n@st.cache_data(ttl=3600)\ndef get_dgs3mo", start)

replacement = r'''FRED_GRAPH_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_FRED_LAST_GOOD = {}


def _normalize_fred_frame(frame, series_id):
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["observation_date", series_id])
    work = frame.copy()
    date_col = "observation_date" if "observation_date" in work.columns else work.columns[0]
    value_col = series_id if series_id in work.columns else (work.columns[1] if len(work.columns) > 1 else None)
    if value_col is None:
        return pd.DataFrame(columns=["observation_date", series_id])
    work["observation_date"] = pd.to_datetime(work[date_col], errors="coerce")
    work[series_id] = pd.to_numeric(work[value_col], errors="coerce")
    return (
        work.dropna(subset=["observation_date", series_id])
        .sort_values("observation_date")
        .drop_duplicates("observation_date", keep="last")[["observation_date", series_id]]
    )


def _fetch_fred_graph(series_id):
    response = requests.get(
        FRED_GRAPH_URL,
        params={"id": series_id},
        headers={"User-Agent": "MacroDashboard/1.0"},
        timeout=(2.5, 5.0),
    )
    response.raise_for_status()
    frame = pd.read_csv(StringIO(response.text))
    frame = _normalize_fred_frame(frame, series_id)
    if frame.empty:
        raise RuntimeError(f"FRED graph {series_id} 没有返回有效数据。")
    frame.attrs.update({"source": "FRED graph CSV", "is_stale": False, "is_fallback": False})
    return frame


def _fetch_fred_api(series_id):
    if not FRED_API_KEY:
        raise RuntimeError("FRED_API_KEY 未设置")
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "asc",
    }
    response = requests.get(FRED_API_URL, params=params, timeout=(2.5, 5.0))
    response.raise_for_status()
    rows = []
    for item in (response.json() or {}).get("observations", []):
        value = item.get("value")
        if value in (None, "", "."):
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        rows.append({"observation_date": item.get("date"), series_id: value})
    frame = _normalize_fred_frame(pd.DataFrame(rows), series_id)
    if frame.empty:
        raise RuntimeError(f"FRED API {series_id} 没有返回有效数据。")
    frame.attrs.update({"source": "FRED API", "is_stale": False, "is_fallback": True})
    return frame


def _fred_series(series_id):
    """Retrieve a FRED series without allowing a transient network error to crash the app.

    The public graph CSV endpoint is preferred because it does not depend on an
    API key. The authenticated API is a secondary route. A successful frame is
    retained as process-local last-known-good data. If both live routes fail,
    return that real prior frame marked stale; on a cold start return an empty,
    explicitly unavailable frame rather than manufacturing observations.
    """
    errors = []
    for fetcher in (_fetch_fred_graph, _fetch_fred_api):
        try:
            frame = fetcher(series_id)
            if not frame.empty:
                saved = frame.copy()
                saved.attrs = dict(frame.attrs)
                saved.attrs["fetched_at"] = time.time()
                _FRED_LAST_GOOD[series_id] = saved
                return frame
        except Exception as exc:
            errors.append(f"{fetcher.__name__}: {type(exc).__name__}: {exc}")

    previous = _FRED_LAST_GOOD.get(series_id)
    if isinstance(previous, pd.DataFrame) and not previous.empty:
        stale = previous.copy()
        stale.attrs = dict(previous.attrs)
        stale.attrs.update({
            "is_stale": True,
            "is_fallback": True,
            "fallback_reason": " | ".join(errors),
        })
        return stale

    empty = pd.DataFrame(columns=["observation_date", series_id])
    empty.attrs.update({
        "source": "FRED unavailable",
        "is_stale": True,
        "is_fallback": True,
        "unavailable": True,
        "fallback_reason": " | ".join(errors),
    })
    return empty
'''

text = text[:start] + replacement + text[end:]
path.write_text(text, encoding="utf-8")
print("FRED resilience patch applied")
