from datetime import datetime, timezone
import gzip
import unittest
from unittest.mock import patch
from main import Plugin, filter_options, select_songs

NOW = datetime(2026, 9, 13, 12, tzinfo=timezone.utc)


def song(number, rating=10, tier='easy', uploaded='2026-08-01 12:00:00', downloads=1, **extra):
    flag, field = {'easy': ('hasEasyDifficulty', 'easyDifficulty'), 'hard': ('hasHardDifficulty', 'hardDifficulty'),
                   'extreme': ('hasExtremeDifficulty', 'expertDifficulty'), 'xd': ('hasXDDifficulty', 'XDDifficulty')}[tier]
    return {'id': number, 'title': f'Song {number:03}', flag: True, field: rating, 'downloads': downloads,
            'uploadDate': {'date': uploaded, 'timezone': 'UTC'}, **extra}


class FilterTests(unittest.TestCase):
    def select(self, songs, mode='topAllTime', **options):
        return select_songs(songs, mode, filter_options(options), NOW)

    def test_rating_matches_selected_tier_not_another_chart(self):
        mixed = song(1, 5, hasXDDifficulty=True, XDDifficulty=55)
        self.assertEqual(self.select([mixed], difficulty='easy', minimum=40, maximum=60), [])
        self.assertEqual(len(self.select([mixed], difficulty='xd', minimum=40, maximum=60)), 1)

    def test_extreme_uses_spinshare_expert_numeric_field(self):
        self.assertEqual(len(self.select([song(1, 25, 'extreme')], difficulty='extreme', minimum=25, maximum=25)), 1)

    def test_all_difficulties_is_any_matching_chart(self):
        mixed = song(1, 5, hasXDDifficulty=True, XDDifficulty=55)
        self.assertEqual(len(self.select([mixed], minimum=50, maximum=60)), 1)

    def test_missing_rating_not_treated_as_zero(self):
        items = [song(1, None), song(2, 0), song(3, False)]
        self.assertEqual([s['id'] for s in self.select(items, difficulty='easy', maximum=0)], [2])

    def test_unknown_ratings_last_in_both_sort_directions(self):
        items = [song(1, None), song(2, 5), song(3, 50)]
        self.assertEqual([s['id'] for s in self.select(items, sort='difficultyAsc')], [2, 3, 1])
        self.assertEqual([s['id'] for s in self.select(items, sort='difficultyDesc')], [3, 2, 1])

    def test_sort_uses_only_ratings_inside_selected_range(self):
        mixed = song(1, 1, hasHardDifficulty=True, hardDifficulty=20, hasXDDifficulty=True, XDDifficulty=80)
        self.assertEqual([s['id'] for s in self.select([mixed, song(2, 15)], minimum=10, maximum=25, sort='difficultyAsc')], [2, 1])

    def test_calendar_year_not_rolling_year(self):
        items = [song(1, uploaded='2025-12-31 12:00:00', downloads=1000), song(2, downloads=4),
                 song(3, uploaded='2026-01-01 00:00:00', downloads=10), song(4, uploaded='2027-01-01 00:00:00')]
        self.assertEqual([s['id'] for s in self.select(items, 'topYear')], [3, 2])

    def test_alltime_keeps_older_charts_and_sorts_total_downloads(self):
        self.assertEqual([s['id'] for s in self.select([song(1, uploaded='2020-01-01', downloads=100), song(2, downloads=5)])], [1, 2])

    def test_week_and_month_keep_upload_window(self):
        items = [song(1, uploaded='2026-09-12'), song(2, uploaded='2026-09-01'), song(3, uploaded='2026-07-01')]
        self.assertEqual([s['id'] for s in self.select(items, 'hotThisWeek')], [1])
        self.assertEqual([s['id'] for s in self.select(items, 'hotThisMonth')], [1, 2])

    def test_updated_excludes_never_updated(self):
        items = [song(1), song(2, updateDate={'date': '2026-08-01 12:00:00', 'timezone': 'UTC'}),
                 song(3, updateDate={'date': '2026-09-01', 'timezone': 'UTC'})]
        self.assertEqual([s['id'] for s in self.select(items, 'updated')], [3])

    def test_invalid_filters_rejected(self):
        for options in [{'minimum': 50, 'maximum': 10}, {'minimum': -1}, {'maximum': 100}, {'difficulty': 'bogus'}, {'sort': 'bogus'}]:
            with self.assertRaises(ValueError):
                filter_options(options)


