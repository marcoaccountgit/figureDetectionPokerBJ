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

test('equity distinguishes unavailable current metrics, estimates, and clears stale results',()=>{
 const {elements,context}=panel();
 vm.runInContext(`const metric={value:.4,standard_error:.01,ci95:[.38,.42]};
 renderEquity({status:'ready',method:'monte_carlo',complete:false,hero_cards:['As','Kh'],community_cards:[],street:'preflop',opponents_count:2,current_label:null,
 metrics:{win:metric,lose:metric,tie:metric,equity:metric},categories:{'High Card':metric},simulations:5000,processing_ms:200});`,context);
 assert.match(elements.get('equityState').textContent,/progressiva/);
 assert.match(elements.get('equityMeta').textContent,/Prima del flop/);
 assert.match(elements.get('equityTiming').textContent,/IC 95%/);
 const current=descendants(elements.get('equityCurrent'));
 assert.ok(current.some(n=>n.textContent==='Non disponibile'));
 assert.ok(descendants(elements.get('equityFinal')).some(n=>String(n.textContent).includes('≈')));
 vm.runInContext('renderEquity({status:"waiting",message:"Board transitorio"})',context);
 assert.equal(elements.get('equityFinal').children.length,0);
 assert.equal(elements.get('equityCategories').children.length,0);
 assert.equal(elements.get('equityMeta').textContent,'');
 assert.equal(elements.get('equityState').textContent,'Board transitorio');
});

test('equity uses detected opponents unless a valid manual input overrides it',()=>{
 const {elements,context}=panel();
 elements.get('equityOpponents').value='2';
 vm.runInContext('renderOpponents({count:3,pending:false,seats:[]})',context);
 assert.match(elements.get('equityOpponentSource').textContent,/automatico: 3 avversari/);
 assert.equal(elements.get('equityOpponents').disabled,true);
 assert.equal(vm.runInContext('equityOptions().opponents',context),'');
 elements.get('equityManual').checked=true;
 elements.get('equityManual').onchange();
 assert.equal(elements.get('equityManualField').hidden,false);
 assert.equal(vm.runInContext('equityOptions().opponents',context),'2');
 assert.match(elements.get('equityOpponentSource').textContent,/manuale: 2/);
 for(const invalid of ['', '1.5', '6', '-1']){
  elements.get('equityOpponents').value=invalid;
  elements.get('equityOpponents').oninput();
  assert.equal(vm.runInContext('equityOptions().opponents',context),'0');
  assert.match(elements.get('equityOpponentSource').textContent,/numero intero da 1 a 5/);
 }
 elements.get('equityManual').checked=false;
 elements.get('equityManual').onchange();
 assert.equal(vm.runInContext('equityOptions().opponents',context),'');
 assert.equal(elements.get('equityManualField').hidden,true);
});

test('equity translates final categories and current category labels',()=>{
 const {elements,context}=panel();
 vm.runInContext(`const m={value:.5,standard_error:.01,ci95:[.48,.52]};
 renderEquity({status:'ready',method:'monte_carlo',complete:true,hero_cards:['As','Kh'],community_cards:['Qs','Js','Ts'],street:'flop',opponents_count:1,current_label:'Royal Flush',metrics:{equity:m},categories:{'High Card':m,'One Pair':m,'Straight Flush':m},simulations:5000,processing_ms:200});`,context);
 assert.match(elements.get('equityMeta').textContent,/Scala reale/);
 const labels=descendants(elements.get('equityCategories')).map(n=>n.textContent);
 assert.ok(labels.includes('Carta alta'));
 assert.ok(labels.includes('Coppia'));
 assert.ok(labels.includes('Scala colore'));
});

test('conditional advice shows prices and clears them when the next state is incomplete',()=>{
 const {elements,context}=panel();
 vm.runInContext(`renderAdvice({status:'conditional',title:'Indicazione teorica: vedere',message:'Ipotesi da verificare',unit:'BB',pot_before_call:150,call_cost:50,pot_after_call:200,required_equity:.25,equity:.35,margin:.10,expected_value:20,expected_value_ci95:[18,22],complete:false,factors:[{label:'Già davanti',value:.4}],notes:['Non sommare le probabilità'],limits:['Costi futuri esclusi']});`,context);
 assert.match(elements.get('adviceTitle').textContent,/Indicazione teorica/);
 assert.ok(descendants(elements.get('adviceNumbers')).some(n=>n.textContent==='20 BB'));
 assert.ok(descendants(elements.get('adviceNotes')).some(n=>String(n.textContent).includes('provvisoria')));
 vm.runInContext('renderEquity({status:"waiting"})',context);
 assert.equal(elements.get('adviceNumbers').children.length,0);
 assert.equal(elements.get('adviceFactors').children.length,0);
 assert.equal(elements.get('adviceTitle').textContent,'Valutazione in attesa');
});

