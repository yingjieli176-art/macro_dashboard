from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from macro_platform.vix_market import parse_cboe_quote, confirmed_close, append_confirmed_close, write_quote, read_quote


def payload(time="2026-11-05T16:15:01", value=28.18):
    return {"timestamp":"2026-11-06 02:10:15", "data":{
        "symbol":"^VIX", "security_type":"index", "current_price":value,
        "last_trade_time":time}}


NOW = datetime(2026,11,6,2,30,tzinfo=timezone.utc)


class VixMarketTests(unittest.TestCase):
    def test_actual_quote_time_is_used_instead_of_response_time(self):
        quote=parse_cboe_quote(payload(),now=NOW)
        self.assertEqual(quote["observed_at"],"2026-11-05T21:15:01+00:00")
        self.assertEqual(quote["value"],28.18)
        self.assertTrue(quote["delayed"])
        self.assertEqual(confirmed_close(quote,now=NOW),{"date":"2026-11-05","value":28.18})

    def test_intraday_quotes_do_not_become_daily_closes(self):
        quote=parse_cboe_quote(payload(time="2026-11-05T12:45:16",value=26.14),now=NOW)
        self.assertIsNone(confirmed_close(quote,now=NOW))
        quote=parse_cboe_quote(payload(),now=NOW)
        self.assertIsNone(confirmed_close(quote,now=datetime(2026,11,5,21,20,tzinfo=timezone.utc)))

    def test_wrong_index_futures_invalid_and_future_values_rejected(self):
        for key,value in [("symbol","VIX3M"),("symbol","VX=F"),("security_type","future"),
                          ("current_price",0),("current_price",float("nan")),
                          ("current_price",True),("last_trade_time","2026-11-07T16:15:01")]:
            item=payload();item["data"][key]=value
            with self.subTest(key=key,value=value),self.assertRaises((ValueError,TypeError)):
                parse_cboe_quote(item,now=NOW)

    def test_daylight_saving_conversion_keeps_the_exchange_day(self):
        quote=parse_cboe_quote(payload(time="2026-07-02T16:15:01"),now=NOW)
        self.assertEqual(quote["observed_at"],"2026-07-02T20:15:01+00:00")

    def test_only_missing_confirmed_close_is_appended_without_rewriting_history(self):
        quote=parse_cboe_quote(payload(),now=NOW)
        records=[{"date":f"2026-10-{day:02}","value":18.0} for day in range(12,31)]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"VIXCLS.json"
            path.write_text(json.dumps({"series_id":"VIXCLS","records":records}))
            self.assertTrue(append_confirmed_close(quote,path=path,now=NOW))
            saved=json.loads(path.read_text())
            self.assertEqual(saved["records"][:-1],records)
            self.assertEqual(saved["records"][-1],{"date":"2026-11-05","value":28.18})
            before=path.read_bytes()
            self.assertFalse(append_confirmed_close(quote,path=path,now=NOW))
            self.assertEqual(path.read_bytes(),before)

    def test_snapshot_keeps_last_good_quote_and_marks_original_observation_time(self):
        new=parse_cboe_quote(payload(),now=NOW)
        old=parse_cboe_quote(payload(time="2026-11-04T16:15:01",value=16.61),now=NOW)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"quote.json"
            self.assertTrue(write_quote(new,path))
            self.assertFalse(write_quote(old,path))
            saved=read_quote((path,),now=NOW)
            self.assertEqual(saved["value"],28.18)
            self.assertEqual(saved["observed_at"],new["observed_at"])


if __name__ == "__main__":
    unittest.main()
