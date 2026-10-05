"""Read-only, credential-free local diagnostic summary."""
import json,os,sqlite3
from pathlib import Path
path=Path(os.getenv('STOCKBOT_DB','data/stockbot.sqlite3')).resolve()
db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
keys=('status','phase','last_error','last_cycle','model','cooldown_ai','cooldown_search','cooldown_alpaca')
print(json.dumps({row['key']:json.loads(row['value']) for row in db.execute('SELECT key,value FROM state WHERE key IN ('+','.join('?' for _ in keys)+')',keys)},indent=2))
print('Recent cycle failures:')
try:
    for row in db.execute('SELECT * FROM cycle_errors ORDER BY ts DESC LIMIT 10'):print(dict(row))
except sqlite3.OperationalError:print('Detailed diagnostics appear after upgrading the backend.')
print('Rolling usage:')
for row in db.execute("SELECT provider,COUNT(*) calls,SUM(cost) reserved FROM requests WHERE ts>strftime('%s','now')-86400 GROUP BY provider"):print(dict(row))
print('Ledger trades:',db.execute('SELECT COUNT(*) FROM trades').fetchone()[0])
