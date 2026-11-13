"""Check the compact dashboard in local headless Edge without opening a window."""
import argparse
import base64
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent


def fixture(equity_open=False,discarded_hand=False):
    page = (ROOT/'browser_ui.html').read_text(encoding='utf-8')
    picture = base64.b64encode((ROOT/'artifacts/capture10-improvement/dataset/reviewed/80.png').read_bytes()).decode()
    script = """<script>
renderBoard(['9D','10H','5C','AS','KC'].map(card=>({card,accepted:true})));
renderHand(['8C','2C'].map(card=>({card,accepted:true})));
renderHandCount({count:18});document.getElementById('status').textContent='Scansione in diretta';
document.getElementById('record').textContent='Ferma registrazione';
renderOpponents({count:3,pending:false,players_with_cards:4,seats:[1,2,3,4,5].map(n=>({label:'Posto '+n,confirmed:true,in_hand:n<4}))});
renderTableObservation({status:'ready',button:'top',pot:{value:24,unit:'BB'},collected_pot:{value:18,unit:'BB'},contribution:{value:6,unit:'BB'},
seats:['top','upper_right','lower_right','hero','lower_left','upper_left'].map((seat,i)=>({seat,name:'Giocatore'+(i+1),position:['BTN','SB','BB','UTG','HJ','CO'][i],action:i===1?'raise':null,stack:{value:70+i,unit:'BB'},wager:i===1?{value:6,unit:'BB'}:null})),available_actions:[{text:'Vedi',action:'call',amount:{value:6,unit:'BB'}}],events:[],street_pots:{flop:{first_total:{value:6,unit:'BB'},last_collected:{value:6,unit:'BB'}},turn:{first_total:{value:18,unit:'BB'},last_collected:{value:18,unit:'BB'}}}});
const qaImage=new Image();qaImage.onload=()=>{
const c=document.getElementById('image'),v=document.getElementById('view');c.width=qaImage.width;c.height=qaImage.height;c.getContext('2d').drawImage(qaImage,0,0);c.hidden=false;document.getElementById('overlay').hidden=false;document.getElementById('empty').hidden=true;v.style.setProperty('--capture-aspect',c.width/c.height);fitCapturePreview();
setTimeout(()=>{fitCapturePreview();
const ids=['board','playerHand','opponentCount','handCount','tableObservation','view','potPanel','equityPanel','handProbabilities','opponentThreatPanel','equityFinal','equityCurrent','equityCategories'];
const rectangles=Object.fromEntries(ids.map(id=>{const r=document.getElementById(id).getBoundingClientRect();return[id,{left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height}]}));
const t=document.querySelector('.seat-table-wrap');
const report={width:innerWidth,height:innerHeight,pageHeight:document.documentElement.scrollHeight,rectangles,tableNeedsScroll:t.scrollHeight>t.clientHeight,canvasSize:[c.width,c.height],aspectError:Math.abs(v.clientWidth/v.clientHeight-c.width/c.height)};
report.overflow=Array.from(document.querySelectorAll('.left-column,.right-column,#equityContent,#handProbabilities,#opponentThreatPanel,.board-slot strong')).filter(e=>e.checkVisibility()).filter(e=>e.scrollHeight>e.clientHeight+1||e.scrollWidth>e.clientWidth+1).map(e=>({id:e.id||e.className,client:[e.clientWidth,e.clientHeight],scroll:[e.scrollWidth,e.scrollHeight]}));
report.outside=Array.from(document.querySelectorAll('main h2,main p,main .equity-row,main .board-slot,main .threat-table tr')).filter(e=>e.checkVisibility()).filter(e=>{const r=e.getBoundingClientRect();return r.bottom>innerHeight+1||r.right>innerWidth+1||r.left<0;}).map(e=>e.id||e.textContent);
const reading=document.getElementById('tableObservation'),probabilities=document.getElementById('handProbabilities');
const before=probabilities.getBoundingClientRect().top;reading.open=true;
const expanded=reading.querySelector('.table-observation-content').getBoundingClientRect();
report.readingOverlayFits=expanded.left>=0&&expanded.right<=innerWidth&&expanded.bottom<=innerHeight;
report.readingMovesPanels=Math.abs(before-probabilities.getBoundingClientRect().top)>1;reading.open=false;
const pre=document.createElement('pre');pre.id='layoutReport';pre.hidden=true;pre.textContent=JSON.stringify(report);document.body.append(pre);
},500);};qaImage.src='data:image/png;base64,PICTURE';
</script>""".replace('PICTURE',picture)
    if discarded_hand:
        script=script.replace("renderHand(['8C','2C'].map(card=>({card,accepted:true})));",
            "renderHand(['QH','JS'].map(card=>({card,accepted:true})),{count:17,active:true});"
            "renderHand([],{count:17,active:false,ended:true});"
            "renderHand(['8C','2C'].map(card=>({card,accepted:true})),{count:18,active:true});")
        script=script.replace("'board','playerHand','opponentCount'","'board','playerHand','discardedHandPanel','opponentCount'")
    if equity_open:
        from poker_equity import calculate_equity
        from poker_advice import analyze_decision
        result = calculate_equity(['8C','2C'],['9D','10H','5C','AS','KC'],3,simulations=200,random_seed=17,backend='python')
        advice = analyze_decision(result,dict(status='ready',hand_id=18,street='river',
                                 pot=dict(value=24,unit='BB'),seats=[],
                                 available_actions_confirmed=[dict(action='call',amount=dict(value=6,unit='BB'))]),18)
        result['bet_model'] = dict(status='ready', message='Ipotesi sulle puntate confermate.',unit='BB',seats=[])
        result['bet_scenario'] = dict(result)
        page = page.replace('</body>', '<script>renderEquity('
                            +json.dumps(result)+','+json.dumps(advice)+','+json.dumps(advice)+');'
                            +"renderPotSummary({status:'ready',pot:{value:24,unit:'BB'},collected_pot:{value:18,unit:'BB'},street_pots:{}});"
                            +'</script></body>')
        script = script.replace("'tableObservation','view','potPanel'", "'tableObservation','view','potPanel','equityPanel'")
    return page.replace('</body>',script+'</body>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser',type=Path,default=Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/dashboard-layout')
    parser.add_argument('--equity-open',action='store_true')
    parser.add_argument('--discarded-hand',action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    path = output/'preview.html'
    path.write_text(fixture(args.equity_open,args.discarded_hand),encoding='utf-8')
    reports = []
    for width,height in ((1920,1080),(1366,768),(1280,720),(1100,650)):
        key = f'{width}x{height}'
        command = [str(args.browser),'--headless','--disable-gpu','--no-first-run',
                   '--disable-background-networking','--no-default-browser-check','--hide-scrollbars',
                   '--virtual-time-budget=2000',f'--window-size={width},{height}',
                   '--user-data-dir='+str(output/('edge-qa-'+key)),
                   '--screenshot='+str(output/(key+'.png')),'--dump-dom',path.as_uri()]
        result = subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace',
                                timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        match = re.search(r'<pre id="layoutReport" hidden="">(.*?)</pre>',result.stdout,re.S)
        if not match:
            raise RuntimeError(result.stderr[-1500:])
        report = json.loads(match[1])
        report['requested_window'] = [width,height]
        reports.append(report)
        (output/(key+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(key, 'viewport', report['width'], report['height'], 'overflow', report['overflow'], 'outside', report['outside'])
        assert report['pageHeight']<=report['height'], 'Pagina oltre la viewport'
        assert report['aspectError']<.02, 'Proporzioni anteprima alterate'
        assert all(r['bottom']<=report['height'] and r['right']<=report['width']
                   for key,r in report['rectangles'].items()), 'Pannello fuori dalla viewport'
        assert not report['overflow'], 'Contenuto richiede scorrimento: '+str(report['overflow'])
        assert not report['outside'], 'Informazioni fuori dalla viewport: '+str(report['outside'])
        assert report['readingOverlayFits'] and not report['readingMovesPanels'], 'La tendina sposta i pannelli o esce dalla vista'
        if args.discarded_hand:
            discarded=report['rectangles']['discardedHandPanel']
            assert discarded['width']>0, 'Carte scartate nascoste'
            assert discarded['top']>=report['rectangles']['playerHand']['bottom'], 'Carte scartate sovrapposte alla mano'
            assert discarded['width']<=report['rectangles']['playerHand']['width']+1, 'Carte scartate non compatte'
        if args.equity_open:
            equity = report['rectangles']['equityPanel']
            assert equity['right'] <= report['width']
    (output/'report.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
