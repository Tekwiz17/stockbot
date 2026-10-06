"""SQLite ledger: one writer, integer microdollars and microshares, atomic fills."""
import json, sqlite3, time
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from pathlib import Path

SCALE = 1_000_000
INITIAL = 100_000 * SCALE

def units(value):
    d = Decimal(str(value))
    if not d.is_finite():
        raise ValueError('Nonfinite amount')
    return int((d * SCALE).to_integral_value(rounding=ROUND_DOWN))

def now(): return time.time()

class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS positions(symbol TEXT PRIMARY KEY,qty INTEGER NOT NULL CHECK(qty>=0),cost INTEGER NOT NULL CHECK(cost>=0));
        CREATE TABLE IF NOT EXISTS prices(id INTEGER PRIMARY KEY,ts REAL,symbol TEXT,bid INTEGER,ask INTEGER,source TEXT);
        CREATE INDEX IF NOT EXISTS prices_symbol_ts ON prices(symbol,ts);
        CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY,ts REAL,symbol TEXT,side TEXT,qty INTEGER,price INTEGER,amount INTEGER,realized INTEGER,reason TEXT,decision TEXT,UNIQUE(decision,symbol,side));
        CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY,ts REAL,kind TEXT,title TEXT,body TEXT);
        CREATE TABLE IF NOT EXISTS equity(id INTEGER PRIMARY KEY,ts REAL,equity INTEGER,cash INTEGER);
        CREATE TABLE IF NOT EXISTS requests(id INTEGER PRIMARY KEY,ts REAL,provider TEXT,cost REAL,status TEXT);
        CREATE TABLE IF NOT EXISTS research(id INTEGER PRIMARY KEY,ts REAL,query TEXT,results TEXT);
        CREATE TABLE IF NOT EXISTS price_history(symbol TEXT,bucket INTEGER,quote_ts REAL,bid INTEGER,ask INTEGER,PRIMARY KEY(symbol,bucket));
        CREATE TABLE IF NOT EXISTS position_plans(symbol TEXT PRIMARY KEY,created_at REAL,horizon TEXT,review_after REAL,thesis TEXT,invalidation TEXT);
        CREATE TABLE IF NOT EXISTS cycle_errors(ts REAL,stage TEXT,kind TEXT,detail TEXT);
        CREATE TABLE IF NOT EXISTS bars(symbol TEXT,ts REAL,open REAL,high REAL,low REAL,close REAL,volume REAL,PRIMARY KEY(symbol,ts));
        CREATE TABLE IF NOT EXISTS decisions(id TEXT PRIMARY KEY,ts REAL,kind TEXT,payload TEXT);
        CREATE TABLE IF NOT EXISTS auth_attempts(ts REAL,ip TEXT);
        ''')
        for k,v in {'cash':INITIAL,'status':'running','model':'pending','phase':'Connecting','last_cycle':0,'last_error':'','last_stream':0,'collection_error':'','last_reflection':'','strategy':'AI choosing strategy','strategy_why':'Awaiting the next autonomous decision','strategy_horizon':'Undecided','plan':None,'plan_version':0,'last_plan':'','cooldown_ai':0,'cooldown_search':0,'cooldown_alpaca':0}.items():
            self.db.execute('INSERT OR IGNORE INTO state VALUES (?,?)',(k,json.dumps(v)))
        if not self.db.execute("SELECT 1 FROM state WHERE key='history_migrated'").fetchone():
            # Preserve genuine existing observations, choosing the final quote of each five-minute bucket.
            self.db.execute('''INSERT OR IGNORE INTO price_history SELECT symbol,CAST(ts/300 AS INTEGER)*300,ts,bid,ask FROM (SELECT symbol,ts,bid,ask,ROW_NUMBER() OVER (PARTITION BY symbol,CAST(ts/300 AS INTEGER) ORDER BY ts DESC,id DESC) rank FROM prices WHERE ts>?) WHERE rank=1''',(now()-183*86400,))
            self.set('history_migrated',True)
        if not self.db.execute('SELECT 1 FROM equity LIMIT 1').fetchone():
            self.db.execute('INSERT INTO equity(ts,equity,cash) VALUES (?,?,?)',(now(),INITIAL,INITIAL))
    def get(self,k): return json.loads(self.db.execute('SELECT value FROM state WHERE key=?',(k,)).fetchone()[0])
    def set(self,k,v): self.db.execute('INSERT OR REPLACE INTO state VALUES (?,?)',(k,json.dumps(v)))
    def rows(self,q,args=()): return [dict(x) for x in self.db.execute(q,args)]
    def note(self,kind,title,body): self.db.execute('INSERT INTO notes(ts,kind,title,body) VALUES (?,?,?,?)',(now(),kind,str(title)[:160],str(body)[:4000]))
    def reserve(self,provider,cost=0,limit=0.55,cap=48,window=86400):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            r=self.db.execute('SELECT COUNT(*),COALESCE(SUM(cost),0) FROM requests WHERE provider=? AND ts>?',(provider,now()-window)).fetchone()
            if r[0]>=cap or r[1]+cost>limit: self.db.execute('ROLLBACK');return None
            c=self.db.execute('INSERT INTO requests(ts,provider,cost,status) VALUES (?,?,?,?)',(now(),provider,cost,'reserved'))
            self.db.execute('COMMIT');return c.lastrowid
        except BaseException: self.db.execute('ROLLBACK');raise
    def complete(self,rid,status): self.db.execute('UPDATE requests SET status=? WHERE id=?',(status,rid))
    def quote(self,symbol,bid,ask,ts,source='IEX'):
        b,a=units(bid),units(ask)
        if not (0<b<=a) or a>b*1.02 or ts>now()+5: return
        self.db.execute('INSERT INTO prices(ts,symbol,bid,ask,source) VALUES (?,?,?,?,?)',(ts,symbol,b,a,source))
    def bar(self,symbol,open_,high,low,close,volume,ts):
        import math
        values=(open_,high,low,close,volume,ts)
        if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in values):return
        if min(open_,high,low,close)<=0 or volume<0 or low>min(open_,close) or high<max(open_,close) or ts>now()+5:return
        self.db.execute('INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?,?)',(symbol,ts,open_,high,low,close,volume))
    def latest(self,symbol):
        r=self.db.execute('SELECT * FROM prices WHERE symbol=? ORDER BY ts DESC LIMIT 1',(symbol,)).fetchone()
        return dict(r) if r else None
    def account(self):
        cash=self.get('cash'); holdings=[];total=cash
        for p in self.rows('SELECT * FROM positions WHERE qty>0'):
            q=self.latest(p['symbol']);mark=(q['bid']+q['ask'])//2 if q else p['cost']*SCALE//p['qty']
            val=p['qty']*mark//SCALE;total+=val
            holdings.append({**p,'mark':mark,'value':val,'unrealized':val-p['cost'],'quote_ts':q['ts'] if q else None})
        return {'cash':cash,'equity':total,'holdings':holdings}
    def fill(self,decision,symbol,side,quantity,reason,market_open):
        if side not in ('buy','sell'):raise ValueError('Invalid side')
        qty=units(quantity)
        if qty<=0:raise ValueError('Quantity must be positive')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if self.get('status')!='running' or not market_open:raise ValueError('Trading is closed or suspended')
            q=self.latest(symbol)
            if not q or now()-q['ts']>90:raise ValueError('No fresh quote')
            # Buy at ask + 5 bps, sell at bid - 5 bps; this is a simulation, not a brokerage fill.
            price=int((Decimal(q['ask'] if side=='buy' else q['bid'])*Decimal('1.0005' if side=='buy' else '0.9995')).to_integral_value(rounding=ROUND_HALF_UP))
            amount=(qty*price+SCALE-1)//SCALE if side=='buy' else qty*price//SCALE
            if amount<10*SCALE:raise ValueError('Minimum simulated trade is $10')
            p=self.db.execute('SELECT qty,cost FROM positions WHERE symbol=?',(symbol,)).fetchone();held,cost=(p[0],p[1]) if p else (0,0)
            cash=self.get('cash');realized=0
            if side=='buy':
                if amount>cash:raise ValueError('Insufficient cash')
                acc=self.account()
                if held*price//SCALE+amount>acc['equity']*0.30:raise ValueError('30% single position cap')
                held+=qty;cost+=amount;cash-=amount
            else:
                if qty>held:raise ValueError('Cannot sell unowned shares')
                removed=cost if qty==held else cost*qty//held
                held-=qty;cost-=removed;cash+=amount;realized=amount-removed
            self.set('cash',cash)
            self.db.execute('INSERT OR REPLACE INTO positions VALUES (?,?,?)',(symbol,held,cost))
            self.db.execute('INSERT INTO trades(ts,symbol,side,qty,price,amount,realized,reason,decision) VALUES (?,?,?,?,?,?,?,?,?)',(now(),symbol,side,qty,price,amount,realized,str(reason)[:1000],decision))
            self.db.execute('COMMIT')
        except BaseException:self.db.execute('ROLLBACK');raise
    def snapshot(self):
        a=self.account();self.db.execute('INSERT INTO equity(ts,equity,cash) VALUES (?,?,?)',(now(),a['equity'],a['cash']))
    def prune(self):
        self.db.execute('DELETE FROM bars WHERE ts<?',(now()-14*86400,))
        self.db.execute('DELETE FROM cycle_errors WHERE ts<?',(now()-30*86400,))
        # Retain 14 days of minute quote records; trades and decision notes are permanent.
        self.db.execute('DELETE FROM prices WHERE ts<? AND id NOT IN (SELECT id FROM prices WHERE (symbol,ts) IN (SELECT symbol,MAX(ts) FROM prices GROUP BY symbol))',(now()-14*86400,))
        self.db.execute('DELETE FROM auth_attempts WHERE ts<?',(now()-86400,))
    def risk(self,symbol,weight=0):
        from .risk import calculate
        raw=self.rows('SELECT ts,bid,ask FROM prices WHERE symbol=? ORDER BY ts DESC LIMIT 1560',(symbol,))
        buckets={}
        for row in raw:buckets.setdefault(int(row['ts']//60),row)
        rows=list(buckets.values())[:390][::-1]
        return calculate(rows,self.latest(symbol),weight,now())
    def public(self):
        a=self.account()
        for p in a['holdings']:
            plan=self.db.execute('SELECT * FROM position_plans WHERE symbol=?',(p['symbol'],)).fetchone()
            p['holding_plan']=dict(plan) if plan else None
            p['risk']=self.risk(p['symbol'],p['value']/a['equity'] if a['equity'] else 0)
            for k in ('qty','cost','mark','value','unrealized'):p[k]/=SCALE
        for k in ('cash','equity'):a[k]/=SCALE
        trades=self.rows('SELECT * FROM trades ORDER BY id DESC LIMIT 200')
        for t in trades:
            for k in ('qty','price','amount','realized'):t[k]/=SCALE
        count=self.db.execute('SELECT COUNT(*) FROM equity').fetchone()[0]
        stride=max(1,(count+1999)//2000)
        eq=self.rows('SELECT ts,equity,cash FROM equity WHERE id % ?=0 OR id IN (SELECT MIN(id) FROM equity UNION SELECT MAX(id) FROM equity) OR ts>? ORDER BY ts',(stride,now()-86400))
        for e in eq:e['equity']/=SCALE;e['cash']/=SCALE
        stats=self.rows('SELECT provider,COUNT(*) calls,COALESCE(SUM(cost),0) reserved FROM requests WHERE ts>? GROUP BY provider',(now()-86400,))
        realized=self.db.execute('SELECT COALESCE(SUM(realized),0) FROM trades').fetchone()[0]/SCALE
        stock_risks={p['symbol']:p['risk'] for p in a['holdings']}
        archive_stats=self.db.execute('SELECT COUNT(*),MIN(bucket),MAX(bucket),COUNT(DISTINCT symbol) FROM price_history').fetchone()
        return {**a,'price_memory':{'samples':archive_stats[0],'first':archive_stats[1],'last':archive_stats[2],'symbols':archive_stats[3],'error':self.get('collection_error'),'retention_days':183,'interval_minutes':5},'stock_risks':stock_risks,'initial':100000,'pnl':a['equity']-100000,'realized':realized,'trades':trades,'trade_count':self.db.execute('SELECT COUNT(*) FROM trades').fetchone()[0], 'notes':self.rows('SELECT * FROM notes ORDER BY id DESC LIMIT 60'),'curve':eq,'usage':stats,'ai_budget':0.55,'status':self.get('status'),'phase':self.get('phase'),'model':self.get('model'),'strategy':self.get('strategy'),'strategy_why':self.get('strategy_why'),'strategy_horizon':self.get('strategy_horizon'),'plan':self.get('plan'),'provider_limits':{p:self.get('limits_'+p) if self.db.execute('SELECT 1 FROM state WHERE key=?',('limits_'+p,)).fetchone() else {} for p in ('ai','search','alpaca')},'ai_local_budget_available_at':self.db.execute("SELECT MIN(ts)+86400 FROM requests WHERE provider='ai' AND ts>?",(now()-86400,)).fetchone()[0],'last_cycle':self.get('last_cycle'),'last_stream':self.get('last_stream'),'last_error':self.get('last_error'),'as_of':now(),'simulation':True,'feed':'IEX · up to 30 symbols'}
