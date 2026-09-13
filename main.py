"""SpinShare Decky backend. Standard library only; runs as the Deck user."""
import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import hashlib
import gzip
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import ssl
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


# Decky's bundled Python may have build-time OpenSSL paths that do not exist
# on SteamOS. Add the host trust bundle without disabling TLS verification.
SYSTEM_CA_BUNDLES = (
    '/etc/ssl/certs/ca-certificates.crt',
    '/etc/ca-certificates/extracted/tls-ca-bundle.pem',
    '/etc/pki/tls/certs/ca-bundle.crt',
    '/etc/ssl/cert.pem',
)


def tls_context():
    context = ssl.create_default_context()
    for name in SYSTEM_CA_BUNDLES:
        bundle = Path(name)
        if bundle.is_file():
            context.load_verify_locations(cafile=str(bundle))
            break
    if not context.get_ca_certs():
        raise RuntimeError('No trusted system certificates found. Update SteamOS and restart Decky.')
    return context


DIFFICULTIES = {
    'easy': ('hasEasyDifficulty', 'easyDifficulty'),
    'normal': ('hasNormalDifficulty', 'normalDifficulty'),
    'hard': ('hasHardDifficulty', 'hardDifficulty'),
    'extreme': ('hasExtremeDifficulty', 'expertDifficulty'),
    'xd': ('hasXDDifficulty', 'XDDifficulty'),
}
BROWSE_MODES = ('new', 'updated', 'hotThisWeek', 'hotThisMonth', 'topYear', 'topAllTime', 'search')
SORT_ORDERS = ('recommended', 'difficultyAsc', 'difficultyDesc', 'title', 'downloads')
PAGE_SIZE = 12


def filter_options(options=None):
    options = options or {}
    difficulty = options.get('difficulty', 'all')
    order = options.get('sort', 'recommended')
    low, high = int(options.get('minimum', 0)), int(options.get('maximum', 99))
    if difficulty not in ('all', *DIFFICULTIES) or order not in SORT_ORDERS:
        raise ValueError('Invalid difficulty or sort order')
    if not 0 <= low <= high <= 99:
        raise ValueError('Difficulty range must be between 0 and 99, with minimum no higher than maximum')
    return {'difficulty': difficulty, 'minimum': low, 'maximum': high, 'sort': order}


def matching_ratings(song, options):
    tiers = DIFFICULTIES.values() if options['difficulty'] == 'all' else [DIFFICULTIES[options['difficulty']]]
    return [song[value] for flag, value in tiers
            if song.get(flag) and isinstance(song.get(value), (int, float))
            and not isinstance(song.get(value), bool)
            and options['minimum'] <= song[value] <= options['maximum']]


def song_date(song, field):
    value = song.get(field)
    if isinstance(value, dict):
        zone = value.get('timezone', 'Europe/Berlin')
        value = value.get('date')
    else:
        zone = 'Europe/Berlin'
    try:
        parsed = datetime.fromisoformat(value)
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=ZoneInfo(zone))).astimezone(timezone.utc)
    except (TypeError, ValueError, KeyError):
        return datetime.min.replace(tzinfo=timezone.utc)


