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
