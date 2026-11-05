const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// Exercise the actual page renderers without requesting screen permissions.
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.textContent = ''; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
}
function panel() {
  const elements = new Map();
  const document = {
    getElementById(id) { if (!elements.has(id)) elements.set(id, new Element('div')); return elements.get(id); },
    createElement(tag) { return new Element(tag); },
    createDocumentFragment() { return new Element('fragment'); },
  };
  const context = vm.createContext({ document, URLSearchParams,
    location: {search:'?token=test'}, Image: class {}, window:{addEventListener(){}},
  });
  const html = fs.readFileSync(require('node:path').join(__dirname,'../browser_ui.html'),'utf8');
  vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1], context);
  return {elements, context};
}
function descendants(node) {
  return [node,...(node.children || []).filter(n=>typeof n==='object').flatMap(descendants)];
}
test('board and hand retain codes and display the correct suit images',()=>{
  const {elements,context} = panel();
  vm.runInContext("renderBoard([{accepted:true,card:'7S'},{accepted:true,card:'2D'}]);renderHand([{accepted:true,card:'4H'},{accepted:true,card:'8C'}]);",context);
  for (const [id,expected] of [['board',['picche','quadri']],['playerHand',['cuori','fiori']]]) {
    const nodes = descendants(elements.get(id));
    assert.deepEqual(nodes.filter(n=>n.tagName==='img').map(n=>n.alt),expected);
    assert.ok(nodes.filter(n=>n.tagName==='img').every(n=>n.src.startsWith('data:image/svg+xml,')));
  }
  assert.equal(elements.get('board').children.length,5);
  assert.equal(elements.get('playerHand').children.length,2);
});
test('counter distinguishes zero opponents from a pending observation and resets',()=>{
  const {elements,context} = panel();
  vm.runInContext("renderOpponents({count:0,pending:false,players_with_cards:1,seats:[]})",context);
  assert.equal(elements.get('opponentCount').textContent,0);
  vm.runInContext("renderOpponents({count:null,pending:true,seats:[]})",context);
  assert.equal(elements.get('opponentCount').textContent,'—');
  assert.match(elements.get('opponentState').textContent,/Verifica/);
  vm.runInContext('renderOpponents();renderBoard();renderHand();',context);
  assert.equal(elements.get('opponentState').textContent,'In attesa di scansione');
  assert.equal(descendants(elements.get('playerHand')).filter(n=>n.tagName==='img').length,0);
});
test('hand count starts at zero, updates independently of card reading, and resets on new capture',()=>{
  const {elements,context} = panel();
  assert.equal(elements.get('handCount').textContent,0);
  vm.runInContext('renderHandCount({count:2});renderHand();',context);
  assert.equal(elements.get('handCount').textContent,2);
  vm.runInContext('renderHandCount()',context);
  assert.equal(elements.get('handCount').textContent,0);
});
