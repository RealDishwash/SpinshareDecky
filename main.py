"""SpinShare Decky backend. Standard library only; runs as the Deck user."""
import asyncio
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import threading
import time
import urllib.request
import zipfile

API = 'https://spinsha.re/api/'
SUFFIX = Path('steamapps/compatdata/1058830/pfx/drive_c/users/steamuser/AppData/LocalLow/Super Spin Digital/Spin Rhythm XD/Custom')
MAX_ZIP = 256 * 1024 * 1024
MAX_FILES = 512
MAX_UNPACKED = 512 * 1024 * 1024


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    with temp.open('w') as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_path(root, relative):
    parts = PurePosixPath(relative).parts
    if not parts or '..' in parts or PurePosixPath(relative).is_absolute() or '\\' in relative:
        raise ValueError('Unsafe song file path')
    target = root.joinpath(*parts)
    for parent in [target, *target.parents]:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError('Song files must not be symbolic links')
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('Song file escapes Custom folder')
    return target


class Library:
    def __init__(self, root):
        self.root = Path(root)
        self.db = self.root / '.spinshare-decky.json'

    def records(self):
        return json.loads(self.db.read_text()) if self.db.exists() else {}

    def install(self, song, archive):
        records = self.records()
        key = str(song['id'])
        if key in records:
            raise ValueError('Song already installed. Delete it before downloading again.')
        self.root.mkdir(parents=True, exist_ok=True)
        files = {}
        # Stage and validate the whole archive before touching the game library.
        with tempfile.TemporaryDirectory(prefix='.spinshare-stage-', dir=self.root) as stage:
            stage = Path(stage)
            with zipfile.ZipFile(archive) as bundle:
                entries = bundle.infolist()
                if len(entries) > MAX_FILES or sum(i.file_size for i in entries) > MAX_UNPACKED:
                    raise ValueError('Song archive exceeds safety limits')
                for entry in entries:
                    if entry.is_dir():
                        continue
                    raw = PurePosixPath(entry.filename)
                    if raw.is_absolute() or '..' in raw.parts or '\\' in entry.filename or stat.S_ISLNK(entry.external_attr >> 16):
                        raise ValueError('Unsafe path in song archive')
                    # Backups may have one enclosing folder; preserve game asset layout.
                    if len(raw.parts) >= 2 and raw.parts[-2] in ('AlbumArt', 'AudioClips'):
                        relative = '/'.join(raw.parts[-2:])
                    elif raw.suffix.lower() == '.srtb':
                        relative = raw.name
                    else:
                        continue
                    if relative in files:
                        raise ValueError('Duplicate file in song archive')
                    destination = safe_path(self.root, relative)
                    staged = safe_path(stage, relative)
                    staged.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(entry) as source, staged.open('wb') as output:
                        shutil.copyfileobj(source, output)
                    checksum = digest(staged)
                    if destination.exists() and digest(destination) != checksum:
                        raise ValueError(f'Existing file would be overwritten: {relative}')
                    files[relative] = {'sha256': checksum, 'owned': not destination.exists() or any(r.get('files', {}).get(relative, {}).get('owned') for r in records.values())}
            if not any(f.endswith('.srtb') for f in files):
                raise ValueError('Archive contains no Spin Rhythm chart')
            if shutil.disk_usage(self.root).free < sum((stage / f).stat().st_size for f in files) + 16 * 1024 * 1024:
                raise ValueError('Not enough free space to install song')
            created = []
            try:
                for relative in files:
                    target = safe_path(self.root, relative)
                    if not target.exists():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        # Exclusive creation prevents accidental replacement.
                        with target.open('xb') as output:
                            created.append(target)
                            with (stage / relative).open('rb') as source:
                                shutil.copyfileobj(source, output)
                records[key] = {'song': song, 'files': files}
                atomic_json(self.db, records)
            except BaseException:
                for target in created:
                    target.unlink(missing_ok=True)
                raise
        return {'message': f"Installed {song['title']}"}

    def delete(self, key):
        records = self.records()
        if key.startswith('local:'):
            relative = key[6:]
            if '/' in relative or not relative.endswith('.srtb'):
                raise ValueError('Invalid local chart')
            target = safe_path(self.root, relative)
            if any(relative in r['files'] for r in records.values()):
                raise ValueError('Use the managed song entry to delete this chart')
            target.unlink()
            return {'message': 'Chart deleted. Existing audio and artwork were preserved.'}
        record = records.get(key)
        if not record:
            raise ValueError('Song is not installed')
        others = {f for k, r in records.items() if k != key for f in r['files']}
        # Unknown local charts may reference any asset. Keep assets in that case.
        known = {f for r in records.values() for f in r['files']}
        unknown = any(p.name not in known for p in self.root.glob('*.srtb'))
        # A retained chart can still reference these assets.
        unknown = unknown or any(
            f.endswith('.srtb') and safe_path(self.root, f).exists()
            and (not info['owned'] or digest(safe_path(self.root, f)) != info['sha256'])
            for f, info in record['files'].items())
        targets = []
        kept = 0
        for relative, info in record['files'].items():
            target = safe_path(self.root, relative)
            if relative in others or not target.exists():
                continue
            if not info['owned'] or (unknown and '/' in relative) or digest(target) != info['sha256']:
                kept += 1
                continue
            targets.append(target)
        # Move to temporary trash and restore on failure before committing manifest.
        with tempfile.TemporaryDirectory(prefix='.spinshare-delete-', dir=self.root) as trash:
            moved = []
            try:
                for i, target in enumerate(targets):
                    backup = Path(trash) / str(i)
                    os.replace(target, backup)
                    moved.append((target, backup))
                del records[key]
                atomic_json(self.db, records)
            except BaseException:
                for target, backup in reversed(moved):
                    os.replace(backup, target)
                raise
        return {'message': 'Song deleted.' + (f' Preserved {kept} shared, pre-existing or modified files.' if kept else '')}

    def listing(self):
        records = self.records()
        songs = []
        known = set()
        for key, record in records.items():
            known.update(record['files'])
            songs.append({**record['song'], 'key': key, 'installed': True,
                          'missing': any(not safe_path(self.root, f).exists() for f in record['files'])})
        for path in sorted(self.root.glob('*.srtb')):
            if path.name not in known and not path.is_symlink():
                songs.append({'id': 0, 'key': 'local:' + path.name, 'title': path.stem,
                              'artist': 'Existing custom chart', 'charter': '', 'local': True, 'installed': True})
        return songs


