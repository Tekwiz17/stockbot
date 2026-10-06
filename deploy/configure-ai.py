"""Privately configure the second independently funded AI key; no experiment reset."""
import getpass,os,re
from pathlib import Path
path=Path('.env')
if not path.exists():raise SystemExit('Install the backend first.')
text=path.read_text()
key=getpass.getpass('Second Hack Club AI key (Enter to keep/skip): ').strip()
if not key:raise SystemExit('Existing configuration preserved.')
if any(c in key for c in '\n\r"\\'):raise SystemExit('Invalid key characters; nothing saved.')
primary=re.search(r'^HACKCLUB_AI_KEY=(.*)$',text,re.M)
if primary and primary.group(1).strip().strip('"').strip("'")==key:raise SystemExit('This is the primary key; duplicate keys cannot add a second budget.')
line='HACKCLUB_AI_KEY_2="'+key+'"'
if re.search(r'^HACKCLUB_AI_KEY_2=.*$',text,re.M):text=re.sub(r'^HACKCLUB_AI_KEY_2=.*$',lambda _:line,text,flags=re.M)
else:text=text.rstrip()+'\n'+line+'\n'
temporary=path.with_name('.env.ai.tmp')
fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as file:file.write(text)
os.replace(temporary,path)
print('Second AI key saved privately. $0.55 rolling allowance and $0.05 buffer per distinct, independently funded key. Restart stockbot to load it.')
