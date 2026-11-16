import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const source=await fs.readFile(new URL('../macro_platform/frontend/linked_charts.js',import.meta.url),'utf8');
const {asTime,peakDrawdown,compactTooltip,latestObservation,lockRightAxes,presetStart,dateLabel,evenDateTicks,copyPresentation,latestAnchoredRange,containLockedAxes}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const midnight=Date.UTC(2026,10,5);
assert.equal(asTime('2026-11-05'),midnight);
assert.equal(asTime('2026-11-05T00:00:00'),midnight);
assert.equal(asTime('2026-11-05T00:00:00Z'),midnight);
const points=[['2026-11-04T00:00:00',100],['2026-11-05T00:00:00',110]];
const path=peakDrawdown(points,midnight,midnight);
assert.equal(path.peak.value,110);
assert.equal(path.data[0][1],0);
assert(compactTooltip([{seriesName:'SPX',value:[midnight,7353.73]}],{}).startsWith('2026-11-05\n'));
console.log('PASS source date, peak selection and tooltip in',process.env.TZ);

assert.equal(latestObservation({series:[{data:[['2026-11-12',3],['2026-11-13',null]]}]}),'2026-11-12');
const axes={yAxis:[{position:'left'},{position:'right'},{position:'right'}]};
lockRightAxes(axes,new Map([[1,[7000,8000]],[2,[3,4]]]));
assert.equal(axes.yAxis[0].min,undefined);
assert.deepEqual([axes.yAxis[1].min,axes.yAxis[1].max],[7000,8000]);
assert.deepEqual([axes.yAxis[2].min,axes.yAxis[2].max],[3,4]);

assert.equal(latestObservation({series:[{data:[['bad-date',7],['2026-11-12',3]]}]}),'2026-11-12');

assert.equal(new Date(presetStart(Date.UTC(2024,2,31),"1M")).toISOString().slice(0,10),"2024-02-29");
assert.equal(new Date(presetStart(Date.UTC(2024,1,29),"1Y")).toISOString().slice(0,10),"2023-02-28");

assert.equal(dateLabel('2026-11-16'), '26/11-16');
for (const width of [88,286,1200]) for (const days of [1,30,365,1826]) {
  const end=Date.UTC(2026,10,16), start=end-days*86400000;
  const ticks=evenDateTicks(start,end,width);
  assert.equal(ticks.at(-1).time,end);
  assert.equal(ticks.at(-1).label,'26/11-16');
  assert.equal(ticks[0].time,start);
  for (let i=1;i<ticks.length;i++) {
    assert(Math.abs(ticks[i].fraction-ticks[i-1].fraction-1/(ticks.length-1))<1e-10);
    assert.match(ticks[i].label,/^\d{2}\/\d{2}-\d{2}$/);
  }
}
const original={series:[{data:points,lineStyle:{width:2}}],grid:{left:42}};
const presentation=copyPresentation(original);
assert.equal(presentation.series[0].data,points);
presentation.grid.left=99; presentation.series[0].lineStyle.width=9;
assert.equal(original.grid.left,42); assert.equal(original.series[0].lineStyle.width,2);
assert.deepEqual(latestAnchoredRange(20,40),[80,100]);
assert.deepEqual(latestAnchoredRange(0,100),[0,100]);
const bounded={series:[{name:'p',yAxisIndex:1,data:[[1,100],[2,250]]}],yAxis:[{}, {position:'right'}]};
const bounds=new Map([[1,[150,220]]]);
containLockedAxes(bounded,bounds,1,2,{});
assert(bounded.yAxis[1].min<100 && bounded.yAxis[1].max>250);
