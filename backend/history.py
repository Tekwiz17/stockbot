"""Six-month price memory and summaries, calculated locally without AI calls."""
import math
from .store import SCALE,now
RETENTION=90*86400

def archive(store,symbols,stamp=None):
    stamp=now() if stamp is None else stamp
    bucket=int(stamp//300)*300
    for symbol in symbols:
        q=store.latest(symbol)
        if q and 0<=stamp-q['ts']<=300:
            store.db.execute('INSERT OR REPLACE INTO price_history VALUES (?,?,?,?,?)',(symbol,bucket,q['ts'],q['bid'],q['ask']))
    store.db.execute('DELETE FROM price_history WHERE bucket<? AND bucket < ? - COALESCE((SELECT days FROM history_retention WHERE history_retention.symbol=price_history.symbol),90)*86400',(stamp-RETENTION,stamp))
    store.set('last_price_archive',stamp)

def summary(store,symbol,stamp=None):
    stamp=now() if stamp is None else stamp
    last=store.db.execute('SELECT * FROM price_history WHERE symbol=? ORDER BY bucket DESC LIMIT 1',(symbol,)).fetchone()
    if not last:return {'samples':0}
    mid=(last['bid']+last['ask'])/2
    result={'as_of':last['quote_ts'],'samples':store.db.execute('SELECT COUNT(*) FROM price_history WHERE symbol=?',(symbol,)).fetchone()[0]}
    for label,seconds in [('30m',1800),('1d',86400),('5d',5*86400),('20d',20*86400),('90d',90*86400)]:
        target=last['quote_ts']-seconds
        anchor=store.db.execute('SELECT bid,ask,quote_ts FROM price_history WHERE symbol=? AND quote_ts<=? ORDER BY bucket DESC LIMIT 1',(symbol,target)).fetchone()
        # Allow weekend/session gaps, but do not present a much older point as a short-window return.
        tolerance=300 if seconds<86400 else 4*86400
        if anchor and target-anchor['quote_ts']<=tolerance:
            result[label]=round((mid/((anchor['bid']+anchor['ask'])/2)-1)*100,3)
    rows=store.rows('SELECT bucket,bid,ask FROM price_history WHERE symbol=? AND bucket>? ORDER BY bucket',(symbol,last['bucket']-20*86400))
    mids=[(r['bid']+r['ask'])/2 for r in rows]
    if mids:
        result['range20d_pct']=round((max(mids)/min(mids)-1)*100,3)
        result['drawdown20d_pct']=round((mid/max(mids)-1)*100,3)
    returns=[math.log(mids[i]/mids[i-1]) for i in range(1,len(rows)) if 240<=rows[i]['bucket']-rows[i-1]['bucket']<=360]
    if len(returns)>=20:
        import statistics
        result['daily_vol_proxy_pct']=round(statistics.stdev(returns)*math.sqrt(78)*100,3)
    return result
