'use strict';
const $=id=>document.getElementById(id);
async function api(path,body){const r=await fetch('/api/admin/'+path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,credentials:'same-origin'});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Request failed');return d;}
function state(s){$('login').hidden=true;$('controls').hidden=false;$('state').textContent=s;$('pause').hidden=s!=='running';$('resume').hidden=s!=='paused';$('stop').hidden=s==='stopped';}
function message(m,error=false){$('message').textContent=m;$('message').classList.toggle('error',error);}
$('login').addEventListener('submit',async e=>{e.preventDefault();try{await api('login',{passcode:$('passcode').value});$('passcode').value='';const d=await api('status');state(d.status);message('Authenticated. Only lifecycle controls are available.');}catch(e){message(e.message,true);}});
for(const action of ['pause','resume','stop'])$(action).addEventListener('click',async()=>{if(action==='stop'&&!confirm('End this experiment permanently? The ledger remains, and no sell orders are issued.'))return;try{const d=await api('control',{action});state(d.status);message('Experiment '+d.status+'.');}catch(e){message(e.message,true);}});
$('logout').addEventListener('click',async()=>{try{await api('logout',{});$('login').hidden=false;$('controls').hidden=true;message('Signed out.');}catch(e){message(e.message,true);}});
api('status').then(d=>state(d.status)).catch(()=>{});
