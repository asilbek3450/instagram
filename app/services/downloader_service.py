"""
Public Instagram Reels/media downloader service.

Data source chain:
  1. RapidAPI (instagram120) — `/api/instagram/reels` lists a profile's reels
     (thumbnails + stats only, no video URLs) and `/api/instagram/links`
     resolves a post/reel URL to a direct CDN .mp4 link.
  2. yt-dlp fallback — if the RapidAPI resolve call fails (quota, outage,
     unsupported media), we extract the direct video URL locally with yt-dlp.

The RapidAPI key never reaches the browser: the frontend only calls our own
/api/downloader/* endpoints. Media bytes are streamed through our proxy so the
browser's `download` attribute works without CORS issues; the proxy only
accepts Instagram CDN hosts (see `is_allowed_media_url`) to prevent SSRF.
"""

import re
import time
from urllib.parse import urlparse

import requests
from flask import current_app

try:
    import yt_dlp
except ImportError:  # optional fallback — feature degrades gracefully
    yt_dlp = None

# Instagram CDN hosts we are willing to proxy media bytes from.
_ALLOWED_HOST_SUFFIXES = ('.cdninstagram.com', '.fbcdn.net')

# Accepts the scheme-less form, an optional `/<username>/` segment
# (instagram.com/<user>/reel/<code>/) and trailing query strings.
_POST_URL_RE = re.compile(
    r'^(?:https?://)?(?:www\.)?instagram\.com/(?!share/)(?:[A-Za-z0-9._]+/)?'
    r'(?:reel|reels|p|tv)/(?P<code>[A-Za-z0-9_-]+)/?'
)

# Mobile-app "Copy link" now often produces /share/… URLs that redirect to
# the canonical post URL; they carry a share token, not a real shortcode.
_SHARE_URL_RE = re.compile(
    r'^(?:https?://)?(?:www\.)?instagram\.com/share/[A-Za-z0-9._/-]+', re.IGNORECASE
)

# Simple in-process TTL cache to save RapidAPI quota on repeat lookups.
_CACHE_TTL = 300  # seconds
_cache = {}


def _cache_get(key):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _CACHE_TTL:
        return hit[1]
    _cache.pop(key, None)
    return None


def _cache_set(key, value):
    if len(_cache) > 256:  # avoid unbounded growth
        _cache.clear()
    _cache[key] = (time.time(), value)


class UpstreamError(ValueError):
    """RapidAPI returned a non-success status. Carries the HTTP status code."""
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _rapidapi_post(path, payload, timeout=30):
    host = current_app.config.get('RAPIDAPI_HOST')
    key = current_app.config.get('RAPIDAPI_KEY')
    if not key:
        raise ValueError("Downloader is not configured (RAPIDAPI_KEY missing).")
    resp = requests.post(
        f"https://{host}{path}",
        json=payload,
        headers={
            'x-rapidapi-key': key,
            'x-rapidapi-host': host,
            'Content-Type': 'application/json',
        },
        timeout=timeout,
    )
    if resp.status_code == 429:
        raise UpstreamError(429, "Rate limit reached, please try again in a minute.")
    if resp.status_code != 200:
        error_msg = f"Upstream API error ({resp.status_code})."
        try:
            # Try to extract a specific error message from the API
            data = resp.json()
            if isinstance(data, dict) and data.get('message'):
                msg_lower = data['message'].lower()
                if 'private' in msg_lower or 'not authorized' in msg_lower:
                    error_msg = "Ushbu profil yopiq (private). Yopiq profillardan yuklab olish imkonsiz."
                else:
                    error_msg = data['message']
        except Exception:
            if resp.status_code == 400:
                error_msg = "Profil yopiq (private) bo'lishi mumkin yoki havola xato. Yopiq profillardan yuklab olish imkonsiz."
        raise UpstreamError(resp.status_code, error_msg)
    return resp.json()


