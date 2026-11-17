import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source = await readFile(new URL('../macro_platform/frontend/linked_charts.js', import.meta.url), 'utf8');
const {observePageResume} = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

test('resume is immediate without an animation frame and listeners are disposed', () => {
  const doc = new EventTarget(), win = new EventTarget();
  let calls = 0;
  doc.hidden = true;
  const stop = observePageResume(() => calls++, doc, win);
  doc.dispatchEvent(new Event('visibilitychange'));
  assert.equal(calls, 0);
  doc.hidden = false;
  doc.dispatchEvent(new Event('visibilitychange'));
  assert.equal(calls, 1);
  win.dispatchEvent(new Event('pageshow'));
  assert.equal(calls, 2);
  stop();
  doc.dispatchEvent(new Event('visibilitychange'));
  win.dispatchEvent(new Event('pageshow'));
  assert.equal(calls, 2);
});
