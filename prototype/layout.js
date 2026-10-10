/* Everseen floor layout: offline-capable vanilla JS, no external 3D/CDN dependency. */
'use strict';
const $ = id => document.getElementById(id);
const COLS=12,ROWS=8;
let draft={version:1,sections:[]},saved=null,config={cameras:[]},report=null,selected=null;
let pending=false,drag=null,roll=0,refreshing=false,rotX=57,rotZ=-25,zoom=1;
const modelColors={missing:'#516478',empty:'#4b1d63',one:'#963a79',mid:'#e97668',high:'#f9c9ab'};
const fields=['sectionName','sectionRole','sectionX','sectionY','sectionW','sectionH'];
function clone(v){return JSON.parse(JSON.stringify(v))}
function inform(msg,error=false){$('status').textContent=msg;$('status').style.color=error?'#ffb0ad':'#8df2d9'}
function markDirty(){pending=true;$('dirty').textContent='● Unsaved layout';$('dirty').style.color='#ffc58b'}
function markClean(){pending=false;$('dirty').textContent='All changes saved';$('dirty').style.color='#93eaca'}
async function request(url,opts){const r=await fetch(url,opts);const obj=await r.json().catch(()=>({}));if(!r.ok)throw Error(obj.detail||'Request failed: '+r.status);return obj}
function elected(){return draft.sections.find(s=>s.id===selected)}
function clamp(n,min,max){return Math.min(max,Math.max(min,n))}
function overlaps(a,b){return a.x<b.x+b.w&&b.x<a.x+a.w&&a.y<b.y+b.h&&b.y<a.y+a.h}
function fits(s){return s.x>=0&&s.y>=0&&s.w>=1&&s.h>=1&&s.x+s.w<=COLS&&s.y+s.h<=ROWS&&!draft.sections.some(t=>t.id!==s.id&&overlaps(s,t))}
function occupied(x,y,w,h){return draft.sections.some(t=>overlaps({x,y,w,h},t))}
function freshMetrics(s){return report?.sections?.find(r=>r.id===s.id)}
function fillTileStyle(node,s){node.style.left=(100*s.x/COLS)+'%';node.style.top=(100*s.y/ROWS)+'%';node.style.width=(100*s.w/COLS)+'%';node.style.height=(100*s.h/ROWS)+'%'}
function updateProperties(){
 const s=elected();$('properties').hidden=!s;$('editorEmpty').hidden=!!s;
 if(!s)return;
 $('sectionName').value=s.name;$('sectionRole').value=s.role||'other';
 for(const key of ['x','y','w','h'])$('section'+key.toUpperCase()).value=s[key];
 const options=$('zoneLinks');options.replaceChildren();
 let any=false;
 for(const camera of config.cameras||[]){for(const zone of camera.zones||[]){
   any=true;const element=document.createElement('label');element.className='link-option';
   const check=document.createElement('input');check.type='checkbox';
   check.checked=s.links?.some(link=>link.camera_id===camera.id&&link.zone_id===zone.id)||false;
   check.onchange=()=>{if(check.checked){s.links.push({camera_id:camera.id,zone_id:zone.id})}else{s.links=s.links.filter(l=>l.camera_id!==camera.id||l.zone_id!==zone.id)}markDirty();paintMetrics();render3d()};
   const name=document.createElement('span');name.textContent=`${camera.name||camera.id} · ${zone.label||zone.id}`;
   element.append(check,name);options.append(element);
 }}
 if(!any){const p=document.createElement('p');p.className='hint';p.textContent='No camera zones available. Open Live Operations, draw polygons, then return to map them here.';options.append(p)}
}
function select(id){selected=id;renderEditor();updateProperties();render3d()}
function renderEditor(){
 const editor=$('editor');editor.replaceChildren();
 for(const section of draft.sections){
   const tile=document.createElement('div');tile.className='edit-tile'+(section.id===selected?' selected':'');
   tile.dataset.id=section.id;fillTileStyle(tile,section);
   const title=document.createElement('strong');title.textContent=section.name;
   const count=document.createElement('em');const m=freshMetrics(section);count.textContent=m?.count!=null?`${m.count} observed`:'Not mapped / offline';
   const handle=document.createElement('span');handle.className='resize';handle.title='Drag to resize';
   tile.append(title,count,handle);
   tile.addEventListener('pointerdown',e=>{
     if(e.button!==0)return;
     e.preventDefault();e.stopPropagation();
     selected=section.id;
     const origin=clone(section),rect=editor.getBoundingClientRect();
     drag={id:section.id,origin,mode:e.target===handle?'resize':'move',startX:e.clientX,startY:e.clientY,rect,changed:false};
     tile.setPointerCapture(e.pointerId);renderSelectionOnly();updateProperties();
   });
   tile.addEventListener('pointermove',e=>{
     if(!drag||drag.id!==section.id)return;
     const stepX=Math.round((e.clientX-drag.startX)/(drag.rect.width/COLS));
     const stepY=Math.round((e.clientY-drag.startY)/(drag.rect.height/ROWS));
     const next={...drag.origin};
     if(drag.mode==='move'){next.x=clamp(next.x+stepX,0,COLS-next.w);next.y=clamp(next.y+stepY,0,ROWS-next.h)}
     else{next.w=clamp(next.w+stepX,1,COLS-next.x);next.h=clamp(next.h+stepY,1,ROWS-next.y)}
     if(!fits(next))return;
     Object.assign(section,next);fillTileStyle(tile,section);
     drag.changed=drag.changed||JSON.stringify(next)!==JSON.stringify(drag.origin);
     if(drag.changed){markDirty();render3d()}
   });
   const release=()=>{if(drag&&drag.id===section.id){drag=null;renderEditor();updateProperties()}};
   tile.addEventListener('pointerup',release);tile.addEventListener('pointercancel',release);
   editor.append(tile);
 }
}
function renderSelectionOnly(){for(const tile of $('editor').children){tile.classList.toggle('selected',tile.dataset.id===selected)}}
function sectionId(){return 'section_'+Date.now().toString(36)+'_'+Math.random().toString(36).slice(2,6)}
function addSection(){
 const preferred=[[0,6],[2,6],[4,6],[6,6],[8,6],[10,6],[0,0],[2,0],[4,0],[6,0],[8,0],[10,0]];
 let location=preferred.find(([x,y])=>!occupied(x,y,2,2));
 let w=2,h=2;
 if(!location){outer:for(let y=0;y<ROWS;y++)for(let x=0;x<COLS;x++){if(!occupied(x,y,1,1)){location=[x,y];w=1;h=1;break outer}}}
 if(!location){inform('No free grid squares. Resize or remove a section first.',true);return}
 const s={id:sectionId(),name:'New section '+(draft.sections.length+1),role:'other',x:location[0],y:location[1],w,h,links:[]};
 draft.sections.push(s);markDirty();select(s.id);paintMetrics();inform('Section added. Drag it into position and map camera zones.')
}
function exampleLayout(){
 if(draft.sections.length&&!confirm('Replace your unsaved layout with a demonstration schematic? Save first if needed.'))return;
 const examples=[['Entrance','entrance',4,6,4,2],['North Aisle','aisle',0,3,4,3],['Central Display','display',4,3,4,3],['Right Aisle','aisle',8,3,4,3],['Rear Checkout','checkout',0,0,4,3],['Back Display','display',4,0,4,3],['Exit','exit',8,0,4,3]];
 draft.sections=examples.map(([name,role,x,y,w,h],i)=>({id:'example_'+i,name,role,x,y,w,h,links:[]}));
 selected=draft.sections[0].id;markDirty();renderEditor();updateProperties();render3d();paintMetrics();inform('Example schematic created. Map real camera zones before interpreting the colors or insights.')
}
function updateSection(){
 const s=elected();if(!s)return;
 const proposed={...s,name:$('sectionName').value.trim(),role:$('sectionRole').value};
 for(const key of ['x','y','w','h'])proposed[key]=Number($('section'+key.toUpperCase()).value);
 if(!proposed.name||proposed.name.length>80){inform('Enter a section name of 1–80 characters.',true);return}
 if(['x','y','w','h'].some(k=>!Number.isInteger(proposed[k]))||!fits(proposed)){inform('Invalid position, size, or overlapping grid boxes.',true);return}
 Object.assign(s,proposed);markDirty();renderEditor();updateProperties();render3d();paintMetrics();inform('Section updated. Save floor plan to keep the changes.')
}
function removeSection(){const s=elected();if(!s)return;if(!confirm('Delete '+s.name+' from the draft layout?'))return;
 draft.sections=draft.sections.filter(x=>x.id!==s.id);selected=draft.sections[0]?.id||null;markDirty();renderEditor();updateProperties();render3d();paintMetrics()}