def select_songs(songs, mode, options, now=None):
    """Filter and sort the complete search result BEFORE pagination."""
    now = now or datetime.now(timezone.utc)
    earliest = datetime.min.replace(tzinfo=timezone.utc)
    if mode == 'hotThisWeek':
        earliest = now - timedelta(days=7)
    elif mode == 'hotThisMonth':
        # Calendar-month window, matching SpinShare's one-month popularity list.
        previous = now.replace(day=1) - timedelta(days=1)
        earliest = now.replace(year=previous.year, month=previous.month, day=min(now.day, previous.day))
    elif mode == 'topYear':
        earliest = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    result = []
    unrestricted = options['difficulty'] == 'all' and options['minimum'] == 0 and options['maximum'] == 99
    for song in songs:
        # Direct chart-link searches can bypass the server's filters.
        ratings = matching_ratings(song, options)
        if not ratings and not unrestricted:
            continue
        uploaded = song_date(song, 'uploadDate')
        if mode in ('hotThisWeek', 'hotThisMonth', 'topYear') and not earliest <= uploaded <= now:
            continue
        if mode == 'updated' and song_date(song, 'updateDate') <= uploaded:
            continue
        result.append(song)
    order = options['sort']
    def identity(song):
        return str(song.get('title', '')).casefold(), int(song.get('id', 0))
    if order in ('difficultyAsc', 'difficultyDesc'):
        def difficulty_key(song):
            ratings = matching_ratings(song, options)
            if not ratings:
                return (True, 0, identity(song))
            value = min(ratings) if order == 'difficultyAsc' else -max(ratings)
            return (False, value, identity(song))
        result.sort(key=difficulty_key)
    elif order == 'title':
        result.sort(key=identity)
    elif order == 'downloads' or (order == 'recommended' and mode in ('hotThisWeek', 'hotThisMonth', 'topYear', 'topAllTime')):
        result.sort(key=lambda song: (-(song.get('downloads') or 0), -(song.get('views') or 0), identity(song)))
    else:
        result.sort(key=lambda song: (song_date(song, 'updateDate' if mode == 'updated' else 'uploadDate'), int(song.get('id', 0))), reverse=True)
    return result


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
        if key in self.cache and time.monotonic() - self.cache[key][0] < (300 if endpoint == 'searchCharts' else 60):
            return self.cache[key][1]
        request = urllib.request.Request(API + endpoint, data=json.dumps(body).encode() if body is not None else None,
                                         headers={'User-Agent': 'SpinShareDecky/0.2.0', 'Content-Type': 'application/json', 'Accept-Encoding': 'gzip'})
        with urllib.request.urlopen(request, timeout=30, context=tls_context()) as response:
            raw = response.read(32 * 1024 * 1024 + 1)
            if len(raw) > 32 * 1024 * 1024:
                raise ValueError('Search response is too large. Narrow your search.')
            if response.headers.get('Content-Encoding', '').lower() == 'gzip':
                with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
                    raw = compressed.read(32 * 1024 * 1024 + 1)
                if len(raw) > 32 * 1024 * 1024:
                    raise ValueError('Search response is too large. Narrow your search.')
            value = json.loads(raw)
        if value.get('status') == 404:
            return []
        if value.get('status') != 200:
            raise ValueError('SpinShare could not complete the request')
        if len(self.cache) >= 4:
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = (time.monotonic(), value['data'])
        return value['data']

    async def browse(self, mode='new', query='', offset=0, options=None):
        if mode not in BROWSE_MODES:
            raise ValueError('Invalid browse mode')
        options = filter_options(options)
        offset = max(0, min(int(offset), 100000))
        query = str(query).strip()[:200]
        filtered = options != filter_options() or bool(query)
        if not filtered and mode in ('new', 'updated', 'hotThisWeek', 'hotThisMonth'):
            # SpinShare calls this parameter offset, but its repository multiplies
            # it by 12: the wire value is a PAGE index, not a record offset.
            data = await asyncio.to_thread(self.api, f'songs/{mode}/{offset // PAGE_SIZE}')
            return {'songs': data, 'hasMore': len(data) == PAGE_SIZE, 'total': None}
        # Prefer a cached broad query, otherwise let SpinShare narrow the payload.
        # Sorting is always applied to the complete result before pagination.
        body = {'searchQuery': query, 'showExplicit': True, 'diffEasy': True, 'diffNormal': True,
                'diffHard': True, 'diffExpert': True, 'diffXD': True, 'diffRatingFrom': 0, 'diffRatingTo': 99}
        broad = self.cache.get('searchCharts' + json.dumps(body))
        if broad and time.monotonic() - broad[0] < 300:
            data = broad[1]
        else:
            for tier, parameter in [('easy', 'diffEasy'), ('normal', 'diffNormal'), ('hard', 'diffHard'),
                                    ('extreme', 'diffExpert'), ('xd', 'diffXD')]:
                body[parameter] = options['difficulty'] in ('all', tier)
            body['diffRatingFrom'] = options['minimum']
            body['diffRatingTo'] = options['maximum']
            data = await asyncio.to_thread(self.api, 'searchCharts', body)
        selected = await asyncio.to_thread(select_songs, data, mode, options)
        return {'songs': selected[offset:offset + PAGE_SIZE], 'hasMore': len(selected) > offset + PAGE_SIZE, 'total': len(selected)}

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
                request = urllib.request.Request(API + f'song/{song_id}/download', headers={'User-Agent': 'SpinShareDecky/0.2.0'})
                with urllib.request.urlopen(request, timeout=60, context=tls_context()) as response:
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
