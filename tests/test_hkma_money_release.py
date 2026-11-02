"""Original published amounts must repair API gaps without inventing observations."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import hkma_money_release as money
from scripts import audit_source_freshness as audit
from scripts import probe_all_sources as probe
from scripts.update_hkma_snapshot import _parse_proxy_json
from scripts.update_hkma_monetary_base_history import _parse_transport_text

TEXT = """(HK$ Million)
Sep 2026 Aug 2026 Jun 2026 Sep 2025
M2 - HK$2
9,491,899 9,573,225 (-0.8) 9,283,575 (2.2) 8,830,160 (7.5)
Foreign currency 12,781,535
M3 - HK$2
9,505,133 9,586,157 (-0.8) 9,295,677 (2.3) 8,843,704 (7.5)
Total 22,317,144
2. Adjusted to include foreign currency swap deposits.
TABLE 1A : HONG KONG MONETARY STATISTICS - September 2026
"""


class OfficialMoneyRelease(unittest.TestCase):
    def tearDown(self):
        probe.reset_probe_cache()

    def test_adjusted_hkd_amounts_are_read_without_growth_based_reconstruction(self):
        row = money.parse_release_text(TEXT, "2026-09")
        self.assertEqual(row, {"end_of_month":"2026-09", "m2_hkd":9491899.0, "m3_hkd":9505133.0})
        for bad in (TEXT.replace("September 2026", "August 2026"),
                    TEXT.replace("HK$ Million", "US$ Million"),
                    TEXT.replace("Adjusted to include", "Unadjusted to include"),
                    TEXT.replace("9,505,133", "8,505,133")):
            with self.subTest(text=bad), self.assertRaises(ValueError):
                money.parse_release_text(bad, "2026-09")

    def test_discovered_annex_is_dated_and_preserves_provenance(self):
        article = "https://www.hkma.gov.hk/eng/news-and-media/press-releases/2026/10/20261030-7/"
        annex = "https://www.hkma.gov.hk/media/eng/doc/key-information/press-release/2026/20261030e7a1.pdf"
        responses = [Mock(text=f'<a href="{article}" title="Monetary Statistics for September 2026">Release</a>'),
                     Mock(text=f'<a href="{annex}">Annex</a>'), Mock(content=b'%PDF-fixture')]
        page = Mock(); page.extract_text.return_value = TEXT
        reader = Mock(); reader.pages = [page]
        get = Mock(side_effect=responses)
        with patch("pypdf.PdfReader", return_value=reader):
            row = money.fetch_latest_money_release(get=get, now=datetime(2026,11,2,tzinfo=timezone.utc))
        self.assertEqual(row["m2_hkd"], 9491899)
        self.assertEqual(row["money_source_url"], annex)
        self.assertEqual(row["money_release_url"], article)
        self.assertEqual(len(row["money_source_sha256"]), 64)
        self.assertEqual(get.call_count, 3)
        with self.assertRaises(ValueError):
            money.fetch_latest_money_release(get=Mock(return_value=responses[0]),
                                            now=datetime(2026,10,1,tzinfo=timezone.utc))

    def test_release_fills_api_nulls_without_overwriting_precise_observations(self):
        release = dict(money.parse_release_text(TEXT,"2026-09"), **{k:"source" for k in money.PROVENANCE_FIELDS})
        monthly={"2026-08":{"end_of_month":"2026-08","m2_hkd":9573224.866,"m3_hkd":9586156.603}}
        self.assertTrue(money.merge_release_pair(monthly, release))
        self.assertEqual(monthly["2026-09"]["m2_hkd"],9491899)
        monthly["2026-09"]["m2_hkd"]=9491899.123
        self.assertFalse(money.merge_release_pair(monthly, release))
        self.assertEqual(monthly["2026-09"]["m2_hkd"],9491899.123)
        self.assertEqual(monthly["2026-08"]["m2_hkd"],9573224.866)

    def test_proxy_envelope_text_and_direct_json_share_strict_validation(self):
        payload={"header":{"success":True},"result":{"records":[{"end_of_month":"2026-09"}]*60}}
        for text in (json.dumps(payload), "Markdown Content:\n"+json.dumps(payload),
                     json.dumps({"code":200,"data":{"content":json.dumps(payload)}})):
            with self.subTest(text=text[:30]):
                self.assertEqual(_parse_proxy_json(text),payload)
                self.assertEqual(len(_parse_transport_text(text)),60)
        for payload in ({"header":{"success":False}}, {"data":{"content":"not JSON"}}, []):
            with self.assertRaises((ValueError,RuntimeError)):
                _parse_proxy_json(json.dumps(payload))

    def test_probe_reads_the_latest_published_month_once_for_both_money_fields(self):
        row=dict(money.parse_release_text(TEXT,"2026-09"), money_source_url="official-annex")
        with patch.object(money,"fetch_latest_money_release",return_value=row) as get:
            for field in ("m2_hkd","m3_hkd"):
                self.assertEqual(probe.hkma_money(field),("2026-09-30","official-annex"))
            get.assert_called_once()

    def test_initial_audit_can_report_for_repair_but_final_audit_still_fails(self):
        report={"file":"money.json","record_issues":{},"invalid_snapshot":False,
                "latest_by_name":{"m2_hkd":"2026-08-31"},"due_by_name":{"m2_hkd":"2026-11-01"},
                "stale_names":["m2_hkd"],"future_names":[],"missing_names":[]}
        with tempfile.TemporaryDirectory() as folder, patch.object(audit,"audit",return_value=[report]):
            output=str(Path(folder)/"report.json")
            with patch("sys.argv",["audit","--output",output,"--report-only"]):
                audit.main()
            self.assertTrue(Path(output).exists())
            with patch("sys.argv",["audit","--output",output]), self.assertRaises(SystemExit):
                audit.main()


if __name__ == "__main__":
    unittest.main()