test('nine-seat tables allow eight manual opponents and display chip units in Italian',()=>{
 const {elements,context}=panel();
 vm.runInContext('renderOpponents({count:8,pending:false,max_opponents:8,seats:[]})',context);
 elements.get('equityManual').checked=true;elements.get('equityOpponents').value='8';
 elements.get('equityManual').onchange();
 assert.equal(elements.get('equityOpponents').max,'8');
 assert.equal(vm.runInContext('equityOptions().opponents',context),'8');
 assert.equal(vm.runInContext('formatAmount({value:1500,unit:"CHIPS"})',context),'1500 fiches');
 vm.runInContext('renderOpponents({count:3,pending:false,max_opponents:5,seats:[]})',context);
 assert.equal(vm.runInContext('equityOptions().opponents',context),'0');
});

test('opponent input follows any supported advertised table capacity',()=>{
 const {elements,context}=panel();
 elements.get('equityManual').checked=true;
 for(const capacity of [5,6,8,9,10]){
  vm.runInContext(`renderOpponents({count:2,pending:false,max_opponents:${capacity-1},seats:[]})`,context);
  elements.get('equityOpponents').value=String(capacity-1);
  assert.equal(elements.get('equityOpponents').max,String(capacity-1));
  assert.equal(vm.runInContext('equityOptions().opponents',context),String(capacity-1));
  elements.get('equityOpponents').value=String(capacity);
  assert.equal(vm.runInContext('equityOptions().opponents',context),'0');
 }
});

test('source picker accepts browser tabs, application windows, monitors and unspecified surfaces',async()=>{
 for(const [surface,label] of [['browser','Scheda'],['window','Finestra'],['monitor','Schermo'],[undefined,'Sorgente condivisa']]){
  const {elements,context}=panel();let requested,stopped=false;
  const track={label:'PokerStars',getSettings:()=>({displaySurface:surface}),stop:()=>{stopped=true;}};
  context.navigator={mediaDevices:{getDisplayMedia:async options=>{
   requested=options;return {getVideoTracks:()=>[track],getTracks:()=>[track]};
  }}};
  context.crypto={randomUUID:()=>String(surface)};
  const video=elements.get('video');video.play=async()=>{};video.videoWidth=1920;video.videoHeight=1080;
  elements.get('view').style={setProperty(){}};
  elements.get('view').classList={add(){},remove(){}};
  elements.get('overlay').getContext=()=>({clearRect(){}});
  await elements.get('choose').onclick();
  assert.equal(elements.get('error').textContent,'');
  assert.equal(elements.get('start').disabled,false);
  assert.equal(elements.get('source').textContent,`Sorgente (${label}): PokerStars`);
  assert.equal(requested.monitorTypeSurfaces,'include');
  assert.equal(requested.video.displaySurface,undefined);
  assert.equal(requested.audio,false);
  track.onended();
  assert.equal(stopped,true);
  assert.equal(elements.get('start').disabled,true);
  assert.equal(video.srcObject,null);
 }
});

test('analysis pixels come directly from the source, independently of the preview size',()=>{
 const {elements,context}=panel();
 const canvas=vm.runInContext('captureCanvas',context);
 let draw;
 canvas.getContext=()=>({drawImage:(...args)=>{draw=args;}});
 elements.get('image').width=300;elements.get('image').height=100;
 const source={videoWidth:1920,videoHeight:1200};context.testSource=source;
 const frame=vm.runInContext('copySourceFrame(testSource)',context);
 assert.equal(frame,canvas);
 assert.equal(frame.width,1920);assert.equal(frame.height,1200);
 assert.equal(draw[0],source);
 assert.deepEqual(draw.slice(1),[0,0,1920,1200]);
 vm.runInContext('renderAlignment({ready:false,profile:"pokerstars-desktop-six"})',context);
 assert.match(elements.get('alignmentStatus').textContent,/sospese/);
 vm.runInContext('renderAlignment({ready:true,profile:"pokerstars-desktop-six"})',context);
 assert.match(elements.get('alignmentStatus').textContent,/Desktop a 6 posti/);
});
