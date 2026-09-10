from pathlib import Path


PATH = Path("data.py")
text = PATH.read_text(encoding="utf-8")

old = '''@st.cache_data(ttl=3600)
def get_dgs10(): return _fred_series("DGS10")
'''
new = '''@st.cache_data(ttl=3600)
def get_dgs10():
    """Return 10Y nominal Treasury yield with an identity-based fallback.

    Prefer the direct FRED DGS10 series. If that route is temporarily missing
    observations, backfill only those missing dates from DFII10 + T10YIE.
    FRED defines the 10Y breakeven rate from nominal less real yield, so this
    preserves the chart without inventing unrelated market data.
    """
    direct = _fred_series("DGS10").copy()
    real = _fred_series("DFII10").copy()
    breakeven = _fred_series("T10YIE").copy()

    derived = real.merge(breakeven, on="observation_date", how="inner")
    if not derived.empty:
        derived["DGS10"] = (
            pd.to_numeric(derived["DFII10"], errors="coerce")
            + pd.to_numeric(derived["T10YIE"], errors="coerce")
        )
        derived = derived.dropna(subset=["observation_date", "DGS10"])[["observation_date", "DGS10"]]

    if direct.empty:
        if derived.empty:
            return direct
        result = derived.sort_values("observation_date").drop_duplicates("observation_date", keep="last")
        result.attrs.update({
            "source": "Derived from FRED DFII10 + T10YIE",
            "is_stale": bool(real.attrs.get("is_stale") or breakeven.attrs.get("is_stale")),
            "is_fallback": True,
            "derived_fallback": True,
        })
        return result

    if derived.empty:
        return direct

    # Prefer observed DGS10 where available; use the identity only to fill gaps.
    combined = direct.merge(derived, on="observation_date", how="outer", suffixes=("_direct", "_derived"))
    combined["DGS10"] = combined["DGS10_direct"].combine_first(combined["DGS10_derived"])
    result = combined.dropna(subset=["observation_date", "DGS10"])[["observation_date", "DGS10"]]
    result = result.sort_values("observation_date").drop_duplicates("observation_date", keep="last")
    result.attrs = dict(direct.attrs)
    result.attrs["identity_backfill"] = True
    return result
'''

if new in text:
    print("DGS10 fallback already applied")
elif old not in text:
    raise RuntimeError("get_dgs10 patch target not found")
else:
    PATH.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("DGS10 fallback applied")
