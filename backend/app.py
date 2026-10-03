import asyncio, base64, hashlib, hmac, json, os, secrets, time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse
from .store import Store
from .engine import Engine

store=Store(os.getenv('STOCKBOT_DB','data/stockbot.sqlite3'))
engine=Engine(store)
secret=os.getenv('SESSION_SECRET','')

def signed(exp):
    raw=str(exp);return raw+'.'+hmac.new(secret.encode(),raw.encode(),hashlib.sha256).hexdigest()

def authorized(req):
    if not secret:raise HTTPException(503,'Server authentication is not configured')
    value=req.cookies.get('stockbot_session','')
    try:
        raw,signature=value.split('.')
        if int(raw)<time.time() or not hmac.compare_digest(signed(raw),value):raise ValueError()
    except ValueError:raise HTTPException(401,'Sign in to the admin dashboard')

def same_origin(req):
    origin=req.headers.get('origin','')
    # Vercel rewrite preserves browser Origin; explicitly configure its public origin on Nest.
    allowed={x.rstrip('/') for x in os.getenv('PUBLIC_ORIGINS','').split(',') if x}
    allowed.add(str(req.base_url).rstrip('/'))
    if origin not in allowed:raise HTTPException(403,'Origin not allowed')

@asynccontextmanager
async def lifespan(app):
    if os.getenv('STOCKBOT_DISABLE_WORKER')=='1':tasks=[]
    else:tasks=[asyncio.create_task(engine.loop()),asyncio.create_task(engine.stream())]
    yield
    for t in tasks:t.cancel()
    await asyncio.gather(*tasks,return_exceptions=True)
    await engine.close()

app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)

@app.middleware('http')
async def security(req,call_next):
    response=await call_next(req)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    return response

@app.get('/api/health')
async def health():return {'ok':True,'worker_enabled':os.getenv('STOCKBOT_DISABLE_WORKER')!='1','configured':engine.configured(),'status':store.get('status')}

@app.get('/api/public')
async def public():
    # All visitors read the database. None can invoke a paid provider or a trading cycle.
    return JSONResponse(store.public(),headers={'Cache-Control':'public, max-age=15, s-maxage=30, stale-while-revalidate=60'})

@app.post('/api/admin/login')
async def login(req:Request):
    same_origin(req)
    if not secret or not os.getenv('ADMIN_PASSCODE'):raise HTTPException(503,'Authentication is not configured')
    ip=req.client.host if req.client else 'unknown'
    count=store.db.execute('SELECT COUNT(*) FROM auth_attempts WHERE ts>?',(time.time()-900,)).fetchone()[0]
    if count>=8:raise HTTPException(429,'Too many attempts. Try again in 15 minutes.')
    store.db.execute('INSERT INTO auth_attempts VALUES (?,?)',(time.time(),ip))
    if int(req.headers.get('content-length','0'))>1024:raise HTTPException(413,'Request too large')
    data=await req.json()
    if not hmac.compare_digest(str(data.get('passcode','')),os.environ['ADMIN_PASSCODE']):raise HTTPException(401,'Incorrect passcode')
    response=JSONResponse({'ok':True});response.set_cookie('stockbot_session',signed(int(time.time()+3600)),httponly=True,secure=os.getenv('ALLOW_HTTP')!='1',samesite='strict',max_age=3600,path='/')
    return response

@app.get('/api/admin/status')
async def admin_status(req:Request):authorized(req);return {'status':store.get('status')}

@app.post('/api/admin/control')
async def control(req:Request):
    authorized(req);same_origin(req);data=await req.json();action=data.get('action')
    # Deliberately no prompts, orders, run-now, holdings edits, strategy editor, or resume after stop.
    if action not in ('pause','resume','stop'):raise HTTPException(400,'Only pause, resume or stop is allowed')
    if store.get('status')=='stopped':raise HTTPException(409,'This experiment has ended')
    if action=='resume' and store.get('status')!='paused':raise HTTPException(409,'Only a paused experiment can resume')
    status={'pause':'paused','resume':'running','stop':'stopped'}[action]
    store.set('status',status);store.set('phase',status.capitalize());store.note('system','Experiment '+status,'Administrative lifecycle control. No trade instruction was supplied. Holdings remain recorded at their last available market prices.')
    return {'status':status}

@app.post('/api/admin/logout')
async def logout(req:Request):
    same_origin(req);response=JSONResponse({'ok':True});response.delete_cookie('stockbot_session');return response

ROOT=Path(__file__).resolve().parent.parent/'public'
@app.get('/')
async def index():return FileResponse(ROOT/'index.html')
@app.get('/admin')
async def admin():return FileResponse(ROOT/'admin.html')
@app.get('/{asset}')
async def asset(asset:str):
    if asset not in ('app.js','styles.css','admin.js','favicon.svg'):raise HTTPException(404)
    return FileResponse(ROOT/asset)
