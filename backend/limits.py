"""Provider reset metadata. Rate-limit reset headers are NOT dollar-credit reset promises."""
import math,re
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime

def reset_time(value,stamp):
    if not value:return None
    s=str(value).strip()
    try:
        n=float(s)
        if not math.isfinite(n) or n<0:return None
        if n>1e12:n/=1000
        return n if n>1e9 else stamp+n
    except ValueError:pass
    matches=re.findall(r'(\d+(?:\.\d+)?)(ms|d|h|m|s)',s)
    if matches and ''.join(n+u for n,u in matches)==s:
        seconds=sum(float(n)*{'ms':.001,'s':1,'m':60,'h':3600,'d':86400}[u] for n,u in matches)
        return stamp+seconds
    try:
        dt=datetime.fromisoformat(s.replace('Z','+00:00'))
        if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        try:return parsedate_to_datetime(s).timestamp()
        except (ValueError,TypeError,OverflowError):return None

def capture(store,provider,response,stamp,scope=None):
    headers=response.headers;key='limits_'+provider+('_'+scope if scope else '')
    row=store.db.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()
    import json
    metadata=json.loads(row[0]) if row else {}
    metadata['observed_at']=stamp
    blocking=[]
    for category in ('requests','tokens'):
        name='x-ratelimit-reset-'+category
        if name in headers:
            target=reset_time(headers[name],stamp)
            metadata[category+'_reset_at']=target
            metadata[category+'_reset_raw']=headers[name][:128]
        remaining=headers.get('x-ratelimit-remaining-'+category)
        if remaining is not None:
            try:
                number=float(remaining)
                if math.isfinite(number):metadata[category+'_remaining']=max(0,number)
            except ValueError:pass
        target=metadata.get(category+'_reset_at')
        remaining_value=metadata.get(category+'_remaining')
        if remaining is not None and target and target>stamp and isinstance(remaining_value,(int,float)) and remaining_value<=0:blocking.append(target)
    retry=reset_time(headers.get('retry-after'),stamp)
    if response.status_code==429:
        if retry and retry>stamp:blocking.append(retry)
        if not blocking:blocking.extend(t for t in (metadata.get('requests_reset_at'),metadata.get('tokens_reset_at')) if t and t>stamp)
        if not blocking:blocking.append(stamp+600)
    if response.status_code==402:
        # A money balance limit is separate; absent explicit credit metadata, retry at next UTC day.
        credit=reset_time(headers.get('x-credit-reset-at'),stamp)
        target=credit if credit and credit>stamp else (int(stamp)//86400+1)*86400+5
        metadata['credit_retry_at']=target
        metadata['credit_retry_source']='x-credit-reset-at' if credit else 'UTC day fallback; not confirmed by rate-limit headers'
        blocking.append(target)
    if response.status_code in (401,403,422):blocking.append(stamp+86400)
    if blocking:
        cooldown_key='cooldown_'+provider+('_'+scope if scope else '')
        row=store.db.execute('SELECT value FROM state WHERE key=?',(cooldown_key,)).fetchone()
        previous=json.loads(row[0]) if row else 0
        store.set(cooldown_key,max(previous,max(blocking)+1))
        # Request/token exhaustion may be account-wide: do not switch keys to bypass it.
        if scope and (response.status_code==429 or any(metadata.get(c+'_remaining')==0 for c in ('requests','tokens'))):
            store.set('cooldown_'+provider,max(store.get('cooldown_'+provider),max(blocking)+1))
    store.set(key,metadata)
    if scope:store.set('limits_'+provider,metadata)
    return metadata
