"""Add the owner's public domain without changing private credentials."""
from pathlib import Path
p=Path('.env')
lines=p.read_text().splitlines();origins=[]
for line in lines:
    if line.startswith('PUBLIC_ORIGINS='):
        origins.extend(line.split('=',1)[1].strip().strip('"').strip("'").split(','))
origins.append('https://stockbot.tekwiz17.me')
origins=list(dict.fromkeys(o.strip().rstrip('/') for o in origins if o.strip()))
lines=[line for line in lines if not line.startswith('PUBLIC_ORIGINS=')]
lines.append('PUBLIC_ORIGINS="'+','.join(origins)+'"')
p.write_text('\n'.join(lines)+'\n');p.chmod(0o600)
print('Public frontend origin configured; existing credentials preserved.')
