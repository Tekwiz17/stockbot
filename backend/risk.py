"""Explainable heuristic from observed quotes, never a loss probability or AI guess."""
import math,statistics

def calculate(rows,quote,weight,stamp):
    points=[(r['ts'],(r['bid']+r['ask'])/2) for r in rows if r['bid']>0 and r['ask']>=r['bid']]
    returns=[math.log(b[1]/a[1]) for a,b in zip(points,points[1:]) if 30<=b[0]-a[0]<=180]
    base={'score':None,'label':'Insufficient data','samples':len(returns),'as_of':quote['ts'] if quote else None,'stale':not quote or stamp-quote['ts']>90,'method':'Observed one-minute volatility, drawdown, bid/ask spread and portfolio weight. Heuristic 0–100; not a probability of loss.'}
    if len(returns)<20:return base
    daily_vol=statistics.stdev(returns)*math.sqrt(390)*100
    peak=0;drawdown=0
    for _,price in points:peak=max(peak,price);drawdown=max(drawdown,(peak-price)/peak*100)
    spread=(quote['ask']-quote['bid'])/((quote['ask']+quote['bid'])/2)*100 if quote else 0
    # 45 points volatility, 25 drawdown, 15 spread, 15 concentration. Components saturate.
    score=round(min(45,daily_vol/8*45)+min(25,drawdown/10*25)+min(15,spread/.5*15)+min(15,max(0,weight)/.30*15))
    return {**base,'score':score,'label':'Low' if score<30 else 'Moderate' if score<60 else 'High','daily_volatility_proxy_pct':round(daily_vol,2),'observed_drawdown_pct':round(drawdown,2),'spread_pct':round(spread,3),'position_weight_pct':round(weight*100,2)}
