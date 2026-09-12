import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from main import Library, Plugin, SUFFIX


def archive(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as bundle:
        for name, data in files.items():
            bundle.writestr(name, data)
    output.seek(0)
    return output


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'Custom'
        self.library = Library(self.root)
        self.song = {'id': 1, 'title': 'Test'}

    def tearDown(self):
        self.temp.cleanup()

    def install(self, files=None, song=None):
        return self.library.install(song or self.song, archive(files or {'track.srtb': '{}', 'AudioClips/music.ogg': 'audio', 'AlbumArt/cover.png': 'art'}))

    def test_install_layout_and_delete(self):
        self.install({'backup/track.srtb': '{}', 'backup/AudioClips/music.ogg': 'audio', 'backup/AlbumArt/cover.png': 'art'})
        self.assertEqual((self.root / 'AudioClips/music.ogg').read_text(), 'audio')
        self.assertEqual(len(self.library.listing()), 1)
        self.library.delete('1')
        self.assertFalse((self.root / 'track.srtb').exists())
        self.assertFalse((self.root / 'AudioClips/music.ogg').exists())

    def test_traversal_rejected_without_partial_install(self):
        with self.assertRaises(ValueError):
            self.install({'track.srtb': '{}', '../escaped.srtb': 'bad'})
        self.assertFalse((self.root / 'track.srtb').exists())
        self.assertFalse((self.root.parent / 'escaped.srtb').exists())

    def test_conflict_does_not_overwrite(self):
        self.root.mkdir()
        (self.root / 'track.srtb').write_text('original')
        with self.assertRaises(ValueError):
            self.install()
        self.assertEqual((self.root / 'track.srtb').read_text(), 'original')
        self.assertFalse(self.library.db.exists())

    def test_shared_audio_survives_until_last_song(self):
        self.install()
        self.install({'other.srtb': 'other', 'AudioClips/music.ogg': 'audio'}, {'id': 2, 'title': 'Other'})
        self.library.delete('1')
        self.assertTrue((self.root / 'AudioClips/music.ogg').exists())
        self.library.delete('2')
        self.assertFalse((self.root / 'AudioClips/music.ogg').exists())

    def test_modified_files_preserved(self):
        self.install()
        (self.root / 'track.srtb').write_text('edited')
        self.library.delete('1')
        self.assertEqual((self.root / 'track.srtb').read_text(), 'edited')
        self.assertTrue((self.root / 'AudioClips/music.ogg').exists())

    def test_preexisting_identical_files_preserved(self):
        self.root.mkdir()
        (self.root / 'track.srtb').write_text('{}')
        self.install()
        self.library.delete('1')
        self.assertTrue((self.root / 'track.srtb').exists())

    def test_unknown_chart_preserves_assets(self):
        self.install()
        (self.root / 'unknown.srtb').write_text('unknown')
        self.library.delete('1')
        self.assertTrue((self.root / 'AudioClips/music.ogg').exists())
        self.library.delete('local:unknown.srtb')
        self.assertFalse((self.root / 'unknown.srtb').exists())

    def test_symlink_rejected(self):
        self.root.mkdir()
        outside = self.root.parent / 'outside'
        outside.mkdir()
        (self.root / 'AudioClips').symlink_to(outside)
        with self.assertRaises(ValueError):
            self.install()
        self.assertEqual(list(outside.iterdir()), [])

    def test_install_rolls_back_failed_manifest_write(self):
        with patch('main.atomic_json', side_effect=OSError('full disk')):
            with self.assertRaises(OSError):
                self.install()
        self.assertFalse((self.root / 'track.srtb').exists())

    def test_delete_rolls_back_failed_manifest_write(self):
        self.install()
        with patch('main.atomic_json', side_effect=OSError('full disk')):
            with self.assertRaises(OSError):
                self.library.delete('1')
        self.assertTrue((self.root / 'track.srtb').exists())
        self.assertEqual(len(self.library.records()), 1)

    def test_missing_files_reported(self):
        self.install()
        (self.root / 'track.srtb').unlink()
        self.assertTrue(self.library.listing()[0]['missing'])

    def test_no_chart_rejected(self):
        with self.assertRaises(ValueError):
            self.install({'AudioClips/music.ogg': 'audio'})

    def test_steam_sd_library_detection(self):
        plugin = Plugin()
        plugin.home = self.root.parent / 'home'
        steam = plugin.home / '.local/share/Steam/steamapps'
        steam.mkdir(parents=True)
        sd = self.root.parent / 'SD Card'
        (sd / SUFFIX.parent).mkdir(parents=True)
        (steam / 'libraryfolders.vdf').write_text('"libraryfolders" { "1" { "path" "' + str(sd) + '" } }')
        self.assertEqual(plugin.candidates(), [str(sd / SUFFIX)])

if __name__ == '__main__':
    unittest.main()
