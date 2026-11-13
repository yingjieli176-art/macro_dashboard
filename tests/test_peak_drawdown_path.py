"""Exercise the actual browser calculation with independent expected paths."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which("node"), "Browser calculation also verified in Chromium CI")
class PeakDrawdownPathTests(unittest.TestCase):
    def test_every_historical_drawdown_without_lookahead_or_zoom_rebasing(self):
        source = Path(__file__).resolve().parents[1] / "macro_platform/frontend/linked_charts.js"
        script = r'''
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const source = readFileSync(process.argv[1], 'utf8');
const {peakDrawdown,dailyPriceTooltip,drawdownDifference,drawdownComparison} = await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
assert.deepEqual(drawdownDifference([['2026-10-01',-.30],['2026-10-02',-4],['2026-10-03',null]],
  [['2026-10-01',-2.55],['2026-10-02',-1],['2026-10-04',-2]]).map(p=>p[1]),[2.25,-3,null,null]);
assert.deepEqual(drawdownDifference([],[]),[]);
assert.match(dailyPriceTooltip({seriesId:'macro-peak-drawdown-difference',value:['2026-10-01',2.25]},[]),/2.25个百分点/);
const points = [['2026-10-01',80],['2026-10-02',100],['2026-10-05',120],
  ['2026-10-06',120],['2026-10-07',90],['2026-10-08',null],
  ['2026-10-09',110],['2026-10-12',130],['2026-10-13',117]];
const before = JSON.stringify(points);
const path = peakDrawdown(points, Date.parse('2026-10-02'), Date.parse('2026-10-07'));
assert.equal(path.peak.day, '2026-10-05'); // Price guide remains the selected high.
assert.equal(path.peak.value,120);
assert.deepEqual(path.data.map(p=>p[0]), points.map(p=>p[0])); // Includes latest beyond right handle.
const expected = [0,0,0,0,-25,null,-8.3333333333,0,-10];
path.data.forEach((p,i)=>expected[i] === null ? assert.equal(p[1],null) : assert.ok(Math.abs(p[1]-expected[i])<1e-8));
assert.equal(JSON.stringify(points),before);
const narrow = peakDrawdown(points,Date.parse('2026-10-12'),Date.parse('2026-10-13'));
assert.equal(narrow.peak.value,130);
assert.deepEqual(narrow.data,path.data);
assert.ok(Math.abs(narrow.data.at(-1)[1]+10)<1e-8);
assert.equal(peakDrawdown(points,Date.parse('2026-10-08'),Date.parse('2026-10-08')).peak,null);
assert.deepEqual(peakDrawdown([],0,Infinity), {peak:null,data:[]});
assert.equal(peakDrawdown([['2026-10-01',Infinity],['2026-10-02',-1]],0,Infinity).peak,null);
assert.equal(drawdownComparison(['沪深300','中证1000','中证2000']).left,2);
assert.equal(drawdownComparison(['中证2000','沪深300']).right,1);
assert.equal(drawdownComparison(['沪深300']),null);
const chinaSmall=peakDrawdown([['2026-10-01',100],['2026-10-02',80],['2026-10-05',120],['2026-10-06',108]],0,Infinity);
const chinaLarge=peakDrawdown([['2026-10-01',100],['2026-10-02',90],['2026-10-05',110],['2026-10-06',110]],0,Infinity);
const chinaDifference=drawdownDifference(chinaSmall.data,chinaLarge.data);
chinaDifference.forEach((point,index)=>assert.ok(Math.abs(point[1]-[0,-10,0,-10][index])<1e-8));
const gaps=peakDrawdown([['2026-10-01',null],['2026-10-02',100],['2026-10-05',NaN],['2026-10-06',90]],0,Infinity);
assert.deepEqual(gaps.data.map(p=>p[1]===null ? null : Number(p[1].toFixed(8))),[null,0,null,-10]);
assert.match(dailyPriceTooltip({seriesId:'macro-peak-drawdown-difference',value:['2026-10-01',-5]},['沪深300','中证1000','中证2000']),/中证2000回撤−沪深300回撤：-5.00个百分点/);
const single = peakDrawdown(points,Date.parse('2026-10-13'),Date.parse('2026-10-13'));
assert.deepEqual(single.data,path.data);
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
