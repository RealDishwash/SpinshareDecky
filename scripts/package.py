"""Build the installable Decky zip without development dependencies."""
import json
from pathlib import Path
import zipfile
root = Path(__file__).resolve().parents[1]
version = json.loads((root / 'package.json').read_text())['version']
output = root / 'release' / f'spinshare-decky-{version}.zip'
output.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
    for name in ['package.json', 'plugin.json', 'main.py', 'README.md', 'LICENSE']:
        archive.write(root / name, 'spinshare-decky/' + name)
    for path in (root / 'dist').rglob('*'):
        if path.is_file():
            archive.write(path, 'spinshare-decky/' + str(path.relative_to(root)))
print(output)