def is_allowed_media_url(url):
    """Only Instagram CDN URLs may pass through the media proxy."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != 'https' or not parsed.hostname:
        return False
    return parsed.hostname.endswith(_ALLOWED_HOST_SUFFIXES)


def parse_post_url(url):
    """Return the shortcode from an instagram.com post/reel URL, or None."""
    m = _POST_URL_RE.match((url or '').strip())
    return m.group('code') if m else None


def _resolve_share_url(url):
    """Follow an instagram.com/share/… redirect to the canonical post URL."""
    url = url.strip()
    if not url.lower().startswith('http'):
        url = 'https://' + url
    resp = requests.get(
        url, allow_redirects=True, timeout=15, stream=True,
        headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                               'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'},
    )
    resp.close()
    return resp.url


# ── Profile feed listings (reels / posts / stories) ─────────────────────────

def _best_thumbnail(media):
    candidates = (media.get('image_versions2') or {}).get('candidates') or []
    if not candidates:
        return None
    # Prefer a mid-size portrait candidate (~480px) — big enough for cards,
    # cheaper than the full-size first entry.
    for c in candidates:
        if c.get('width') == 480:
            return c.get('url')
    return candidates[0].get('url')


def _best_image(media):
    """Full-size image URL — candidates come largest-first."""
    candidates = (media.get('image_versions2') or {}).get('candidates') or []
    return candidates[0].get('url') if candidates else None


def _video_url(media):
    video_versions = media.get('video_versions') or []
    if video_versions and isinstance(video_versions, list):
        return (video_versions[0] or {}).get('url')
    return None


def _normalize_username(username):
    # Accept "@user", "@@user", "@ user", " @User " … — strip any leading
    # @/whitespace mix so the upstream API always gets a bare username.
    return re.sub(r'^[@\s]+', '', (username or '')).strip().lower()


def _build_item(media, url_prefix='p', force_video=False):
    """
    Build a downloader item from an upstream media node.
    Types: 'video' | 'image' | 'carousel' (upstream media_type 2 / 1 / 8).
    `force_video` is used for the reels feed, where every item is a video
    even when the listing carries no video_versions (resolved lazily).
    """
    code = media.get('code')
    caption = media.get('caption')
    caption_text = caption.get('text') if isinstance(caption, dict) else None
    video_url = _video_url(media)
    carousel = media.get('carousel_media')
    media_type = media.get('media_type')

    if not force_video and isinstance(carousel, list) and carousel:
        item_type = 'carousel'
    elif force_video or media_type == 2 or video_url:
        item_type = 'video'
    else:
        item_type = 'image'

    item = {
        'id': media.get('pk'),
        'code': code,
        'type': item_type,
        'post_url': f"https://www.instagram.com/{url_prefix}/{code}/",
        'thumbnail': _best_thumbnail(media),
        'caption': (caption_text or '')[:180] or None,
        'play_count': media.get('play_count') or 0,
        'like_count': media.get('like_count') or 0,
        'comment_count': media.get('comment_count') or 0,
        'counts_hidden': bool(media.get('like_and_view_counts_disabled')),
        'width': media.get('original_width'),
        'height': media.get('original_height'),
    }
    if item_type == 'video':
        item['video_url'] = video_url
    elif item_type == 'image':
        item['image_url'] = _best_image(media)
    else:
        item['children'] = [{
            'type': 'video' if _video_url(child) else 'image',
            'video_url': _video_url(child),
            'image_url': None if _video_url(child) else _best_image(child),
            'thumbnail': _best_thumbnail(child),
        } for child in carousel]
    return item


def _fetch_feed(kind, username, max_id=''):
    """Shared reels/posts listing: {'items': […], 'next_max_id', 'has_more'}."""
    data = _rapidapi_post(f'/api/instagram/{kind}',
                          {'username': username, 'maxId': max_id or ''})
    result = data.get('result') or {}
    items = []
    for edge in result.get('edges') or []:
        node = edge.get('node') or {}
        # The upstream API returns two shapes: fields nested under
        # `node.media`, or flattened directly on `node`. Support both.
        media = node.get('media') or node
        if not media.get('code'):
            continue
        items.append(_build_item(
            media,
            url_prefix='reel' if kind == 'reels' else 'p',
            force_video=(kind == 'reels'),
        ))
    page_info = result.get('page_info') or {}
    return {
        'username': username,
        'items': items,
        'next_max_id': page_info.get('end_cursor') or None,
        'has_more': bool(page_info.get('has_next_page')),
    }


_NO_MEDIA_MSG = (
    "No {kind} found for this profile. It may be private, misspelled "
    "or temporarily unavailable. (Profil yopiq yoki mavjud emas.)"
)


def fetch_reels(username, max_id=''):
    """
    Return {'items': [...], 'next_max_id': str|None, 'has_more': bool}
    for a public profile's reels. Raises ValueError with a friendly message.
    """
    username = _normalize_username(username)
    if not username:
        raise ValueError("Username is required.")

    cache_key = ('reels', username, max_id)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        payload = _fetch_feed('reels', username, max_id)
    except UpstreamError as e:
        if e.status == 429:
            raise
        # The upstream /reels listing answers 500 "link not found" for some
        # profiles even though they exist — their video posts still come
        # through /posts, so fall back and keep only the videos.
        try:
            posts = fetch_posts(username, max_id)
        except ValueError:
            raise ValueError(_NO_MEDIA_MSG.format(kind='reels')) from e
        payload = dict(posts)
        payload['items'] = [i for i in posts['items'] if i['type'] == 'video']
        payload['source'] = 'posts'

    if not payload['items'] and not max_id:
        raise ValueError(
            "No reels found — this profile looks private or empty. "
            "(Profil yopiq yoki bo'sh. Yopiq profillardan yuklab olish imkonsiz.)"
        )
    _cache_set(cache_key, payload)
    return payload


def fetch_posts(username, max_id=''):
    """Profile's post feed — images, videos and carousels."""
    username = _normalize_username(username)
    if not username:
        raise ValueError("Username is required.")

    cache_key = ('posts', username, max_id)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        payload = _fetch_feed('posts', username, max_id)
    except UpstreamError as e:
        if e.status == 429:
            raise
        raise ValueError(_NO_MEDIA_MSG.format(kind='posts')) from e

    if not payload['items'] and not max_id:
        raise ValueError(
            "No posts found — this profile looks private or empty. "
            "(Profil yopiq yoki bo'sh. Yopiq profillardan yuklab olish imkonsiz.)"
        )
    _cache_set(cache_key, payload)
    return payload


