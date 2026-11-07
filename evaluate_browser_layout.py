"""Check the compact dashboard in local headless Edge without opening a window."""
import argparse
import base64
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent


def fixture(equity_open=False):
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
const ids=['board','playerHand','opponentCount','handCount','tableObservation','view','potPanel','equityPanel'];
const rectangles=Object.fromEntries(ids.map(id=>{const r=document.getElementById(id).getBoundingClientRect();return[id,{left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height}]}));
const t=document.querySelector('.seat-table-wrap');
const report={width:innerWidth,height:innerHeight,pageHeight:document.documentElement.scrollHeight,rectangles,tableNeedsScroll:t.scrollHeight>t.clientHeight,canvasSize:[c.width,c.height],aspectError:Math.abs(v.clientWidth/v.clientHeight-c.width/c.height)};
const panelIds=['tableObservation','equityPanel'];
report.populatedHeights=panelIds.map(id=>document.getElementById(id).getBoundingClientRect().height);
renderTableObservation();renderEquity();
report.waitingHeights=panelIds.map(id=>document.getElementById(id).getBoundingClientRect().height);
report.columnScroll=getComputedStyle(document.querySelector('.left-column')).overflowY;
const pre=document.createElement('pre');pre.id='layoutReport';pre.hidden=true;pre.textContent=JSON.stringify(report);document.body.append(pre);
},500);};qaImage.src='data:image/png;base64,PICTURE';
</script>""".replace('PICTURE',picture)
    if equity_open:
        from poker_equity import calculate_equity
        from poker_advice import analyze_decision
        result = calculate_equity(['8C','2C'],['9D','10H','5C','AS','KC'],3,simulations=200,random_seed=17)
        advice = analyze_decision(result,dict(status='ready',hand_id=18,street='river',
                                 pot=dict(value=24,unit='BB'),seats=[],
                                 available_actions_confirmed=[dict(action='call',amount=dict(value=6,unit='BB'))]),18)
        page = page.replace('</body>', '<script>renderEquity('
                            +json.dumps(result)+','+json.dumps(advice)+');</script></body>')
        script = script.replace("'tableObservation','view','potPanel'", "'tableObservation','view','potPanel','equityPanel'")
    return page.replace('</body>',script+'</body>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser',type=Path,default=Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/dashboard-layout')
    parser.add_argument('--equity-open',action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    path = output/'preview.html'
    path.write_text(fixture(args.equity_open),encoding='utf-8')
    reports = []
    for width,height in ((1366,768),(1280,720),(1100,650)):
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
        print(key,json.dumps(report))
        assert report['pageHeight']<=report['height'], 'Pagina oltre la viewport'
        assert not report['tableNeedsScroll'], 'Righe dei giocatori non tutte visibili'
        assert report['aspectError']<.02, 'Proporzioni anteprima alterate'
        assert all(r['bottom']<=report['height'] and r['right']<=report['width']
                   for key,r in report['rectangles'].items() if key not in ('tableObservation','equityPanel'))
        assert report['populatedHeights']==report['waitingHeights']==[360,620], 'Altezza variabile tra misure e attesa'
        assert report['columnScroll']=='auto', 'Pannelli non raggiungibili tramite scorrimento'
        if args.equity_open:
            equity = report['rectangles']['equityPanel']
            assert equity['top'] >= report['rectangles']['tableObservation']['bottom']
            assert equity['right'] <= report['width']
    (output/'report.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
