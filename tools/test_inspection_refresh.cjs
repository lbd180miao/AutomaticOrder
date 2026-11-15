const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('templates/devices/status.html', 'utf8').split('<script>')[1].split('</script>')[0];
const cards = {};
const replaced = [];
function card(kind, value) {
  const details = kind === 'log' ? null : {open: false};
  return {dataset: {inspection: kind}, outerHTML: value, querySelector: s => s === '.inspection-details' ? details : null,
    querySelectorAll: () => [], replaceWith(next) {cards[kind] = next; replaced.push(kind);}};
}
for (const kind of ['rack', 'foam', 'log']) cards[kind] = card(kind, kind + '-initial');
const kindOf = selector => selector.match(/data-inspection="(\w+)"/)[1];
const grid = {querySelector: s => s.startsWith('#') ? null : cards[kindOf(s)],
 querySelectorAll: s => s === '[data-inspection]' ? Object.values(cards) : [], addEventListener() {}};
const pending = [], timers = [];
const context = {console, URL, URLSearchParams, HTMLImageElement: class {},
 document: {hidden: false, getElementById: id => id === 'latest-inspections' ? grid : null,
 createElement: () => ({set innerHTML(text) {const data = JSON.parse(text); this.content = {querySelector: s => card(kindOf(s), data[kindOf(s)])};}})},
 window: {setTimeout: fn => timers.push(fn)}, fetch: (url) => new Promise(resolve => pending.push({url, resolve}))};
vm.runInNewContext(source, context);
async function finish(index, rack, foam) {
 pending[index].resolve({ok:true, text: async () => JSON.stringify({rack, foam, log: 'latest-log'})});
 await new Promise(resolve => setImmediate(resolve));
}
(async () => {
 cards.rack.querySelector('.inspection-details').open = true;
 const first = timers.shift()();
 assert.equal(pending[0].url, '?section=inspections');
 await finish(0, 'rack-new', 'foam-new');
 await first;
 assert.equal(cards.rack.querySelector('.inspection-details').open, true);
 assert.equal(cards.foam.querySelector('.inspection-details').open, false);
 assert.deepEqual(replaced, ['rack', 'foam', 'log']);
 const second = timers.shift()();
 await finish(1, 'rack-new', 'foam-newer');
 await second;
 assert.deepEqual(replaced, ['rack', 'foam', 'log', 'foam']);
 assert.equal(cards.foam.outerHTML, 'foam-newer');
 console.log('PASS: polling updates the latest inspections');
})().catch(error => {console.error(error); process.exitCode = 1;});
