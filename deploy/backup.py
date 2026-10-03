"""Online SQLite backup, preserving ledger consistency; retains the last seven backups."""
import os,sqlite3,time
from pathlib import Path
source=Path(os.getenv('STOCKBOT_DB','data/stockbot.sqlite3'))
dest=source.parent/'backups';dest.mkdir(parents=True,exist_ok=True);dest.chmod(0o700)
out=dest/(time.strftime('stockbot-%Y%m%d-%H%M%S')+'.sqlite3')
with sqlite3.connect(source) as src,sqlite3.connect(out) as target:src.backup(target)
out.chmod(0o600)
for old in sorted(dest.glob('stockbot-*.sqlite3'))[:-7]:old.unlink()
print('Ledger backup complete.')
