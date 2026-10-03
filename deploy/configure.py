"""Write private server configuration without ever echoing secrets."""
import getpass, os, secrets
from pathlib import Path
p=Path('.env')
if p.exists():
    print('Existing .env preserved. Edit it privately if settings must change.');raise SystemExit(0)
fields={
 'ALPACA_KEY':getpass.getpass('Alpaca market-data key: '),
 'ALPACA_SECRET':getpass.getpass('Alpaca market-data secret: '),
 'HACKCLUB_AI_KEY':getpass.getpass('Hack Club AI key: '),
 'HACKCLUB_SEARCH_KEY':getpass.getpass('Hack Club Search key: '),
 'ADMIN_PASSCODE':getpass.getpass('Admin passcode: '),
 'SESSION_SECRET':secrets.token_hex(32),
 'PUBLIC_ORIGINS':(input('Vercel production origin [https://stockbot.tekwiz17.me]: ').strip() or 'https://stockbot.tekwiz17.me')+',https://stockbot.tekwiz17.hackclub.app',
 'STOCKBOT_DB':str(Path.cwd()/'data/stockbot.sqlite3'),
}
if any(not v for v in fields.values()):raise SystemExit('All values are required; configuration was not saved.')
if any('\n' in v or '\r' in v or '"' in v or '\\' in v for v in fields.values()):raise SystemExit('Invalid environment value.')
fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:f.write(''.join(k+'="'+v+'"\n' for k,v in fields.items()))
print('Private environment saved with permissions 0600.')
