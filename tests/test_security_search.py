import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from macro_platform.security_search import search_securities, eastmoney_matches, yahoo_matches


class SecuritySearchTests(unittest.TestCase):
    def test_chinese_alias_and_padded_hk_code_work_without_remote_search(self):
        get = Mock(side_effect=TimeoutError)
        for query in ("小米", "小米集团", "Xiaomi", "1810", "01810", "1810.HK"):
            with self.subTest(query=query):
                result = search_securities("HK", query, get=get)
                self.assertEqual(result["items"][0]["symbol"], "1810.HK")
                self.assertEqual(result["items"][0]["name"], "小米集团-W")
                self.assertFalse(result["unavailable"])
        get.assert_not_called()

    def test_chinese_provider_maps_etf_and_keeps_market_boundaries(self):
        payload = {"QuotationCodeTable": {"Data": [
            {"Code": "159740", "Name": "恒生科技ETF", "QuoteID": "0.159740"},
            {"Code": "600000", "Name": "浦发银行", "QuoteID": "1.600000"},
            {"Code": "01810", "Name": "小米集团-W", "QuoteID": "116.01810"},
        ]}}
        self.assertEqual([r["symbol"] for r in eastmoney_matches(payload, "CN")], ["159740.SZ", "600000.SS"])
        self.assertEqual([r["symbol"] for r in eastmoney_matches(payload, "HK")], ["1810.HK"])

    def test_remote_name_search_uses_domestic_provider_and_deduplicates(self):
        response = Mock()
        response.json.return_value = {"QuotationCodeTable": {"Data": [
            {"Code": "00981", "Name": "中芯国际", "QuoteID": "116.00981"},
            {"Code": "00981", "Name": "中芯国际", "QuoteID": "116.00981"},
        ]}}
        get = Mock(return_value=response)
        result = search_securities("HK", "中芯", get=get)
        self.assertEqual([r["symbol"] for r in result["items"]], ["0981.HK"])
        self.assertIn("eastmoney", get.call_args.args[0])

    def test_yahoo_fallback_accepts_etfs_and_filters_other_markets(self):
        payload = {"quotes": [
            {"symbol": "ARKK", "shortname": "ARK Innovation ETF", "quoteType": "ETF"},
            {"symbol": "159740.SZ", "quoteType": "ETF"},
            {"symbol": "1810.HK", "quoteType": "EQUITY"},
            {"symbol": "GC=F", "quoteType": "FUTURE"},
        ]}
        self.assertEqual([r["symbol"] for r in yahoo_matches(payload, "US")], ["ARKK"])
        self.assertEqual([r["symbol"] for r in yahoo_matches(payload, "CN")], ["159740.SZ"])

    def test_unavailable_service_is_distinct_from_successful_empty_result(self):
        failed = search_securities("HK", "不存在的查询词", get=Mock(side_effect=TimeoutError))
        self.assertEqual(failed, {"items": [], "unavailable": True})
        response = Mock()
        response.json.return_value = {"QuotationCodeTable": {"Data": []}, "quotes": []}
        empty = search_securities("HK", "不存在的查询词", get=Mock(return_value=response))
        self.assertEqual(empty, {"items": [], "unavailable": False})

    def test_query_change_clears_old_selection_and_market_is_preserved(self):
        source = Path(__file__).resolve().parents[1] / "app.py"
        node = next(n for n in ast.parse(source.read_text()).body
                    if isinstance(n, ast.FunctionDef) and n.name == "_run_search")
        state = {"market_search_hk": "小米", "market_search_hk_result_select": 7}
        namespace = {"st": SimpleNamespace(session_state=state), "_search_market": search_securities}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
        namespace["_run_search"]("market_search_hk", "HK")
        self.assertNotIn("market_search_hk_result_select", state)
        self.assertEqual(state["market_search_hk_results"][0]["market"], "HK")
        state["market_search_hk"] = ""
        namespace["_run_search"]("market_search_hk", "HK")
        self.assertNotIn("market_search_hk_results", state)