class Plugin:
    def __init__(self):
        self.lock = threading.Lock()
        self.cache = {}
        self.job = {'state': 'idle', 'message': ''}
        self.task = None
        self.home = Path(os.environ.get('DECKY_USER_HOME', str(Path.home())))
        self.settings = Path(os.environ.get('DECKY_PLUGIN_SETTINGS_DIR', str(self.home / '.config/spinshare-decky'))) / 'settings.json'

    def candidates(self):
        roots = {self.home / '.local/share/Steam', self.home / '.steam/steam'}
        for root in list(roots):
            vdf = root / 'steamapps/libraryfolders.vdf'
            if vdf.exists():
                roots.update(Path(p.replace('\\\\', '\\')) for p in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text()))
        return sorted({str((root / SUFFIX).resolve()) for root in roots if (root / SUFFIX.parent).is_dir()})

    def root(self):
        settings = json.loads(self.settings.read_text()) if self.settings.exists() else {}
        if settings.get('path'):
            path = Path(settings['path'])
            if not path.parent.is_dir():
                raise ValueError('Custom folder is unavailable. Check that your SD card is mounted.')
            return path
        candidates = self.candidates()
        if len(candidates) != 1:
            raise ValueError('Select a Custom folder in Settings. Launch Spin Rhythm XD first to create its Proton prefix.')
        return Path(candidates[0])

    def api(self, endpoint, body=None):
        key = endpoint + json.dumps(body)
        if key in self.cache and time.monotonic() - self.cache[key][0] < 60:
            return self.cache[key][1]
        request = urllib.request.Request(API + endpoint, data=json.dumps(body).encode() if body is not None else None,
                                         headers={'User-Agent': 'SpinShareDecky/0.1.0', 'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=30) as response:
            value = json.loads(response.read(8 * 1024 * 1024))
        if value.get('status') == 404:
            return []
        if value.get('status') != 200:
            raise ValueError('SpinShare could not complete the request')
        if len(self.cache) > 100:
            self.cache.clear()
        self.cache[key] = (time.monotonic(), value['data'])
        return value['data']

    async def browse(self, mode='new', query='', offset=0):
        if mode not in ('new', 'updated', 'hotThisWeek', 'hotThisMonth', 'search'):
            raise ValueError('Invalid browse mode')
        offset = max(0, min(int(offset), 100000))
        if mode == 'search':
            data = await asyncio.to_thread(self.api, 'searchCharts', {'searchQuery': str(query)[:200], 'showExplicit': True})
            return {'songs': data[offset:offset + 12], 'hasMore': len(data) > offset + 12}
        data = await asyncio.to_thread(self.api, f'songs/{mode}/{offset}')
        return {'songs': data, 'hasMore': len(data) == 12}

    async def detail(self, song_id):
        return await asyncio.to_thread(self.api, f'song/{int(song_id)}')

    async def status(self):
        return await asyncio.to_thread(self._status)

    def _status(self):
        try:
            root = self.root()
            with self.lock:
                songs = Library(root).listing()
            return {'path': str(root), 'candidates': self.candidates(), 'songs': songs, 'job': dict(self.job), 'error': ''}
        except (ValueError, OSError) as error:
            return {'path': '', 'candidates': self.candidates(), 'songs': [], 'job': dict(self.job), 'error': str(error)}

    async def set_path(self, path):
        if self.task and not self.task.done():
            raise ValueError('Wait for the download to finish')
        path = Path(path).expanduser()
        if not path.is_absolute() or path.name != 'Custom' or not path.parent.is_dir():
            raise ValueError('Choose an absolute Custom path inside an existing Spin Rhythm XD save folder')
        atomic_json(self.settings, {'path': str(path.resolve())})
        return await self.status()

    async def install(self, song_id):
        if self.task and not self.task.done():
            raise ValueError('A download is already in progress')
        root = self.root()
        song_id = int(song_id)
        self.job = {'state': 'downloading', 'message': 'Fetching chart details…', 'id': song_id, 'bytes': 0}
        self.task = asyncio.create_task(asyncio.to_thread(self._download, root, song_id))
        return True

    def _download(self, root, song_id):
        try:
            song = self.api(f'song/{song_id}')
            if not isinstance(song, dict):
                raise ValueError('Song no longer exists on SpinShare')
            if song.get('dlc'):
                raise ValueError('This chart requires DLC verification. Install it with the official SpinShare client.')
            with tempfile.TemporaryFile() as archive:
                request = urllib.request.Request(API + f'song/{song_id}/download', headers={'User-Agent': 'SpinShareDecky/0.1.0'})
                with urllib.request.urlopen(request, timeout=60) as response:
                    received = 0
                    while chunk := response.read(256 * 1024):
                        received += len(chunk)
                        if received > MAX_ZIP:
                            raise ValueError('Download exceeds 256 MiB limit')
                        archive.write(chunk)
                        self.job = {'state': 'downloading', 'message': f"Downloading {song['title']}", 'id': song_id, 'bytes': received}
                archive.seek(0)
                self.job = {'state': 'installing', 'message': 'Installing chart, audio and artwork…', 'id': song_id}
                with self.lock:
                    result = Library(root).install(song, archive)
            self.job = {'state': 'done', **result, 'id': song_id}
        except Exception as error:
            self.job = {'state': 'error', 'message': str(error), 'id': song_id}

    async def delete_song(self, key):
        if self.task and not self.task.done():
            raise ValueError('Wait for the download to finish')
        def remove():
            with self.lock:
                return Library(self.root()).delete(str(key))
        return await asyncio.to_thread(remove)

    async def _main(self):
        pass

    async def _unload(self):
        if self.task:
            await self.task
