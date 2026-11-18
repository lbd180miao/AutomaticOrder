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
const context = {console, URL, URLSearchParams, AbortSignal, HTMLImageElement: class {},
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
 assert.deepEqual(pending.map(p => p.url), ['?section=rack', '?section=foam', '?section=log']);
 // Keep 3D pending: neither foam nor logs may wait for its response.
 await finish(2, 'rack-ignored', 'foam-ignored');
 assert.deepEqual(replaced, ['log']);
 await finish(1, 'rack-ignored', 'foam-new');
 assert.deepEqual(replaced, ['log', 'foam']);
 assert.equal(cards.rack.outerHTML, 'rack-initial');
 await finish(0, 'rack-new', 'foam-ignored');
 assert.equal(cards.rack.querySelector('.inspection-details').open, true);
 assert.equal(cards.foam.outerHTML, 'foam-new');
 const again = timers.shift()();
 assert.equal(pending[3].url, '?section=log');
 await finish(3, 'rack-ignored', 'foam-ignored');
 await again;
 assert.deepEqual(replaced, ['log', 'foam', 'rack']);
 console.log('PASS: log and foam refresh while 3D is pending; unchanged logs and details are preserved');
})().catch(error => {console.error(error); process.exitCode = 1;});
