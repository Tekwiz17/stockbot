import asyncio,json,os,time
from datetime import datetime,timezone
import pytest,httpx
from backend.store import Store,SCALE,now
from backend.engine import Engine,SYMBOLS

@pytest.fixture
def store(tmp_path):return Store(str(tmp_path/'ledger.db'))

def quote(s,symbol='NVDA',age=0):s.quote(symbol,100,100.05,now()-age)

def test_fractional_round_trip_and_realized_profit(store):
    quote(store);store.fill('a','NVDA','buy',12.345678,'Test thesis',True)
    after=store.get('cash');assert 0<after<100000*SCALE
    store.quote('NVDA',110,110.05,now());store.fill('b','NVDA','sell',12.345678,'Thesis fulfilled',True)
    assert store.get('cash')>100000*SCALE
    assert not store.account()['holdings']
    assert store.rows('SELECT * FROM trades')[-1]['realized']==store.get('cash')-100000*SCALE

def test_duplicate_decision_rolls_back_every_change(store):
    quote(store);store.fill('same','NVDA','buy',10,'Test thesis',True);before=store.public()
    with pytest.raises(Exception):store.fill('same','NVDA','buy',10,'Test thesis',True)
    assert store.public()['cash']==before['cash'];assert store.public()['holdings']==before['holdings'];assert store.public()['trade_count']==1

@pytest.mark.parametrize('kind',['stale','closed','paused','oversell','overspend','concentration','nan','negative'])
def test_guards_preserve_cash_and_positions(store,kind):
    quote(store,age=91 if kind=='stale' else 0)
    if kind=='paused':store.set('status','paused')
    side='sell' if kind=='oversell' else 'buy';qty={'overspend':2000,'concentration':400,'nan':float('nan'),'negative':-1}.get(kind,10)
    with pytest.raises(ValueError):store.fill('a','NVDA',side,qty,'Test thesis',kind!='closed')
    assert store.get('cash')==100000*SCALE;assert not store.account()['holdings']

def test_partial_sale_preserves_cost_basis(store):
    quote(store);store.fill('a','NVDA','buy',20,'Test thesis',True);basis=store.account()['holdings'][0]['cost']
    store.fill('b','NVDA','sell',5,'Test thesis',True)
    p=store.account()['holdings'][0];assert p['qty']==15*SCALE;assert p['cost']==basis-basis//4

def test_budget_survives_restart_and_failed_request(store):
    for _ in range(42):
        rid=store.reserve('ai',.01,cap=42);assert rid;store.complete(rid,'failed')
    assert store.reserve('ai',.01,cap=42) is None
    path=store.db.execute('PRAGMA database_list').fetchone()[2]
    reopened=Store(path);assert reopened.reserve('ai',.01,cap=42) is None
    assert reopened.reserve('search',cap=48)

def test_market_calendar_holiday_early_close_and_weekend(store):
    e=Engine(store)
    def opened(t):return e.market_open(datetime.fromisoformat(t).timestamp())
    assert not opened('2026-10-03T15:00:00+00:00')
    assert not opened('2026-12-25T15:00:00+00:00')
    assert opened('2026-11-27T17:00:00+00:00')
    assert not opened('2026-11-27T19:00:00+00:00')
    asyncio.run(e.close())

def test_model_requires_known_price_and_reserves_worst_case(store):
    async def scenario():
        e=Engine(store)
        async def handler(req):
            if req.url.path.endswith('/models'):return httpx.Response(200,json={'data':[{'id':'qwen/qwen3-32b','pricing':{'prompt':'0.0000001','completion':'0.0000004'}}]})
            assert req.url.host=='ai.hackclub.com'
            body=json.loads(req.content);assert body['max_tokens']==1800
            return httpx.Response(200,json={'choices':[{'message':{'content':'{"title":"Review","note":"Learned from outcomes","actions":[]}'}}]})
        await e.http.aclose();e.http=httpx.AsyncClient(transport=httpx.MockTransport(handler));os.environ['HACKCLUB_AI_KEY']='test'
        obj=await e.decide([],False);assert obj['actions']==[]
        assert store.rows("SELECT cost FROM requests WHERE provider='ai'")[0]['cost']>0
        await e.close()
    asyncio.run(scenario())

def test_closed_review_and_pause_cannot_execute(store):
    quote(store);e=Engine(store);e.market_open=lambda stamp=None:True
    obj={'title':'Review','note':'Lesson','actions':[{'symbol':'NVDA','side':'buy','quantity':10,'reason':'Momentum is strong'}]}
    e.apply(obj,False);assert store.public()['trade_count']==0
    store.set('status','paused');e.apply(obj,True);assert store.public()['trade_count']==0
    asyncio.run(e.close())