def fetch_stories(username):
    """
    Profile's active stories (last 24h). Empty list is a normal result —
    most profiles simply have no story right now.
    """
    username = _normalize_username(username)
    if not username:
        raise ValueError("Username is required.")

    cache_key = ('stories', username)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        data = _rapidapi_post('/api/instagram/stories', {'username': username})
    except UpstreamError as e:
        if e.status == 429:
            raise
        raise ValueError(_NO_MEDIA_MSG.format(kind='stories')) from e

    items = []
    for story in data.get('result') or []:
        if not isinstance(story, dict) or not story.get('pk'):
            continue
        video_url = _video_url(story)
        items.append({
            'id': story.get('pk'),
            'code': None,
            'type': 'video' if video_url else 'image',
            'video_url': video_url,
            'image_url': None if video_url else _best_image(story),
            'thumbnail': _best_thumbnail(story),
            'taken_at': story.get('taken_at'),
            'width': story.get('original_width'),
            'height': story.get('original_height'),
        })

    payload = {'username': username, 'items': items,
               'next_max_id': None, 'has_more': False}
    _cache_set(cache_key, payload)
    return payload


# ── Download link resolution ─────────────────────────────────────────────────

def _quality_rank(u):
    """Numeric sort key for an upstream `urls` entry — `quality` may be an
    int (720) or a string ('720p'/'HD'); never compare raw values."""
    q = u.get('quality')
    if isinstance(q, (int, float)):
        return q
    m = re.search(r'\d+', str(q or ''))
    return int(m.group()) if m else 0