class BrowseTests(unittest.IsolatedAsyncioTestCase):
    async def test_feed_offset_is_page_index(self):
        plugin = Plugin()
        with patch.object(plugin, 'api', return_value=[]) as api:
            await plugin.browse('new', '', 12)
            api.assert_called_once_with('songs/new/1')

    async def test_global_sort_before_pagination(self):
        plugin = Plugin()
        items = [song(i, rating=i) for i in range(1, 31)]
        with patch.object(plugin, 'api', return_value=items):
            result = await plugin.browse('topAllTime', '', 12, {'sort': 'difficultyDesc'})
        self.assertEqual([s['id'] for s in result['songs']], list(range(18, 6, -1)))
        self.assertTrue(result['hasMore'])
        self.assertEqual(result['total'], 30)

    async def test_filters_apply_before_pagination_and_count(self):
        plugin = Plugin()
        with patch.object(plugin, 'api', return_value=[song(i, rating=i) for i in range(1, 31)]):
            result = await plugin.browse('new', '', 0, {'minimum': 20, 'maximum': 25})
        self.assertEqual(result['total'], 6)
        self.assertFalse(result['hasMore'])

    async def test_search_is_combined_with_collection(self):
        plugin = Plugin()
        with patch.object(plugin, 'api', return_value=[]) as api:
            result = await plugin.browse('topYear', 'Artist', 0, {'difficulty': 'hard'})
        self.assertEqual(api.call_args.args[1]['searchQuery'], 'Artist')
        self.assertEqual(result['songs'], [])

    async def test_search_larger_than_old_eight_megabyte_limit(self):
        plugin = Plugin()
        payload = b'{"status":200,"data":[' + b' ' * (9 * 1024 * 1024) + b']}'
        with patch('main.urllib.request.urlopen') as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = payload
            result = await plugin.browse('topAllTime')
        self.assertEqual(result['total'], 0)

    async def test_oversize_response_reports_actionable_error(self):
        plugin = Plugin()
        with patch('main.urllib.request.urlopen') as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = b' ' * (32 * 1024 * 1024 + 1)
            with self.assertRaisesRegex(ValueError, 'Narrow your search'):
                await plugin.browse('topAllTime')

    async def test_compressed_response_decoded(self):
        plugin = Plugin()
        with patch('main.urllib.request.urlopen') as urlopen:
            response = urlopen.return_value.__enter__.return_value
            response.headers = {'Content-Encoding': 'gzip'}
            response.read.return_value = gzip.compress(b'{"status":200,"data":[]}')
            result = await plugin.browse('topAllTime')
        self.assertEqual(result['total'], 0)

    async def test_compressed_expansion_is_bounded(self):
        plugin = Plugin()
        with patch('main.urllib.request.urlopen') as urlopen:
            response = urlopen.return_value.__enter__.return_value
            response.headers = {'Content-Encoding': 'gzip'}
            response.read.return_value = gzip.compress(b' ' * (32 * 1024 * 1024 + 1))
            with self.assertRaisesRegex(ValueError, 'Narrow your search'):
                await plugin.browse('topAllTime')

    async def test_difficulty_filters_reduce_server_payload(self):
        plugin = Plugin()
        with patch.object(plugin, 'api', return_value=[]) as api:
            await plugin.browse('new', '', 0, {'difficulty': 'extreme', 'minimum': 20, 'maximum': 30})
        body = api.call_args.args[1]
        self.assertTrue(body['diffExpert'])
        self.assertFalse(body['diffEasy'])
        self.assertFalse(body['diffXD'])
        self.assertEqual((body['diffRatingFrom'], body['diffRatingTo']), (20, 30))
