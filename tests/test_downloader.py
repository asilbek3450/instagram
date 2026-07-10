"""
Tests for the public Reels/media downloader (no-auth feature).

RapidAPI calls are mocked with representative payloads; the media proxy is
tested against its SSRF host allowlist.
"""
import unittest
from unittest.mock import patch
from urllib.parse import unquote

from app import create_app, db
from app.services import downloader_service


def _fake_reels_payload():
    return {
        "result": {
            "edges": [
                {"node": {"media": {
                    "pk": "111", "code": "ABC123",
                    "image_versions2": {"candidates": [
                        {"height": 1136, "width": 640, "url": "https://scontent.cdninstagram.com/big.jpg"},
                        {"height": 852, "width": 480, "url": "https://scontent.cdninstagram.com/mid.jpg"},
                    ]},
                    "play_count": 1500, "like_count": 42, "comment_count": 7,
                    "like_and_view_counts_disabled": False,
                    "original_width": 540, "original_height": 960,
                }}},
            ],
            "page_info": {"end_cursor": "CURSOR_1", "has_next_page": True},
        }
    }


def _fake_reels_payload_flat_with_video():
    """Alternative upstream shape: fields flat on `node` + video_versions."""
    return {
        "result": {
            "edges": [
                {"node": {
                    "pk": "222", "code": "VID456",
                    "caption": {"text": "Senior vs junior \U0001f512 #dev"},
                    "video_versions": [
                        {"width": 720, "height": 1280,
                         "url": "https://instagram.fsof9-1.fna.fbcdn.net/o1/v/reel.mp4?x=1"},
                    ],
                    "image_versions2": {"candidates": [
                        {"height": 1136, "width": 640, "url": "https://scontent.cdninstagram.com/v.jpg"},
                    ]},
                    "play_count": 900, "like_count": 10, "comment_count": 2,
                }},
            ],
            "page_info": {"end_cursor": None, "has_next_page": False},
        }
    }


def _fake_posts_payload():
    """Post feed with one image, one carousel (image+video) and one video."""
    return {
        "result": {
            "edges": [
                {"node": {"media": {
                    "pk": "301", "code": "IMG1", "media_type": 1,
                    "image_versions2": {"candidates": [
                        {"height": 1350, "width": 1080, "url": "https://scontent.cdninstagram.com/img_full.jpg"},
                        {"height": 600, "width": 480, "url": "https://scontent.cdninstagram.com/img_mid.jpg"},
                    ]},
                    "like_count": 5, "comment_count": 1,
                }}},
                {"node": {"media": {
                    "pk": "302", "code": "CAR1", "media_type": 8,
                    "image_versions2": {"candidates": [
                        {"height": 1080, "width": 1080, "url": "https://scontent.cdninstagram.com/car_cover.jpg"},
                    ]},
                    "carousel_media": [
                        {"media_type": 1, "image_versions2": {"candidates": [
                            {"height": 1080, "width": 1080, "url": "https://scontent.cdninstagram.com/car_1.jpg"}]}},
                        {"media_type": 2,
                         "video_versions": [{"url": "https://scontent.cdninstagram.com/car_2.mp4"}],
                         "image_versions2": {"candidates": [
                             {"height": 1080, "width": 1080, "url": "https://scontent.cdninstagram.com/car_2_thumb.jpg"}]}},
                    ],
                    "like_count": 9, "comment_count": 2,
                }}},
                {"node": {"media": {
                    "pk": "303", "code": "VID1", "media_type": 2,
                    "video_versions": [{"url": "https://scontent.cdninstagram.com/post_vid.mp4"}],
                    "image_versions2": {"candidates": [
                        {"height": 1080, "width": 1080, "url": "https://scontent.cdninstagram.com/vid_thumb.jpg"}]},
                    "play_count": 100, "like_count": 3, "comment_count": 0,
                }}},
            ],
            "page_info": {"end_cursor": "P_CURSOR", "has_next_page": True},
        }
    }


def _fake_stories_payload():
    return {
        "result": [
            {"pk": "9001", "taken_at": 1783600000,
             "video_versions": [{"url": "https://scontent.cdninstagram.com/story_v.mp4"}],
             "image_versions2": {"candidates": [
                 {"height": 1920, "width": 1080, "url": "https://scontent.cdninstagram.com/story_v_thumb.jpg"}]}},
            {"pk": "9002", "taken_at": 1783600100,
             "image_versions2": {"candidates": [
                 {"height": 1920, "width": 1080, "url": "https://scontent.cdninstagram.com/story_img.jpg"}]}},
        ]
    }


