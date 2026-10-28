"""Exercise the actual browser calculation with independent expected paths."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which("node"), "Browser calculation also verified in Chromium CI")
class PeakDrawdownPathTests(unittest.TestCase):
    def test_fixed_selected_peak_to_current_not_running_peak_or_window_end(self):
        source = Path(__file__).resolve().parents[1] / "macro_platform/frontend/linked_charts.js"
        script = r'''
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const source = readFileSync(process.argv[1], 'utf8');
const {peakDrawdown,dailyPriceTooltip} = await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const points = [['2026-10-01',999],['2026-10-02',100],['2026-10-05',120],
  ['2026-10-06',120],['2026-10-07',90],['2026-10-08',null],
  ['2026-10-09',110],['2026-10-12',130],['2026-10-13',117]];
const before = JSON.stringify(points);
const path = peakDrawdown(points, Date.parse('2026-10-02'), Date.parse('2026-10-07'));
assert.equal(path.peak.day, '2026-10-05'); // Earliest tied high, outside 999 ignored.
assert.equal(path.peak.value,120);
assert.deepEqual(path.data.map(p=>p[0]), points.slice(2).map(p=>p[0])); // Includes latest beyond right handle.
const expected = [0,0,-25,null,-8.3333333333,8.3333333333,-2.5];
path.data.forEach((p,i)=>expected[i] === null ? assert.equal(p[1],null) : assert.ok(Math.abs(p[1]-expected[i])<1e-8));
assert.equal(JSON.stringify(points),before);
const narrow = peakDrawdown(points,Date.parse('2026-10-12'),Date.parse('2026-10-13'));
assert.equal(narrow.peak.value,130);
assert.equal(narrow.data.length,2);
assert.ok(Math.abs(narrow.data[1][1]+10)<1e-8);
assert.deepEqual(peakDrawdown(points,Date.parse('2026-10-08'),Date.parse('2026-10-08')), {peak:null,data:[]});
assert.deepEqual(peakDrawdown([],0,Infinity), {peak:null,data:[]});
assert.equal(peakDrawdown([['2026-10-01',Infinity],['2026-10-02',-1]],0,Infinity).peak,null);
const single = peakDrawdown(points,Date.parse('2026-10-13'),Date.parse('2026-10-13'));
assert.deepEqual(single.data,[['2026-10-13',0,117]]);
const trailing = peakDrawdown([...points,['2026-10-14',null]],Date.parse('2026-10-12'),Date.parse('2026-10-13'));
assert.equal(trailing.data.at(-1)[0],'2026-10-13');
assert.equal(dailyPriceTooltip([{seriesId:'macro-price-0',value:['2026-10-07',90]},
  {seriesId:'macro-peak-drawdown-0',value:['2026-10-07',-25,90]}],['SPX']),
  '2026-10-07\nSPX 收盘：90.00\nSPX 回撤比例：-25.00%');
assert.equal(dailyPriceTooltip({seriesId:'macro-peak-drawdown-0',value:['2026-10-05',0,120]},['沪深300']),
  '2026-10-05\n沪深300 回撤比例：0.00%');
console.log(JSON.stringify({passed:true}));
'''
        result = subprocess.run([shutil.which("node"), "--input-type=module", "-e", script, str(source)],
                                capture_output=True, text=True, check=True)
        self.assertTrue(json.loads(result.stdout)["passed"])


if __name__ == "__main__":
    unittest.main()
