'use strict';
const $=id=>document.getElementById(id);
const money=n=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(n);
const number=n=>new Intl.NumberFormat('en-US',{maximumFractionDigits:5}).format(n);
const stamp=ts=>ts?new Date(ts*1000).toLocaleString('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZone:'America/New_York'})+' ET':'—';
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let data=null,range=0,chartMetric='equity';
function sign(n){return n>=0?'positive':'negative'}
function setMetric(id,value,n){$(id).textContent=value;$(id).classList.remove('positive','negative');if(n!==undefined)$(id).classList.add(sign(n));}
function riskBadge(r){if(!r||r.score===null||r.score===undefined)return '<span class="muted">Insufficient data</span>';return `<span class="risk-pill risk-${r.label.toLowerCase()}" title="${escape(r.method)}">${escape(r.label)} · ${r.score}/100${r.stale?' · last data':''}</span>`;}
function render(d){
 data=d;
 $('status').textContent=d.status==='running'&&d.start_not_before>Date.now()/1000?'Experiment scheduled':d.status==='running'?'Experiment active':d.status==='paused'?'Experiment paused':'Experiment ended';
 setMetric('equity',money(d.equity));setMetric('pnl',(d.pnl>=0?'+':'')+money(d.pnl),d.pnl);setMetric('cash',money(d.cash));setMetric('trade-count',number(d.trade_count));
 $('equity-foot').textContent='Marked '+stamp(d.as_of);$('pnl-foot').textContent=(d.pnl>=0?'+':'')+(d.pnl/1000).toFixed(2)+'% since inception';$('cash-foot').textContent=(d.equity?d.cash/d.equity*100:0).toFixed(1)+'% of portfolio';$('trades-foot').textContent=number(d.holdings.length)+' open positions';
 $('phase').textContent=d.phase;$('model').textContent=d.model==='pending'?'Awaiting first deliberation':d.model;$('last-cycle').textContent=stamp(d.last_cycle);
 const thought=d.notes.find(n=>n.kind==='decision'||n.kind==='reflection'||n.kind==='plan');$('latest-thought').textContent=thought?thought.body:'The agent’s first deliberation will appear here. No synthetic trades or notes are displayed.';
 const ai=d.usage.find(u=>u.provider==='ai');const reserved=ai?.reserved||0;const budget=d.ai_budget||.55;$('budget-label').textContent='$'+reserved.toFixed(3)+' / $'+budget.toFixed(2);$('budget-fill').style.width=Math.min(100,reserved/budget*100)+'%';
 $('key-budgets').innerHTML=(d.ai_key_budgets||[]).map(key=>`<p>${escape(key.label)}: $${key.reserved.toFixed(3)} / $0.55 · $0.05 buffer${key.cooldown_until>Date.now()/1000?' · retry '+escape(stamp(key.cooldown_until)):''}</p>`).join('');
 $('budget-buffer').textContent='$0.05 kept outside each key’s $0.60 allowance. '+(d.ai_key_budgets?.length||1)+' key(s) configured.';
 $('stream-coverage').textContent='IEX · '+(d.stream_count||0)+' streamed · 120 watched';$('stream-coverage').title=d.stream_status||'';
 $('position-count').textContent=d.holdings.length;
 $('strategy-name').textContent=d.strategy||'AI-selected';$('strategy-horizon').textContent=d.strategy_horizon||'Undecided';$('strategy-why').textContent=d.strategy_why||'';
 const limits=d.provider_limits?.ai||{};
 $('request-reset').textContent='Request limit resets: '+(limits.requests_reset_at?stamp(limits.requests_reset_at):'unknown — provider did not supply header');
 $('token-reset').textContent='Token limit resets: '+(limits.tokens_reset_at?stamp(limits.tokens_reset_at):'unknown — provider did not supply header');
 $('credit-reset').textContent=limits.credit_retry_at?'Credit retry: '+stamp(limits.credit_retry_at)+' ('+limits.credit_retry_source+')':'Dollar-credit reset: unknown — provider did not report it';
 $('local-budget-reset').textContent='Local rolling budget: '+(d.ai_local_budget_available_at?'earliest reservation expires '+stamp(d.ai_local_budget_available_at):'full allowance available')+'. This is separate from provider credits.';
 const memory=d.price_memory;$('price-memory').textContent=memory?'Price memory: '+number(memory.samples)+' snapshots · '+memory.symbols+' tickers · every 5m · 90-day default retention. Latest '+stamp(memory.last)+(d.storage_warning?' · '+d.storage_warning:'')+(memory.error?' · collection deferred: '+memory.error:''):'Price memory: awaiting backend update';
 const plan=d.plan;
 $('session-plan').innerHTML=plan?`<h3>${escape(plan.summary)}</h3><p>${escape(plan.why)}</p><ol>${(plan.steps||[]).map(step=>`<li>${escape(step)}</li>`).join('')}</ol><div class="plan-watchlist">${(plan.watchlist||[]).map(item=>`<article><strong>${escape(item.symbol)}</strong><p><b>Watch:</b> ${escape(item.condition)}</p><p><b>Why:</b> ${escape(item.why)}</p><p><b>Invalidation:</b> ${escape(item.invalidation)}</p></article>`).join('')}</div><p class="muted">Prepared ${escape(stamp(plan.created_at))}. Every entry requires a new decision with fresh prices during market hours.</p>`:'<p class="muted">The AI will publish its plan and reasoning at its next planning cycle.</p>';
 $('risk-body').innerHTML=d.holdings.map(p=>[p.symbol,p.risk||d.stock_risks?.[p.symbol]||{}]).map(([symbol,r])=>`<tr><td class="symbol-name">${escape(symbol)}</td><td>${riskBadge(r)}</td><td>${r.daily_volatility_proxy_pct===undefined?'—':number(r.daily_volatility_proxy_pct)+'%'}</td><td>${r.observed_drawdown_pct===undefined?'—':number(r.observed_drawdown_pct)+'%'}</td><td>${r.spread_pct===undefined?'—':number(r.spread_pct)+'%'}</td><td>${r.samples}</td></tr>`).join('')||'<tr><td colspan="6" class="empty">No open holdings. Stock risk appears when the bot buys shares.</td></tr>';
 $('holdings-body').innerHTML=d.holdings.length?d.holdings.map(p=>`<tr><td><div class="symbol-cell"><span class="ticker-avatar">${escape(p.symbol.slice(0,1))}</span><div><div class="symbol-name">${escape(p.symbol)}</div><div class="quote-age">${p.holding_plan?escape(p.holding_plan.horizon)+' · ':''}${p.quote_ts&&Date.now()/1000-p.quote_ts<90?'Fresh IEX quote':'Last recorded mark'}</div></div></div></td><td>${number(p.qty)}</td><td>${money(p.cost/p.qty)}</td><td>${money(p.mark)}</td><td>${money(p.value)}</td><td class="${sign(p.unrealized)}">${p.unrealized>=0?'+':''}${money(p.unrealized)}</td><td><div class="weight">${(p.value/d.equity*100).toFixed(1)}%<span class="weight-track"><i data-weight="${Math.min(100,p.value/d.equity*100)}"></i></span></div></td><td>${riskBadge(p.risk)}</td></tr>`).join(''):'<tr><td colspan="8" class="empty">No open positions yet. The agent will build its portfolio during market hours.</td></tr>';
 document.querySelectorAll('[data-weight]').forEach(el=>el.style.width=el.dataset.weight+'%');
 $('trades-body').innerHTML=d.trades.length?d.trades.map(t=>`<tr title="${escape(t.reason)}"><td>${escape(stamp(t.ts))}</td><td><span class="side-pill ${t.side==='sell'?'sell':''}">${escape(t.side.toUpperCase())}</span></td><td class="symbol-name">${escape(t.symbol)}</td><td>${number(t.qty)}</td><td>${money(t.price)}</td><td>${money(t.amount)}</td><td class="${t.side==='sell'?sign(t.realized):'muted'}">${t.side==='sell'?money(t.realized):'—'}</td></tr>`).join(''):'<tr><td colspan="7" class="empty">The ledger is empty. Trades appear here after independent execution.</td></tr>';
 $('notes').innerHTML=d.notes.length?d.notes.map(n=>`<article class="note-card"><div class="note-meta"><span class="note-kind">${escape(n.kind)}</span><span>${escape(stamp(n.ts))}</span></div><h3>${escape(n.title)}</h3><p>${escape(n.body)}</p></article>`).join(''):'<div class="empty">Research and reflections appear after the first decision cycle.</div>';
 $('notice').hidden=!d.last_error;$('notice').textContent='The latest cycle was deferred: '+d.last_error;
 if(d.phase==='Awaiting server credentials'){$('notice').hidden=false;$('notice').textContent='The frontend is ready. The Nest backend needs its private credentials before the experiment can begin.';}
 chart();
}
function chart(){
 if(!data)return;
 let points=data.curve.filter(p=>Number.isFinite(p.ts)&&Number.isFinite(p.equity)&&(!range||p.ts>=Date.now()/1000-range*86400)).sort((a,b)=>a.ts-b.ts).map(p=>({...p,equity:chartMetric==='cash'?p.cash:chartMetric==='pnl'?p.equity-data.initial:p.equity}));
 const reference=chartMetric==='equity'?data.initial:0;
 $('chart-legend').textContent=chartMetric==='cash'?'Cash balance':chartMetric==='pnl'?'Gain / loss':'Portfolio value';
 if(!points.length){$('chart').innerHTML='<div class="empty">No portfolio snapshots in this time range.</div>';$('curve-start').textContent='—';$('curve-end').textContent='—';return;}
 const w=780,h=240,left=6,right=72,top=16,bottom=22;
 const vals=points.map(p=>p.equity);let low=Math.min(...vals,reference),high=Math.max(...vals,reference);let pad=Math.max((high-low)*.2,100);low-=pad;high+=pad;
 const x=i=>left+(w-left-right)*(points.length===1||points.at(-1).ts===points[0].ts?0.5:(points[i].ts-points[0].ts)/(points.at(-1).ts-points[0].ts));const y=v=>top+(h-top-bottom)*(high-v)/(high-low);
 const path=points.map((p,i)=>(i?'L':'M')+x(i).toFixed(1)+','+y(p.equity).toFixed(1)).join(' ');
 const grid=[0,1,2,3].map(i=>{let v=high-(high-low)*i/3,yy=y(v);return `<line x1="${left}" y1="${yy}" x2="${w-right}" y2="${yy}" stroke="#25313b" stroke-dasharray="3 5"/><text x="${w-right+10}" y="${yy+4}">$${number(Math.round(v))}</text>`}).join('');
 const baseline=y(reference);const last=points.length-1;
 $('chart').innerHTML=`<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" tabindex="0" role="img" aria-label="Portfolio value over time. Latest value ${escape(money(points[last].equity))}"><defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#b4ed82" stop-opacity=".15"/><stop offset="100%" stop-color="#b4ed82" stop-opacity="0"/></linearGradient></defs>${grid}<line x1="${left}" x2="${w-right}" y1="${baseline}" y2="${baseline}" stroke="#657560" stroke-dasharray="5 5"/><path d="${path} L${x(last)},${h-bottom} L${x(0)},${h-bottom} Z" fill="url(#area)"/><path d="${path}" fill="none" stroke="#b4ed82" stroke-width="2.5"/><circle cx="${x(last)}" cy="${y(points[last].equity)}" r="4" fill="#b4ed82"/><g id="chart-cursor" hidden><line id="chart-crosshair" y1="${top}" y2="${h-bottom}" stroke="#81958c" stroke-dasharray="4 4"/><circle id="chart-dot" r="5" fill="#b4ed82"/></g></svg><div id="chart-tooltip" class="chart-tooltip" hidden></div>`;
 const svg=$('chart').querySelector('svg');let selected=last;
 function inspect(i){selected=Math.max(0,Math.min(last,i));const point=points[selected],xx=x(selected),yy=y(point.equity);$('chart-cursor').removeAttribute('hidden');$('chart-crosshair').setAttribute('x1',xx);$('chart-crosshair').setAttribute('x2',xx);$('chart-dot').setAttribute('cx',xx);$('chart-dot').setAttribute('cy',yy);const tip=$('chart-tooltip');tip.hidden=false;tip.textContent=stamp(point.ts)+' · '+money(point.equity);tip.style.left=Math.min(70,Math.max(0,xx/w*100))+'%';}
 svg.addEventListener('pointermove',e=>{const rect=svg.getBoundingClientRect(),xx=(e.clientX-rect.left)/rect.width*w;let best=0;for(let i=1;i<points.length;i++)if(Math.abs(x(i)-xx)<Math.abs(x(best)-xx))best=i;inspect(best);});
 svg.addEventListener('pointerleave',()=>{$('chart-cursor').setAttribute('hidden','');$('chart-tooltip').hidden=true;});
 svg.addEventListener('focus',()=>inspect(selected));svg.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();inspect(selected+(e.key==='ArrowLeft'?-1:1));}});
 $('curve-start').textContent=new Date(points[0].ts*1000).toLocaleDateString('en-US',{month:'short',day:'numeric'});$('curve-end').textContent=new Date(points[last].ts*1000).toLocaleDateString('en-US',{month:'short',day:'numeric'});
}
async function refresh(){
 try{const r=await fetch('/api/public');if(!r.ok)throw new Error();const d=await r.json();if(!d.simulation)throw new Error();render(d);}
 catch{$('status').textContent='Backend unavailable';$('notice').hidden=false;$('notice').textContent='The experiment backend is not reachable. '+(data?'Showing the last received ledger; values are not live.':'No portfolio data is available yet.');}
}
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('[data-tab]').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.tab-content').forEach(x=>x.hidden=x.id!==b.dataset.tab);}));
document.querySelectorAll('[data-range]').forEach(b=>b.addEventListener('click',()=>{range=Number(b.dataset.range);document.querySelectorAll('[data-range]').forEach(x=>x.classList.toggle('active',x===b));chart();}));
$('chart-metric').addEventListener('change',e=>{chartMetric=e.target.value;chart();});
refresh();setInterval(()=>{if(!document.hidden)refresh()},60000);
