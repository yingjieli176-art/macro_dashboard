import ast
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock


def load_functions(names, namespace):
    source = Path(__file__).resolve().parents[1] / "app.py"
    if "requests" in namespace:
        namespace.setdefault("http_get", namespace["requests"].get)
    tree = ast.parse(source.read_text())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    for node in functions:
        node.decorator_list = []
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), namespace)
    return namespace


class RefreshOptimizationTests(unittest.TestCase):
    def yahoo_namespace(self, market_state="REGULAR", overnight=False):
        response = Mock()
        response.json.return_value = {"chart": {"result": [{"meta": {
            "regularMarketPrice": 105.0, "previousClose": 100.0,
            "marketState": market_state, "regularMarketTime": 1234,
        }}]}}
        return load_functions({"_empty_quote", "_symbol_market", "_get_yahoo_quote_safe"}, {
            "requests": SimpleNamespace(get=Mock(return_value=response)),
            "YAHOO_CHART_BASES": ["https://example.test/"],
            "_us_overnight_window_now": lambda: overnight,
            "_get_yahoo_overnight_safe": Mock(return_value=(106.0, 6.0, 1240)),
        })

    def test_daytime_us_quote_skips_unneeded_overnight_requests(self):
        ns = self.yahoo_namespace()
        quote = ns["_get_yahoo_quote_safe"]("NVDA")
        self.assertEqual(quote["price"], 105.0)
        self.assertEqual(quote["change_pct"], 5.0)
        self.assertIsNone(quote["overnight_price"])
        ns["_get_yahoo_overnight_safe"].assert_not_called()

    def test_asian_quotes_skip_us_overnight_requests_even_during_us_night(self):
        ns = self.yahoo_namespace(overnight=True)
        for symbol in ("0700.HK", "600160.SS"):
            with self.subTest(symbol=symbol):
                self.assertEqual(ns["_get_yahoo_quote_safe"](symbol)["price"], 105.0)
        ns["_get_yahoo_overnight_safe"].assert_not_called()

    def test_overnight_quotes_remain_available_by_clock_or_provider_state(self):
        for state, clock in (("CLOSED", True), ("PREPRE", False), ("POSTPOST", False)):
            with self.subTest(state=state, clock=clock):
                ns = self.yahoo_namespace(state, clock)
                quote = ns["_get_yahoo_quote_safe"]("NVDA")
                self.assertEqual(quote["overnight_price"], 106.0)
                self.assertEqual(quote["overnight_market_time"], 1240)
                ns["_get_yahoo_overnight_safe"].assert_called_once_with("NVDA", 100.0)

    def test_failed_news_fetch_preserves_last_successful_update_time(self):
        previous = {"items": [{"title": "cached news"}], "updated_at": "2026-09-30T14:00:00+08:00"}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "news.json"
            clock = Mock()
            clock.now.return_value.isoformat.return_value = "2026-09-30T15:00:00+08:00"
            fetch = Mock(return_value=([], "source unavailable"))
            ns = load_functions({"_write_news_snapshot"}, {
                "NEWS_STATIC_PATH": path, "fetch_eastmoney_news": fetch,
                "_read_existing_news_snapshot": lambda: previous,
                "datetime": clock, "DASHBOARD_TZ": None, "json": json, "os": os,
            })
            ns["_write_news_snapshot"]()
            failed = json.loads(path.read_text())
            self.assertEqual(failed["items"], previous["items"])
            self.assertEqual(failed["updated_at"], previous["updated_at"])
            self.assertTrue(failed["error"])

            fetch.return_value = ([{"title": "fresh news"}], None)
            ns["_write_news_snapshot"]()
            recovered = json.loads(path.read_text())
            self.assertEqual(recovered["updated_at"], "2026-09-30T15:00:00+08:00")
            self.assertIsNone(recovered["error"])
            self.assertEqual(recovered["items"][0]["title"], "fresh news")

    def test_manual_overview_refresh_bypasses_same_time_bucket_cache(self):
        state = {}
        quotes = {name: {} for name in ("nasdaq", "sp500", "dow", "hsi", "hstech", "sh", "sz", "csi300")}
        loader = Mock(return_value=quotes)
        ns = load_functions({"render_market_groups"}, {
            "time": SimpleNamespace(time=lambda: 1000),
            "st": SimpleNamespace(session_state=state, markdown=Mock()),
            "_quote_refresh_key": lambda: 7, "_load_market_quotes": loader,
            "_active_quote_values": lambda row, market: (None, None),
            "_quote_meta": lambda row, market: "",
            "_market_item_html": lambda *args: "",
        })
        ns["render_market_groups"]()
        ns["render_market_groups"]()
        loader.assert_called_once_with((7, 0))
        state["_market_quotes_snapshot_time"] = 0
        state["_market_refresh_key"] = 1
        ns["render_market_groups"]()
        self.assertEqual(loader.call_count, 2)
        loader.assert_called_with((7, 1))


    def _fragment_test_namespace(self):
        state = {}
        chart = object()
        builder = Mock(return_value=["rebuilt"])
        st = SimpleNamespace(
            markdown=Mock(), radio=Mock(side_effect=AssertionError("Market display toggle was removed")),
        )
        ns = load_functions(
            {"_render_hk_macro_chart", "render_macro_chart_10", "render_macro_chart_11"},
            {
                "st": st,
                "HK_CHART_CONFIGS": [
                    ("title", "description", "hk_5_range", []),
                    ("title", "description", "hk_6_range", []),
                    ("title", "description", "hk_7_range", []),
                    ("title", "description", "hk_8_range", []),
                ],
                "_safe_hk_bundle": builder,
                "_macro_snapshot_revision": lambda: "snap",
                "_render_adaptive_macro_figure": Mock(),
                "show_hk_parameter_description": Mock(),
                "add_sources": Mock(),
                "_safe_macro_build": Mock(side_effect=lambda label, callback: callback()),
                "_cached_macro_figure": Mock(return_value="rebuilt"),
                "CHART_BUILD": "perf-test",
                "US_EQUITY_RISK_DESCRIPTION": "",
                "PRECIOUS_METALS_DESCRIPTION": "",
                "CRYPTO_MARKET_DESCRIPTION": "",
            },
        )
        return ns, state, chart, builder

    def test_hk_prebuilt_chart_is_reused_without_display_toggle(self):
        ns, state, chart, bundle = self._fragment_test_namespace()
        ns["_render_hk_macro_chart"](0, chart)
        bundle.assert_not_called()
        ns["_render_adaptive_macro_figure"].assert_called_with(chart, "hk_5_range")
        ns["_render_hk_macro_chart"](0)
        bundle.assert_called_once_with("snap")
        ns["_render_adaptive_macro_figure"].assert_called_with("rebuilt", "hk_5_range")

    def test_metals_and_crypto_initial_render_does_not_duplicate_data_build(self):
        for no, name in ((10, "precious_metals"), (11, "crypto_market")):
            with self.subTest(chart=no):
                ns, state, chart, _ = self._fragment_test_namespace()
                ns[f"render_macro_chart_{no}"](chart)
                ns["_cached_macro_figure"].assert_not_called()
                ns["_render_adaptive_macro_figure"].assert_called_with(chart, name)
                ns[f"render_macro_chart_{no}"]()
                ns["_cached_macro_figure"].assert_called_once_with(no, "snap", "perf-test")
                ns["_render_adaptive_macro_figure"].assert_called_with("rebuilt", name)

    def test_time_range_inputs_are_isolated_to_us_fragments(self):
        app = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
        tree = ast.parse(app)
        functions = {
            node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
        }
        for n in range(1, 5):
            method = functions[f"render_macro_chart_{n}"]
            self.assertTrue(any(
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and dec.func.attr == "fragment"
                for dec in method.decorator_list
            ))
        self.assertIn("on_complete=_render_completed_macro_chart", app)
        for number in (5, 8, 10, 11):
            self.assertIn(f"{number}: render_macro_chart_{number}", app)
        self.assertIn("@st.cache_data(ttl=300", app)
        # Charts 5, 8, 10 and 11 already have fragments; all remaining
        # macro charts now need them to avoid a full rerun on time clicks.
        for number in (6, 7, 9, 12, 13):
            function = functions[f"render_macro_chart_{number}"]
            self.assertTrue(any(
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "fragment"
                for decorator in function.decorator_list
            ), f"Chart {number} must isolate date-control reruns")


if __name__ == "__main__":
    unittest.main()