async function save(){try{
 const result=await request('/api/layout',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(draft)});
 saved=clone(draft);markClean();inform(`Saved ${result.sections} sections. Topology and metrics refreshed.`);await refresh()
 }catch(e){inform(e.message,true)}}
function discard(){if(pending&&!confirm('Discard changes to the floor plan?'))return;
 draft=clone(saved||{version:1,sections:[]});selected=draft.sections[0]?.id||null;markClean();renderEditor();updateProperties();render3d();paintMetrics();inform('Restored the saved layout.')}
function colorFor(m){if(!m||m.count==null)return modelColors.missing;if(m.count===0)return modelColors.empty;if(m.count===1)return modelColors.one;if(m.count<=3)return modelColors.mid;return modelColors.high}
function render3d(){
 const floor=$('orbitFloor');floor.replaceChildren();const base=document.createElement('div');base.className='orbit-base';floor.append(base);
 for(const section of draft.sections){
   const m=freshMetrics(section),count=m?.count;
   const tile=document.createElement('div');tile.className='floor-3d-tile'+(count==null?' no-feed':'');
   fillTileStyle(tile,section);tile.style.background=`linear-gradient(135deg,${colorFor(m)}d9,#ffffff17)`;
   if(section.id===selected)tile.style.borderColor='#a2fff1';
   const name=document.createElement('div');name.className='tile-label';name.textContent=section.name;
   const people=document.createElement('div');people.className='people-set';
   for(let n=0;n<Math.min(6,count||0);n++){const human=document.createElement('span');human.className='person3d';human.setAttribute('aria-label','Observed person');people.append(human)}
   if(count>6){const more=document.createElement('span');more.className='tile-more';more.textContent='+'+(count-6);people.append(more)}
   const amount=document.createElement('div');amount.className='tile-count';amount.textContent=count==null?'No data':`${count} seen`;
   tile.append(name,people,amount);floor.append(tile);
 }
 rotateFloor();
}
function rotateFloor(){
 $('orbitFloor').style.transform=`translate(-50%,-50%) rotateX(${rotX}deg) rotateZ(${rotZ}deg) scale(${zoom})`;
}
function renderInsights(){
 const list=$('insights');list.replaceChildren();const notes=report?.insights||[];
 if(!notes.length){const e=document.createElement('div');e.className='empty';e.textContent=report?.sections?.some(s=>s.state==='observing')?'No sustained, evidence-supported redistribution suggestions at present.':'Start linked camera feeds and gather consecutive observations for grounded insights.';list.append(e)}
 for(const insight of notes){const node=document.createElement('div');node.className='insight'+(insight.severity==='review'?' attention':'');
   const kind=document.createElement('small');kind.textContent=insight.kind.replace(/_/g,' ').toUpperCase();
   const h=document.createElement('h3');h.textContent=insight.title;
   const action=document.createElement('p');action.textContent=insight.recommendation;
   const evidence=document.createElement('p');evidence.textContent=insight.evidence;
   const caveat=document.createElement('p');caveat.textContent=insight.caveat;caveat.style.fontSize='11px';
   node.append(kind,h,action,evidence,caveat);
   if(insight.section_id){const b=document.createElement('button');b.textContent='Inspect section';b.onclick=()=>{select(insight.section_id);$('editor').scrollIntoView({behavior:'smooth',block:'center'})};node.append(b)}
   list.append(node)}
 const graph=report?.topology;
 if(graph){const pathCount=graph.routes?.length||0,assumptions=[];
   if(graph.assumed_entrances)assumptions.push('bottom tiles as entry');if(graph.assumed_exits)assumptions.push('top tiles as end');
   $('topologyStatus').textContent=`Internal graph: ${Object.keys(graph.adjacency||{}).length} nodes, ${pathCount} entrance-to-back schematic route(s). Entrance: ${(graph.entrances||[]).length}; back: ${(graph.exits||[]).length}. `+(assumptions.length?'Assumptions: '+assumptions.join(', ')+'. ':'')+'No customer routes are inferred from these links.';
 }
}
function paintMetrics(){
 const sections=draft.sections;const body=$('overallRows');body.replaceChildren();
 for(const s of sections){const r=freshMetrics(s);const tr=document.createElement('tr');
   for(const value of [s.name,s.role,r?.count??'—',r?.p90_5m??'—',r?.partial_dwell_s!=null?r.partial_dwell_s+' s':'—',r?.observed_tracks??'—',
     `${r?.active_feeds||0} / ${s.links?.length||0}`,r?.state==='observing'?'Observed':'No live evidence']){
     const td=document.createElement('td');td.textContent=value;tr.append(td)}
   tr.style.cursor='pointer';tr.onclick=()=>{select(s.id);$('editor').scrollIntoView({behavior:'smooth'})};body.append(tr)}
 if(!sections.length){const tr=document.createElement('tr');const td=document.createElement('td');td.colSpan=8;td.textContent='No layout sections yet. Add boxes above.';tr.append(td);body.append(tr)}
 const active=sections.map(s=>freshMetrics(s)).filter(r=>r?.count!=null);
 $('totalSections').textContent=String(sections.length);$('observedSections').textContent=String(active.length);
 $('activeFeeds').textContent=String(report?.overall?.cameras_live||0);
 $('observedTotal').textContent=active.length?String(active.reduce((sum,s)=>sum+s.count,0)):'—';
 for(const tile of $('editor').children){const s=sections.find(x=>x.id===tile.dataset.id);if(s){const em=tile.querySelector('em'),m=freshMetrics(s);if(em)em.textContent=m?.count!=null?`${m.count} observed`:'No live data'}}
}
async function refresh(){if(refreshing)return;refreshing=true;try{
   const fresh=await request('/api/layout/analytics');report=fresh;paintMetrics();render3d();renderInsights();
 }catch(e){inform('Metrics refresh: '+e.message,true)}finally{refreshing=false}}
