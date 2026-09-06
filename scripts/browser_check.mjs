// Optional local Chromium/Yandex CDP check; application itself needs only Python.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';

const root = path.resolve(import.meta.dirname, '..');
const out = path.join(root, 'output', 'demo');
fs.mkdirSync(out, {recursive: true});
const pages = await (await fetch('http://127.0.0.1:9222/json/list')).json();
const socket = new WebSocket(pages.find(p => p.type === 'page').webSocketDebuggerUrl);
await new Promise((resolve, reject) => {socket.onopen = resolve; socket.onerror = reject;});
let nextId = 0;
const pending = new Map(), exceptions = [];
socket.onmessage = event => {
  const message = JSON.parse(event.data);
  if (message.method === 'Runtime.exceptionThrown') exceptions.push(message.params);
  if (message.id && pending.has(message.id)) {
    const {resolve, reject, timer} = pending.get(message.id);
    clearTimeout(timer); pending.delete(message.id);
    message.error ? reject(new Error(JSON.stringify(message.error))) : resolve(message.result);
  }
};
function send(method, params={}) {
  return new Promise((resolve, reject) => {
    const id = ++nextId;
    const timer = setTimeout(() => {pending.delete(id); reject(new Error('CDP timeout: '+method));}, 10000);
    pending.set(id, {resolve, reject, timer});
    socket.send(JSON.stringify({id, method, params}));
  });
}
async function evaluate(expression) {
  const result = await send('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
  if(result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
}
async function until(expression) {
  for(let i=0;i<50;i++) {if(await evaluate(expression)) return; await new Promise(r=>setTimeout(r,100));}
  throw new Error('Condition timeout: '+expression);
}
async function screenshot(name) {
  const shot = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: false});
  fs.writeFileSync(path.join(out,name+'.png'), Buffer.from(shot.data,'base64'));
}
await send('Runtime.enable'); await send('Page.enable');
await send('Emulation.setDeviceMetricsOverride', {width: 1360, height: 1120, deviceScaleFactor: 1, mobile: false});
await send('Page.navigate', {url: 'http://127.0.0.1:8765/'});
await until("typeof online !== 'undefined' && online");
await evaluate("document.getElementById('receipt-input').value = JSON.stringify({...bundle.families[family].fixture, receipt_id:'browser-check-001'},null,2)");
const before = await evaluate('bundle.families[family].state.points');
assert.equal(before,0,'Use a fresh --db for the visual test');
await screenshot('01_before');
await evaluate("document.getElementById('submit').click()");
await until("bundle.families[family].state.challenge_completed === true");
const points = await evaluate('bundle.families[family].state.points');
const completedState = await evaluate('bundle.families[family].state');
await screenshot('02_completed');
await evaluate("document.getElementById('duplicate').click()");
await until("document.getElementById('message').textContent.includes('Повтор распознан')");
assert.equal(await evaluate('bundle.families[family].state.points'),points);
await screenshot('03_duplicate');
await evaluate("document.getElementById('cancel').click()");
await until("bundle.families[family].state.points === 0");
await screenshot('04_returned');
await send('Emulation.setDeviceMetricsOverride', {width: 390, height: 844, deviceScaleFactor: 1, mobile: true});
await screenshot('05_mobile');
assert.equal(await evaluate('document.documentElement.scrollWidth > innerWidth'), false, 'Mobile horizontal overflow');
assert.deepEqual(exceptions, []);
// Render a compact receipt from the actual server response, not invented slide numbers.
const receiptHtml = '<!doctype html><html lang="ru"><meta charset="utf-8"><style>body{margin:0;padding:22px;background:white;font:18px/1.55 monospace;color:#163f2b}main{border:1px solid #cfd8ca;border-radius:10px;padding:20px}h1{font-size:23px}hr{border:0;border-top:1px dashed #a2b89c}small{font-size:14px}.value{font-weight:bold;font-size:24px}</style><main><h1>РАСТЁМ ВМЕСТЕ</h1><p>Ивановы · тестовый чек</p><hr><p>Экономия к цели<br><span class="value">'+(completedState.totals.goal_saving_minor/100)+' ₽</span></p><p>Демо-баллы<br><span class="value">'+completedState.points+'</span></p><p>Рост семьи<br><span class="value">'+completedState.growth_cm+' см</span></p><hr><p>Цель выполнена ✓</p><small>Состояние получено из API.<br>Реальных начислений X5 нет.<br>Кассовая печать не подключена.</small></main></html>';
fs.writeFileSync(path.join(out,'receipt.html'),receiptHtml);
await send('Emulation.setDeviceMetricsOverride', {width: 390, height: 650, deviceScaleFactor: 1, mobile: false});
await evaluate('document.open();document.write('+JSON.stringify(receiptHtml)+');document.close()');
await screenshot('06_receipt');
fs.writeFileSync(path.join(out,'browser_report.json'),JSON.stringify({status:'passed',viewport_desktop:[1360,1120],viewport_mobile:[390,844],before_points:before,earned_points:points,duplicate_points:points,returned_points:0,uncaught_exceptions:exceptions,checks:['actual button -> HTTP -> SQLite -> DOM','duplicate','return','mobile overflow']},null,2));
console.log('PASS: browser submit, duplicate, return, desktop/mobile; screenshots in output/demo');
socket.close();