def _fake_links_payload():
    return [{
        "urls": [
            {"url": "https://scontent.cdninstagram.com/video_low.mp4",
             "name": "MP4", "subName": "480p", "extension": "mp4", "quality": 480},
            {"url": "https://scontent.cdninstagram.com/video.mp4",
             "name": "MP4", "subName": "720p", "extension": "mp4", "quality": 720},
        ],
        "meta": {"title": "Test reel title", "likeCount": 12, "commentCount": 3,
                 "username": "author1", "shortcode": "XYZ789"},
        "pictureUrl": "https://scontent.cdninstagram.com/thumb.jpg",
    }]


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


class DownloaderServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('config.Config')
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['RAPIDAPI_KEY'] = 'test-key'
        self.client = self.app.test_client()
        downloader_service._cache.clear()
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    # ── URL parsing ──────────────────────────────────────────────────────
    def test_parse_post_url(self):
        self.assertEqual(downloader_service.parse_post_url(
            'https://www.instagram.com/reel/DWv5FvBDaud/'), 'DWv5FvBDaud')
        self.assertEqual(downloader_service.parse_post_url(
            'https://instagram.com/p/ABC_12-3'), 'ABC_12-3')
        # Query strings (share links copied from the app/web carry utm params)
        self.assertEqual(downloader_service.parse_post_url(
            'https://www.instagram.com/reel/DaiLJeEthr2/?utm_source=ig_web_copy_link&igsh=x'),
            'DaiLJeEthr2')
        # Scheme-less paste and username-segment post URLs
        self.assertEqual(downloader_service.parse_post_url(
            'www.instagram.com/reel/DWv5FvBDaud/'), 'DWv5FvBDaud')
        self.assertEqual(downloader_service.parse_post_url(
            'https://www.instagram.com/someuser/reel/DWv5FvBDaud/'), 'DWv5FvBDaud')
        # /share/ tokens are not shortcodes — resolved separately via redirect
        self.assertIsNone(downloader_service.parse_post_url(
            'https://www.instagram.com/share/reel/_a8DqXfjK/'))
        self.assertIsNone(downloader_service.parse_post_url('https://evil.com/reel/X/'))
        self.assertIsNone(downloader_service.parse_post_url('not a url'))

    @patch('app.services.downloader_service.requests.post',
           return_value=FakeResp(_fake_links_payload()))
    @patch('app.services.downloader_service._resolve_share_url',
           return_value='https://www.instagram.com/reel/XYZ789/?igsh=t')
    def test_resolve_follows_share_redirect(self, mock_share, mock_post):
        res = self.client.post('/api/downloader/resolve',
                               json={'url': 'https://www.instagram.com/share/reel/_a8DqXfjK/'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['code'], 'XYZ789')
        mock_share.assert_called_once()

    def test_quality_rank_handles_string_quality(self):
        rank = downloader_service._quality_rank
        self.assertEqual(rank({'quality': 720}), 720)
        self.assertEqual(rank({'quality': '1080p'}), 1080)
        self.assertEqual(rank({'quality': 'HD'}), 0)
        self.assertEqual(rank({}), 0)

    def test_media_url_allowlist(self):
        ok = downloader_service.is_allowed_media_url
        self.assertTrue(ok('https://scontent.cdninstagram.com/v/video.mp4'))
        self.assertTrue(ok('https://instagram.facc5-2.fna.fbcdn.net/v/img.jpg'))
        self.assertFalse(ok('https://evil.com/video.mp4'))
        self.assertFalse(ok('http://scontent.cdninstagram.com/v/video.mp4'))  # not https
        self.assertFalse(ok('https://cdninstagram.com.evil.com/x.mp4'))

    # ── Reels listing ────────────────────────────────────────────────────
    @patch('app.services.downloader_service.requests.post',
           return_value=FakeResp(_fake_reels_payload()))
    def test_reels_endpoint(self, mock_post):
        res = self.client.post('/api/downloader/reels', json={'username': '@TestUser'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['username'], 'testuser')
        self.assertEqual(len(data['items']), 1)
        item = data['items'][0]
        self.assertEqual(item['code'], 'ABC123')
        self.assertEqual(item['post_url'], 'https://www.instagram.com/reel/ABC123/')
        # Prefers the ~480px thumbnail candidate
        self.assertEqual(item['thumbnail'], 'https://scontent.cdninstagram.com/mid.jpg')
        self.assertEqual(item['play_count'], 1500)
        self.assertEqual(data['next_max_id'], 'CURSOR_1')
        self.assertTrue(data['has_more'])
        # No video_versions in this payload → no ready download link,
        # and the (absent) raw URL must not leak either.
        self.assertNotIn('download_url', item)
        self.assertNotIn('video_url', item)

    @patch('app.services.downloader_service.requests.post',
           return_value=FakeResp(_fake_reels_payload_flat_with_video()))
    def test_reels_flat_shape_with_video_versions(self, mock_post):
        """Upstream sometimes flattens fields onto `node` and includes
        video_versions — the item must then carry a proxied download_url."""
        res = self.client.post('/api/downloader/reels', json={'username': 'flatshape'})
        self.assertEqual(res.status_code, 200)
        item = res.get_json()['items'][0]
        self.assertEqual(item['code'], 'VID456')
        self.assertIn('Senior vs junior', item['caption'])
        self.assertIn('/api/downloader/media?url=', item['download_url'])
        self.assertIn('instagram_VID456.mp4', item['download_url'])
        self.assertNotIn('video_url', item)  # raw URL replaced by proxy link

    @patch('app.services.downloader_service.requests.post',
           return_value=FakeResp({"result": {"edges": [], "page_info": {}}}))
    def test_reels_empty_profile_is_friendly_error(self, mock_post):
        res = self.client.post('/api/downloader/reels', json={'username': 'ghost'})
        self.assertEqual(res.status_code, 400)
        self.assertIn('No reels found', res.get_json()['error'])

    def test_reels_falls_back_to_posts_when_upstream_flaky(self):
        """Some profiles 500 on /reels but list fine via /posts — the reels
        tab must then show that profile's video posts instead of an error."""
        def fake_post(url, **kwargs):
            if url.endswith('/api/instagram/reels'):
                return FakeResp({"success": False,
                                 "message": "The download link not found."}, status=500)
            return FakeResp(_fake_posts_payload())

        with patch('app.services.downloader_service.requests.post', side_effect=fake_post):
            res = self.client.post('/api/downloader/reels', json={'username': 'flaky.profile'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        # Only the video post survives the filter
        self.assertEqual([i['code'] for i in data['items']], ['VID1'])
        self.assertEqual(data['source'], 'posts')

    def test_reels_upstream_500_and_no_posts_is_friendly_error(self):
        with patch('app.services.downloader_service.requests.post',
                   return_value=FakeResp({"message": "The download link not found."}, status=500)):
            res = self.client.post('/api/downloader/reels', json={'username': 'gone.profile'})
        self.assertEqual(res.status_code, 400)
        self.assertIn('No reels found', res.get_json()['error'])
        self.assertNotIn('download link', res.get_json()['error'])

    # ── Posts listing ────────────────────────────────────────────────────
    @patch('app.services.downloader_service.requests.post',
           return_value=FakeResp(_fake_posts_payload()))
    def test_posts_endpoint_types_and_download_urls(self, mock_post):
        res = self.client.post('/api/downloader/posts', json={'username': 'someuser'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        img, car, vid = data['items']

        self.assertEqual(img['type'], 'image')
        self.assertIn('instagram_IMG1.jpg', img['download_url'])
        self.assertIn('img_full.jpg', unquote(img['download_url']))
        self.assertNotIn('image_url', img)

        self.assertEqual(car['type'], 'carousel')
        self.assertEqual([c['type'] for c in car['children']], ['image', 'video'])
        self.assertIn('instagram_CAR1_1.jpg', car['children'][0]['download_url'])
        self.assertIn('instagram_CAR1_2.mp4', car['children'][1]['download_url'])

        self.assertEqual(vid['type'], 'video')
        self.assertIn('instagram_VID1.mp4', vid['download_url'])
        self.assertEqual(data['next_max_id'], 'P_CURSOR')

    # ── Stories listing ──────────────────────────────────────────────────
    @patch('app.services.downloader_service.requests.post',
           return_value=FakeResp(_fake_stories_payload()))
    def test_stories_endpoint(self, mock_post):
        res = self.client.post('/api/downloader/stories', json={'username': '@someuser'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        video, image = data['items']
        self.assertEqual(video['type'], 'video')
        self.assertIn('instagram_9001.mp4', video['download_url'])
        self.assertEqual(image['type'], 'image')
        self.assertIn('instagram_9002.jpg', image['download_url'])
        self.assertFalse(data['has_more'])

    @patch('app.services.downloader_service.requests.post',
           return_value=FakeResp({"result": []}))
    def test_stories_empty_is_ok_not_error(self, mock_post):
        """No active stories is a normal state, not a 400."""
        res = self.client.post('/api/downloader/stories', json={'username': 'quietuser'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['items'], [])

    def test_reels_requires_username(self):
        res = self.client.post('/api/downloader/reels', json={})
        self.assertEqual(res.status_code, 400)
        # @-only / whitespace-only input is still "no username"
        res = self.client.post('/api/downloader/reels', json={'username': '@ '})
        self.assertEqual(res.status_code, 400)

    @patch('app.services.downloader_service.requests.post',
           return_value=FakeResp(_fake_reels_payload()))
    def test_reels_username_normalization(self, mock_post):
        """'@user', '@@user', '@ User ' must all resolve to the same profile."""
        for variant in ['@testuser', '@@testuser', ' @ TestUser ', 'testuser']:
            downloader_service._cache.clear()
            res = self.client.post('/api/downloader/reels', json={'username': variant})
            self.assertEqual(res.status_code, 200, variant)
            self.assertEqual(res.get_json()['username'], 'testuser', variant)
            sent = mock_post.call_args.kwargs['json']['username']
            self.assertEqual(sent, 'testuser', variant)

    # ── Resolve (download link) ──────────────────────────────────────────
    @patch('app.services.downloader_service.requests.post',
           return_value=FakeResp(_fake_links_payload()))
    def test_resolve_picks_best_quality_and_proxies(self, mock_post):
        res = self.client.post('/api/downloader/resolve',
                               json={'url': 'https://www.instagram.com/reel/XYZ789/'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['proxied'])
        self.assertIn('/api/downloader/media?url=', data['download_url'])
        self.assertIn('video.mp4', data['download_url'])       # 720p variant won
        self.assertEqual(data['filename'], 'instagram_XYZ789.mp4')
        self.assertEqual(data['title'], 'Test reel title')
        # The frontend builds the result card from these:
        self.assertEqual(data['code'], 'XYZ789')
        self.assertEqual(data['thumbnail'], 'https://scontent.cdninstagram.com/thumb.jpg')
        self.assertEqual(data['like_count'], 12)
        self.assertEqual(data['comment_count'], 3)

    def test_resolve_rejects_bad_url(self):
        res = self.client.post('/api/downloader/resolve', json={'url': 'https://evil.com/reel/X/'})
        self.assertEqual(res.status_code, 400)

    @patch('app.services.downloader_service._resolve_via_ytdlp',
           return_value={'video_url': 'https://scontent.cdninstagram.com/yt.mp4',
                         'extension': 'mp4', 'quality': '720p',
                         'title': 'From fallback', 'source': 'yt-dlp'})
    @patch('app.services.downloader_service._resolve_via_rapidapi',
           side_effect=ValueError('quota exceeded'))
    def test_resolve_falls_back_to_ytdlp(self, mock_api, mock_ytdlp):
        res = self.client.post('/api/downloader/resolve',
                               json={'url': 'https://www.instagram.com/reel/FBACK1/'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['proxied'])
        self.assertEqual(data['title'], 'From fallback')
        mock_ytdlp.assert_called_once()

    # ── Media proxy (SSRF guard) ─────────────────────────────────────────
    def test_media_proxy_rejects_foreign_hosts(self):
        res = self.client.get('/api/downloader/media?url=https://evil.com/v.mp4')
        self.assertEqual(res.status_code, 400)

    def test_media_proxy_rejects_missing_url(self):
        res = self.client.get('/api/downloader/media')
        self.assertEqual(res.status_code, 400)

    @patch('app.routes.downloader.requests.get')
    def test_media_proxy_streams_allowed_host(self, mock_get):
        upstream = mock_get.return_value
        upstream.status_code = 200
        upstream.headers = {'Content-Type': 'video/mp4', 'Content-Length': '4'}
        upstream.iter_content.return_value = iter([b'DATA'])
        upstream.raise_for_status.return_value = None

        res = self.client.get(
            '/api/downloader/media?url=https://scontent.cdninstagram.com/v.mp4'
            '&filename=instagram_ABC.mp4')
        self.assertEqual(res.status_code, 200)
        self.assertIn('attachment', res.headers['Content-Disposition'])
        self.assertIn('instagram_ABC.mp4', res.headers['Content-Disposition'])
        self.assertEqual(res.data, b'DATA')

    @patch('app.routes.downloader.requests.get')
    def test_media_proxy_forwards_range_requests(self, mock_get):
        """<video> preview sends Range; the proxy must forward it upstream
        and pass the 206/Content-Range back (Safari refuses to play otherwise)."""
        upstream = mock_get.return_value
        upstream.status_code = 206
        upstream.headers = {'Content-Type': 'video/mp4', 'Content-Length': '1024',
                            'Content-Range': 'bytes 0-1023/4096', 'Accept-Ranges': 'bytes'}
        upstream.iter_content.return_value = iter([b'PART'])
        upstream.raise_for_status.return_value = None

        res = self.client.get(
            '/api/downloader/media?url=https://scontent.cdninstagram.com/v.mp4',
            headers={'Range': 'bytes=0-1023'})
        self.assertEqual(res.status_code, 206)
        self.assertEqual(res.headers['Content-Range'], 'bytes 0-1023/4096')
        self.assertEqual(res.headers['Accept-Ranges'], 'bytes')
        self.assertEqual(mock_get.call_args.kwargs['headers'], {'Range': 'bytes=0-1023'})

    # ── Page availability without auth ───────────────────────────────────
    def test_downloader_page_is_public(self):
        res = self.client.get('/downloader')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Reels', res.data)


if __name__ == '__main__':
    unittest.main()