def test_api_auth_origin_and_control_only(tmp_path,monkeypatch):
    monkeypatch.setenv('STOCKBOT_DB',str(tmp_path/'api.db'));monkeypatch.setenv('STOCKBOT_DISABLE_WORKER','1');monkeypatch.setenv('SESSION_SECRET','a'*64);monkeypatch.setenv('ADMIN_PASSCODE','test-pass');monkeypatch.setenv('ALLOW_HTTP','1')
    import importlib,backend.app
    api=importlib.reload(backend.app)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app),base_url='http://test') as c:
            assert (await c.get('/api/admin/status')).status_code==401
            assert (await c.post('/api/admin/login',json={'passcode':'test-pass'},headers={'Origin':'http://evil'})).status_code==403
            assert (await c.post('/api/admin/login',json={'passcode':'test-pass'},headers={'Origin':'http://test'})).status_code==200
            assert (await c.post('/api/admin/control',json={'action':'buy'},headers={'Origin':'http://test'})).status_code==400
            assert (await c.post('/api/admin/control',json={'action':'pause'},headers={'Origin':'http://test'})).json()['status']=='paused'
            assert (await c.post('/api/admin/control',json={'action':'stop'},headers={'Origin':'http://test'})).json()['status']=='stopped'
            assert (await c.post('/api/admin/control',json={'action':'resume'},headers={'Origin':'http://test'})).status_code==409
            public=(await c.get('/api/public')).json();assert public['simulation'];assert 'test-pass' not in json.dumps(public)
        await api.engine.close()
    asyncio.run(scenario())

def test_no_alpaca_order_or_account_api_in_source():
    from pathlib import Path
    text=Path('backend/engine.py').read_text();assert 'paper-api.alpaca' not in text;assert '/orders' not in text;assert '/positions' not in text
    assert len(SYMBOLS)==30

def test_unexpected_provider_cost_stops_future_ai_calls(store,monkeypatch):
    monkeypatch.setenv('HACKCLUB_AI_KEY','test')
    async def scenario():
        e=Engine(store);calls=[]
        async def handler(req):
            if req.url.path.endswith('/models'):return httpx.Response(200,json={'data':[{'id':'deepseek/deepseek-v4-pro','pricing':{'prompt':'0.0000002088','completion':'0.0000004176'}}]})
            body=json.loads(req.content);assert body['provider']['max_price']['completion']==2.7
            calls.append(req)
            return httpx.Response(200,json={'usage':{'cost':0.02},'choices':[{'message':{'content':'{"actions":[]}'}}]})
        await e.http.aclose();e.http=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with pytest.raises(ValueError):await e.decide([],False)
        assert store.get('cooldown_ai')>now()
        assert store.rows("SELECT cost FROM requests WHERE provider='ai'")[0]['cost']==.02
        with pytest.raises(ValueError):await e.decide([],False)
        assert len(calls)==1
        await e.close()
    asyncio.run(scenario())

def test_listener_accepts_ipv4_and_ipv6():
    import socket
    from backend.serve import listener
    with listener(0) as server:
        port=server.getsockname()[1]
        server.settimeout(2)
        for family,address in [(socket.AF_INET,'127.0.0.1')]+([(socket.AF_INET6,'::1')] if socket.has_dualstack_ipv6() else []):
            with socket.socket(family,socket.SOCK_STREAM) as client:
                client.settimeout(2);client.connect((address,port))
                connection,_=server.accept()
                connection.close()

@pytest.mark.parametrize('value,seconds',[('2m59.56s',179.56),('7.66s',7.66),('1h2m3s',3723),('500ms',.5),('60',60)])
def test_reset_header_durations(value,seconds):
    from backend.limits import reset_time
    assert reset_time(value,1000)==pytest.approx(1000+seconds)

def test_header_cooldown_and_persistence(store):
    from backend.limits import capture,reset_time
    stamp=now()
    assert reset_time('nonsense',stamp) is None
    assert reset_time('1791040000000',stamp)==1791040000
    capture(store,'ai',httpx.Response(200,headers={'x-ratelimit-reset-requests':'1h','x-ratelimit-reset-tokens':'7.66s','x-ratelimit-remaining-requests':'40','x-ratelimit-remaining-tokens':'0'}),stamp)
    assert store.get('cooldown_ai')==pytest.approx(stamp+8.66)
    assert store.get('limits_ai')['requests_reset_at']==stamp+3600
    assert 'credit_retry_at' not in store.get('limits_ai')
    reopened=Store(store.db.execute('PRAGMA database_list').fetchone()[2]);assert reopened.get('limits_ai')['tokens_reset_at']==pytest.approx(stamp+7.66)

