"""Run only with stockbot.service stopped; backs up SQLite before the authorized reset."""
import argparse,os,sys,subprocess,sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from backend.store import Store
from backend.reset import reset_experiment
parser=argparse.ArgumentParser();parser.add_argument('--start-date',required=True)
args=parser.parse_args()
start=datetime.strptime(args.start_date,'%Y-%m-%d').replace(hour=9,minute=30,tzinfo=ZoneInfo('America/New_York')).timestamp()
cmd=['systemctl']+([] if os.getuid()==0 else ['--user'])+['is-active','--quiet','stockbot.service']
if subprocess.run(cmd).returncode==0:raise SystemExit('Stop stockbot.service before resetting the ledger.')
path=os.getenv('STOCKBOT_DB','data/stockbot.sqlite3')
for line in Path('.env').read_text().splitlines() if Path('.env').exists() else []:
    if line.startswith('STOCKBOT_DB='):path=line.split('=',1)[1].strip().strip('"').strip("'")
store=Store(path);reset_id='fresh-'+args.start_date
row=store.db.execute("SELECT value FROM state WHERE key='reset_id'").fetchone()
if row and store.get('reset_id')==reset_id:raise SystemExit('This reset has already been applied. No balances changed.')
backups=Path('data/backups');backups.mkdir(parents=True,exist_ok=True);os.chmod(backups,0o700)
backup=backups/('before-reset-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')
with sqlite3.connect(backup) as target:store.db.backup(target)
os.chmod(backup,0o600)
reset_experiment(store,start,reset_id)
print('Reset complete: $100,000 cash, zero holdings, fresh ledger. Starts '+args.start_date+' at 9:30 AM America/New_York.')
print('Prior experiment backed up to '+str(backup)+'. Price history and provider usage/cooldowns preserved.')