async function initialize(){try{
 [config,saved]=await Promise.all([request('/api/config'),request('/api/layout')]);draft=clone(saved);
 const allowed=new Set(config.cameras.flatMap(c=>(c.zones||[]).map(z=>c.id+'::'+z.id)));
 let removed=0;
 for(const s of draft.sections){const before=(s.links||[]).length;s.links=(s.links||[]).filter(l=>allowed.has(l.camera_id+'::'+l.zone_id));removed+=before-s.links.length}
 selected=draft.sections[0]?.id||null;
 $('feedsNote').textContent=`${config.cameras.length} configured sources · at most four simultaneous CPU inference sessions in the prototype. Additional cameras may be registered and linked to sections without activating them all.`;
 if(removed){markDirty();inform(`${removed} old camera-zone mapping(s) are no longer configured. Removed from the unsaved draft; review and save the repaired layout.`,true)}else markClean();
 renderEditor();updateProperties();render3d();await refresh();setInterval(refresh,2800);
 }catch(e){inform('Could not initialize layout: '+e.message,true)}}

$('addSection').onclick=addSection;$('starter').onclick=exampleLayout;
$('applyProperties').onclick=updateSection;$('deleteSection').onclick=removeSection;
$('saveLayout').onclick=save;$('resetLayout').onclick=discard;$('refresh').onclick=refresh;
$('resetOrbit').onclick=()=>{rotX=57;rotZ=-25;zoom=1;rotateFloor()};
let orbit=null;
$('orbitStage').addEventListener('pointerdown',event=>{if(event.button!==0)return;orbit={x:event.clientX,y:event.clientY,ax:rotX,az:rotZ};$('orbitStage').setPointerCapture(event.pointerId)});
$('orbitStage').addEventListener('pointermove',event=>{if(!orbit)return;rotZ=orbit.az+(event.clientX-orbit.x)*.35;rotX=clamp(orbit.ax+(event.clientY-orbit.y)*.23,10,82);rotateFloor()});
$('orbitStage').addEventListener('pointerup',()=>orbit=null);
$('orbitStage').addEventListener('pointercancel',()=>orbit=null);
$('orbitStage').addEventListener('wheel',event=>{event.preventDefault();zoom=clamp(zoom+(event.deltaY>0?-.08:.08),.5,1.6);rotateFloor()},{passive:false});
window.addEventListener('beforeunload',event=>{if(pending){event.preventDefault();event.returnValue=''}});
initialize();
