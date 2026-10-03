'use strict';
const $=id=>document.getElementById(id);
const money=n=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(n);
const number=n=>new Intl.NumberFormat('en-US',{maximumFractionDigits:5}).format(n);
const stamp=ts=>ts?new Date(ts*1000).toLocaleString('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZone:'America/New_York'})+' ET':'—';
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let data=null,range=0;
function sign(n){return n>=0?'positive':'negative'}
function setMetric(id,value,n){$(id).textContent=value;$(id).classList.remove('positive','negative');if(n!==undefined)$(id).classList.add(sign(n));}
function render(d){
 data=d;
 $('status').textContent=d.status==='running'?'Experiment active':d.status==='paused'?'Experiment paused':'Experiment ended';
 setMetric('equity',money(d.equity));setMetric('pnl',(d.pnl>=0?'+':'')+money(d.pnl),d.pnl);setMetric('cash',money(d.cash));setMetric('trade-count',number(d.trade_count));
 $('equity-foot').textContent='Marked '+stamp(d.as_of);$('pnl-foot').textContent=(d.pnl>=0?'+':'')+(d.pnl/1000).toFixed(2)+'% since inception';$('cash-foot').textContent=(d.equity?d.cash/d.equity*100:0).toFixed(1)+'% of portfolio';$('trades-foot').textContent=number(d.holdings.length)+' open positions';
 $('phase').textContent=d.phase;$('model').textContent=d.model==='pending'?'Awaiting first deliberation':d.model;$('last-cycle').textContent=stamp(d.last_cycle);
 const thought=d.notes.find(n=>n.kind==='decision'||n.kind==='reflection');$('latest-thought').textContent=thought?thought.body:'The agent’s first deliberation will appear here. No synthetic trades or notes are displayed.';
 const ai=d.usage.find(u=>u.provider==='ai');const reserved=ai?.reserved||0;$('budget-label').textContent='$'+reserved.toFixed(3)+' / $0.45';$('budget-fill').style.width=Math.min(100,reserved/.45*100)+'%';
 $('position-count').textContent=d.holdings.length;
 $('holdings-body').innerHTML=d.holdings.length?d.holdings.map(p=>`<tr><td><div class="symbol-cell"><span class="ticker-avatar">${escape(p.symbol.slice(0,1))}</span><div><div class="symbol-name">${escape(p.symbol)}</div><div class="quote-age">${p.quote_ts&&Date.now()/1000-p.quote_ts<90?'Fresh IEX quote':'Last recorded mark'}</div></div></div></td><td>${number(p.qty)}</td><td>${money(p.cost/p.qty)}</td><td>${money(p.mark)}</td><td>${money(p.value)}</td><td class="${sign(p.unrealized)}">${p.unrealized>=0?'+':''}${money(p.unrealized)}</td><td><div class="weight">${(p.value/d.equity*100).toFixed(1)}%<span class="weight-track"><i data-weight="${Math.min(100,p.value/d.equity*100)}"></i></span></div></td></tr>`).join(''):'<tr><td colspan="7" class="empty">No open positions yet. The agent will build its portfolio during market hours.</td></tr>';
 document.querySelectorAll('[data-weight]').forEach(el=>el.style.width=el.dataset.weight+'%');
 $('trades-body').innerHTML=d.trades.length?d.trades.map(t=>`<tr title="${escape(t.reason)}"><td>${escape(stamp(t.ts))}</td><td><span class="side-pill ${t.side==='sell'?'sell':''}">${escape(t.side.toUpperCase())}</span></td><td class="symbol-name">${escape(t.symbol)}</td><td>${number(t.qty)}</td><td>${money(t.price)}</td><td>${money(t.amount)}</td><td class="${t.side==='sell'?sign(t.realized):'muted'}">${t.side==='sell'?money(t.realized):'—'}</td></tr>`).join(''):'<tr><td colspan="7" class="empty">The ledger is empty. Trades appear here after independent execution.</td></tr>';
 $('notes').innerHTML=d.notes.length?d.notes.map(n=>`<article class="note-card"><div class="note-meta"><span class="note-kind">${escape(n.kind)}</span><span>${escape(stamp(n.ts))}</span></div><h3>${escape(n.title)}</h3><p>${escape(n.body)}</p></article>`).join(''):'<div class="empty">Research and reflections appear after the first decision cycle.</div>';
 $('notice').hidden=!d.last_error;$('notice').textContent='The agent deferred its latest cycle because a provider or budget guard was triggered. No trade was fabricated. '+d.last_error;
 if(d.phase==='Awaiting server credentials'){$('notice').hidden=false;$('notice').textContent='The frontend is ready. The Nest backend needs its private credentials before the experiment can begin.';}
 chart();
}
function chart(){
 if(!data)return;
 let points=data.curve.filter(p=>!range||p.ts>=Date.now()/1000-range*86400);
 if(!points.length){$('chart').innerHTML='<div class="empty">No portfolio snapshots in this time range.</div>';return;}
 const w=780,h=240,left=6,right=72,top=16,bottom=22;
 const vals=points.map(p=>p.equity);let low=Math.min(...vals,100000),high=Math.max(...vals,100000);let pad=Math.max((high-low)*.2,100);low-=pad;high+=pad;
 const x=i=>left+(w-left-right)*(points.length===1?0.5:i/(points.length-1));const y=v=>top+(h-top-bottom)*(high-v)/(high-low);
 const path=points.map((p,i)=>(i?'L':'M')+x(i).toFixed(1)+','+y(p.equity).toFixed(1)).join(' ');
 const grid=[0,1,2,3].map(i=>{let v=high-(high-low)*i/3,yy=y(v);return `<line x1="${left}" y1="${yy}" x2="${w-right}" y2="${yy}" stroke="#25313b" stroke-dasharray="3 5"/><text x="${w-right+10}" y="${yy+4}">$${number(Math.round(v))}</text>`}).join('');
 const baseline=y(100000);const last=points.length-1;
 $('chart').innerHTML=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Portfolio value over time. Latest value ${escape(money(points[last].equity))}"><defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#b4ed82" stop-opacity=".15"/><stop offset="100%" stop-color="#b4ed82" stop-opacity="0"/></linearGradient></defs>${grid}<line x1="${left}" x2="${w-right}" y1="${baseline}" y2="${baseline}" stroke="#657560" stroke-dasharray="5 5"/><path d="${path} L${x(last)},${h-bottom} L${x(0)},${h-bottom} Z" fill="url(#area)"/><path d="${path}" fill="none" stroke="#b4ed82" stroke-width="2.5"/><circle cx="${x(last)}" cy="${y(points[last].equity)}" r="4" fill="#b4ed82"/></svg>`;
 $('curve-start').textContent=new Date(points[0].ts*1000).toLocaleDateString('en-US',{month:'short',day:'numeric'});$('curve-end').textContent=new Date(points[last].ts*1000).toLocaleDateString('en-US',{month:'short',day:'numeric'});
}
async function refresh(){
 try{const r=await fetch('/api/public');if(!r.ok)throw new Error();const d=await r.json();if(!d.simulation)throw new Error();render(d);}
 catch{$('status').textContent='Backend unavailable';$('notice').hidden=false;$('notice').textContent='The experiment backend is not reachable. '+(data?'Showing the last received ledger; values are not live.':'No portfolio data is available yet.');}
}
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('[data-tab]').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.tab-content').forEach(x=>x.hidden=x.id!==b.dataset.tab);}));
document.querySelectorAll('[data-range]').forEach(b=>b.addEventListener('click',()=>{range=Number(b.dataset.range);document.querySelectorAll('[data-range]').forEach(x=>x.classList.toggle('active',x===b));chart();}));
refresh();setInterval(()=>{if(!document.hidden)refresh()},60000);