def _resolve_via_rapidapi(post_url):
    data = _rapidapi_post('/api/instagram/links', {'url': post_url})
    # Response shape: [{"urls": [{url, name, subName, extension, quality}],
    #                   "meta": {title, likeCount, commentCount, username, …},
    #                   "pictureUrl": …}]
    entries = data if isinstance(data, list) else [data]
    best = best_entry = None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for u in entry.get('urls') or []:
            if not u.get('url'):
                continue
            if best is None or _quality_rank(u) > _quality_rank(best):
                best, best_entry = u, entry
    if not best:
        raise ValueError("No downloadable media in API response.")
    meta = best_entry.get('meta') or {}
    return {
        'video_url': best['url'],
        'extension': best.get('extension') or 'mp4',
        'quality': best.get('subName') or '',
        'title': meta.get('title') or '',
        'thumbnail': (best_entry.get('pictureUrl')
                      or meta.get('thumbnail') or meta.get('image') or ''),
        'like_count': meta.get('likeCount'),
        'comment_count': meta.get('commentCount'),
        'author': meta.get('username') or '',
        'source': 'api',
    }


def _resolve_via_ytdlp(post_url):
    """Local fallback: extract the direct media URL with yt-dlp (no download)."""
    if yt_dlp is None:
        raise ValueError("yt-dlp is not installed.")
    # Use format: 'b' to get the best single file with both video and audio
    # Also bypass YouTube bot detection by faking mobile clients
    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'format': 'b',
        'extractor_args': {'youtube': {'player_client': ['ios', 'android']}}
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(post_url, download=False)
        
    url = info.get('url')
    if not url:
        raise ValueError("yt-dlp could not extract a direct media URL.")
        
    return {
        'video_url': url,
        'extension': info.get('ext') or 'mp4',
        'quality': f"{info.get('height')}p" if info.get('height') else 'HD',
        'title': info.get('title') or '',
        'thumbnail': info.get('thumbnail') or '',
        'like_count': info.get('like_count'),
        'comment_count': info.get('comment_count'),
        'author': info.get('uploader') or '',
        'source': 'yt-dlp',
    }


def resolve_download(post_url):
    """
    Resolve an instagram.com post/reel URL, TikTok or YouTube URL to a direct CDN media URL.
    Tries RapidAPI first for Instagram, falls back to yt-dlp per requirements.
    For TikTok and YouTube, goes straight to yt-dlp.
    """
    url_lower = post_url.lower()
    is_tiktok = 'tiktok.com' in url_lower
    is_youtube = 'youtube.com' in url_lower or 'youtu.be' in url_lower
    
    if is_tiktok or is_youtube:
        # Bypass Instagram logic for these platforms
        try:
            result = _resolve_via_ytdlp(post_url)
            # Use a dummy code for cache/filename
            code = "tt" if is_tiktok else "yt"
            result['code'] = code
            result['filename'] = f"{'tiktok' if is_tiktok else 'youtube'}_video.{result['extension']}"
            return result
        except Exception as e:
            print(f"[Downloader] yt-dlp failed for {post_url}: {e}")
            raise ValueError("Ushbu mediani yuklab bo'lmadi. Havola xato yoki video o'chirilgan bo'lishi mumkin.")
            
    # Original Instagram logic
    code = parse_post_url(post_url)
    if not code and _SHARE_URL_RE.match((post_url or '').strip()):
        try:
            code = parse_post_url(_resolve_share_url(post_url))
        except requests.RequestException:
            code = None
    if not code:
        raise ValueError("Instagram, TikTok yoki YouTube havolasini kiriting.")
    canonical = f"https://www.instagram.com/reel/{code}/"

    cache_key = ('resolve', code)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        result = _resolve_via_rapidapi(canonical)
    except Exception as api_exc:
        print(f"[Downloader] RapidAPI resolve failed ({api_exc}); trying yt-dlp fallback")
        try:
            result = _resolve_via_ytdlp(canonical)
        except Exception as ytdlp_exc:
            print(f"[Downloader] yt-dlp fallback failed: {ytdlp_exc}")
            raise ValueError(
                "Ushbu mediani yuklab bo'lmadi. U o'chirilgan yoki profil yopiq (private) bo'lishi mumkin. Yopiq profillardan yuklab olish imkonsiz."
            ) from ytdlp_exc

    result['code'] = code
    result['filename'] = f"instagram_{code}.{result['extension']}"
    _cache_set(cache_key, result)
    return result