def test_credit_failure_keeps_spending_budget(store):
    from backend.limits import capture
    store.reserve('ai',.01)
    capture(store,'ai',httpx.Response(402,headers={'x-ratelimit-reset-tokens':'2s'}),now())
    assert store.get('cooldown_ai')>now()+2
    assert store.rows("SELECT cost FROM requests WHERE provider='ai'")[0]['cost']==.01
    assert 'fallback' in store.get('limits_ai')['credit_retry_source']

def test_weekend_plan_does_not_execute_and_strategy_is_persisted(store):
    quote(store);e=Engine(store);e.market_open=lambda stamp=None:False
    obj={'title':'Monday plan','note':'Review catalysts','strategy':{'name':'Defensive swing','why':'Uncertain catalysts','horizon':'swing'},'plan':{'summary':'Wait for confirmation','why':'No valid weekend prices','watchlist':[{'symbol':'NVDA','condition':'Breaks resistance','why':'Momentum','invalidation':'Falls below support'}],'steps':['Recheck quotes after opening']},'actions':[{'symbol':'NVDA','side':'buy','quantity':10,'reason':'Ignore weekend restriction'}]}
    e.apply(obj,False)
    assert store.public()['trade_count']==0;assert store.public()['strategy']=='Defensive swing'
    assert store.public()['plan']['watchlist'][0]['condition']=='Breaks resistance'
    assert 'saved_plan' in json.loads(e.context([],True))
    asyncio.run(e.close())

def test_risk_unknown_until_sufficient_samples_and_more_movement_is_riskier():
    from backend.risk import calculate
    stamp=now()
    def rows(amplitude):return [{'ts':stamp-(40-i)*60,'bid':int((100+amplitude*(i%2))*SCALE),'ask':int((100.01+amplitude*(i%2))*SCALE)} for i in range(40)]
    calm=rows(.01);volatile=rows(2)
    assert calculate(calm[:3],calm[-1],.1,stamp)['score'] is None
    low=calculate(calm,calm[-1],.1,stamp);high=calculate(volatile,volatile[-1],.1,stamp)
    assert 0<=low['score']<high['score']<=100
    assert high['samples']==39

def test_429_uses_exhausted_token_reset_not_unexhausted_request_window(store):
    from backend.limits import capture
    stamp=now()
    capture(store,'ai',httpx.Response(429,headers={'x-ratelimit-reset-requests':'1d','x-ratelimit-remaining-requests':'20','x-ratelimit-reset-tokens':'9s','x-ratelimit-remaining-tokens':'0','retry-after':'2'}),stamp)
    assert store.get('cooldown_ai')==pytest.approx(stamp+10)

def test_sparse_risk_quotes_not_manufactured_into_volatility():
    from backend.risk import calculate
    stamp=now();rows=[{'ts':stamp-i*86400,'bid':100*SCALE,'ask':101*SCALE} for i in range(40)][::-1]
    assert calculate(rows,rows[-1],.1,stamp)['score'] is None

def test_dynamic_ticker_and_holdings_only_risk(store):
    async def run():
        e=Engine(store);e.market_open=lambda stamp=None:True
        async def prices(symbols=None):
            assert symbols==['IBM'];quote(store,'IBM')
        e.fallback_quotes=prices
        obj={'actions':[{'symbol':'IBM','side':'buy','quantity':2,'reason':'Independent earnings thesis'}]}
        await e.prepare_actions(obj,True);e.apply(obj,True)
        assert set(store.public()['stock_risks'])=={'IBM'}
        assert 'IBM' in e.tracked_symbols()
        store.fill('exit','IBM','sell',2,'Close thesis',True)
        assert store.public()['stock_risks']=={}
        await e.close()
    asyncio.run(run())

def test_closed_market_discovery_never_fetches_or_trades(store):
    async def run():
        e=Engine(store)
        async def forbidden(*args):raise AssertionError('No closed-market execution quotes')
        e.fallback_quotes=forbidden
        obj={'actions':[{'symbol':'IBM','side':'buy','quantity':2,'reason':'Independent thesis'}],'plan':{'summary':'Watch IBM','why':'Earnings catalyst','watchlist':[{'symbol':'IBM','condition':'Breakout'}]}}
        await e.prepare_actions(obj,False);e.apply(obj,False)
        assert store.get('plan')['watchlist'][0]['symbol']=='IBM'
        assert store.public()['trade_count']==0
        await e.close()
    asyncio.run(run())
