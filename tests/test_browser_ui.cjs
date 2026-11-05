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
  for (const match of html.matchAll(/\bid="([^"]+)"/g)) document.getElementById(match[1]);
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
test('table observation separates available controls, performed actions and uncertain positions',()=>{
  const {elements,context} = panel();
  vm.runInContext(`renderTableObservation({status:'ready',button:'top',pot:{value:0,unit:'BB'},contribution:null,
   seats:[{seat:'hero',name:'<Check>',position:null,position_estimate:'BB',action:'call',stack:{value:20,unit:'BB'},wager:{value:2,unit:'BB'}}],
   available_actions:[{text:'Fold',action:'fold'}],events:[{hand_id:1,street:'flop',seat:'hero',action:'call',amount:{value:2,unit:'BB'}}]});`,context);
  assert.equal(elements.get('observedPot').textContent,'0 BB');
  assert.match(elements.get('offeredActions').textContent,/non azioni eseguite.*Fold/);
  const cells=elements.get('observedSeats').children[0].children;
  assert.equal(cells[0].textContent,'Tu · <Check>');
  assert.equal(cells[1].textContent,'BB (?)');
  assert.match(cells[1].title,/da verificare/);
  assert.equal(cells[2].textContent,'call');
  assert.equal(elements.get('observedEvents').children.length,1);
  assert.match(elements.get('observedEvents').children[0].textContent,/call.*totale street/);
});
test('stale, pending and OCR errors do not show old table values or reset hand count',()=>{
  const {elements,context} = panel();
  vm.runInContext('renderHandCount({count:4});',context);
  for (const status of ['pending','stale','error']) {
    vm.runInContext(`renderTableObservation({status:'${status}',error:'Nessuna lingua OCR'});`,context);
    assert.equal(elements.get('observedSeats').children.length,0);
    assert.equal(elements.get('observedPot').textContent,'—');
    assert.equal(elements.get('handCount').textContent,4);
  }
  assert.match(elements.get('tableReadStatus').textContent,/OCR: Nessuna lingua/);
});
test('street pot snapshots and collected chips are displayed as different amounts',()=>{
  const {elements,context} = panel();
  vm.runInContext(`renderTableObservation({status:'ready',button:'top',pot:{value:14,unit:'BB'},collected_pot:{value:10,unit:'BB'},contribution:null,
    seats:[],available_actions:[],events:[],street_pots:{flop:{first_total:{value:8,unit:'BB'}},turn:{first_total:{value:12,unit:'BB'}}}});`,context);
  assert.equal(elements.get('observedPot').textContent,'14 BB');
  assert.equal(elements.get('collectedPot').textContent,'10 BB');
  assert.equal(elements.get('streetPots').textContent,'Flop: 8 BB · Turn: 12 BB · River: —');
  vm.runInContext('renderTableObservation({status:"pending"})',context);
  assert.equal(elements.get('collectedPot').textContent,'—');
  assert.equal(elements.get('streetPots').textContent,'Flop: — · Turn: — · River: —');
});
test('visible pot panel uses the actual central amount and latest collected amount for each street',()=>{
  const {elements,context} = panel();
  vm.runInContext(`renderTableObservation({status:'ready',button:'top',pot:{value:14,unit:'BB'},collected_pot:{value:10,unit:'BB'},
   seats:[],available_actions:[],events:[],street_pots:{flop:{first_total:{value:8,unit:'BB'},last_collected:{value:9,unit:'BB'}},turn:{last_collected:{value:10,unit:'BB'}}}});`,context);
  assert.equal(elements.get('centerPotValue').textContent,'10 BB');
  assert.equal(elements.get('tablePotValue').textContent,'14 BB');
  assert.equal(elements.get('centerPotByStreet').textContent,'Flop: 9 BB · Turn: 10 BB · River: —');
  vm.runInContext(`renderTableObservation({status:'ready',pot:{value:14,unit:'BB'},collected_pot:null,seats:[],available_actions:[],events:[]});`,context);
  assert.equal(elements.get('centerPotValue').textContent,'—');
  assert.match(elements.get('potReadStatus').textContent,/in lettura/);
  vm.runInContext(`renderTableObservation({status:'ready',pot:{value:0,unit:'BB'},collected_pot:{value:0,unit:'BB'},seats:[],available_actions:[],events:[]});`,context);
  assert.equal(elements.get('centerPotValue').textContent,'0 BB');
  vm.runInContext('renderTableObservation();',context);
  assert.equal(elements.get('centerPotValue').textContent,'—');
  assert.equal(elements.get('centerPotByStreet').textContent,'Flop: — · Turn: — · River: —');
});
test('opponent reliability disclosure reports observed verification without invented accuracy',()=>{
  const {elements,context} = panel();
  vm.runInContext("renderOpponents({count:3,pending:false,players_with_cards:4,seats:[{confirmed:true},{confirmed:true},{confirmed:false}]})",context);
  assert.equal(elements.get('opponentCount').textContent,3);
  assert.equal(elements.get('opponentReliabilityValue').textContent,'2/3 posti verificati');
  vm.runInContext('renderOpponents()',context);
  assert.equal(elements.get('opponentReliabilityValue').textContent,'Nessuna verifica disponibile');
});
test('preview fits both dimensions without changing captured canvas resolution',()=>{
  const {elements,context} = panel();
  const stage=elements.get('previewStage'),view=elements.get('view'),canvas=elements.get('image');
  stage.clientWidth=600;stage.clientHeight=300;
  view.style={getPropertyValue:()=>String(16/9)};
  canvas.width=1854;canvas.height=954;
  vm.runInContext('fitCapturePreview()',context);
  assert.ok(Math.abs(parseFloat(view.style.width)-300*16/9)<.01);
  stage.clientWidth=400;
  vm.runInContext('fitCapturePreview()',context);
  assert.equal(view.style.width,'400px');
  assert.equal(canvas.width,1854);
  assert.equal(canvas.height,954);
});
