"""Add three OPTIONAL auth fallback key pairs privately, preserving existing env values."""
import getpass,os,re
from pathlib import Path
path=Path('.env')
if not path.exists():raise SystemExit('Run install-nest.sh first to configure the primary credentials.')
text=path.read_text();updates={}
for i in (2,3,4):
    key=getpass.getpass(f'Optional Alpaca key {i} (Enter to keep/skip): ').strip()
    if not key:continue
    secret=getpass.getpass(f'Alpaca secret {i}: ').strip()
    if not secret:raise SystemExit('Matching secret required; nothing saved.')
    if any(c in key+secret for c in '\n\r"\\'):raise SystemExit('Invalid credential characters; nothing saved.')
    updates['ALPACA_KEY_'+str(i)]=key;updates['ALPACA_SECRET_'+str(i)]=secret
for name,value in updates.items():
    pattern=r'^'+re.escape(name)+r'=.*$'
    line=name+'="'+value+'"'
    if re.search(pattern,text,re.M):text=re.sub(pattern,lambda _:line,text,flags=re.M)
    else:text=text.rstrip()+'\n'+line+'\n'
if updates:
    temporary=path.with_name('.env.alpaca.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as file:file.write(text)
    os.replace(temporary,path)
print('Optional authentication fallback configuration saved. All slots share the global request/cooldown guard.')
