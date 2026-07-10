"""
Public (no-auth) API for the Reels/media Downloader page:
  POST /api/downloader/reels    — list a profile's reels {username, max_id}
  POST /api/downloader/posts    — list a profile's posts (images/videos/carousels)
  POST /api/downloader/stories  — list a profile's active stories
  POST /api/downloader/resolve  — resolve a post/reel URL to a download link
  GET  /api/downloader/media    — proxy-stream an Instagram CDN file so the
                                  browser can save it (avoids CORS/hotlink
                                  issues with the `download` attribute)
"""
import requests
from flask import Blueprint, Response, jsonify, request, stream_with_context

from app.services import downloader_service

downloader_bp = Blueprint('downloader_api', __name__, url_prefix='/api/downloader')


def _proxy_url(media_url, filename):
    return (
        '/api/downloader/media?url=' + requests.utils.quote(media_url, safe='')
        + '&filename=' + requests.utils.quote(filename)
    )


def _attach_download_urls(item):
    """
    Replace raw CDN URLs on a listing item (and its carousel children) with
    ready-to-use proxied download links. Raw URLs never reach the client;
    anything not on the CDN allowlist is dropped (resolved lazily instead).
    """
    name = item.get('code') or item.get('id') or 'media'

    def link(url, filename):
        if url and downloader_service.is_allowed_media_url(url):
            return _proxy_url(url, filename)
        return None

    video_url = item.pop('video_url', None)
    image_url = item.pop('image_url', None)
    download = (link(video_url, f"instagram_{name}.mp4")
                or link(image_url, f"instagram_{name}.jpg"))
    if download:
        item['download_url'] = download

    for i, child in enumerate(item.get('children') or [], start=1):
        child_video = child.pop('video_url', None)
        child_image = child.pop('image_url', None)
        ext = 'mp4' if child_video else 'jpg'
        download = link(child_video or child_image, f"instagram_{name}_{i}.{ext}")
        if download:
            child['download_url'] = download


def _feed_response(fetch):
    try:
        payload = fetch()
        for item in payload['items']:
            _attach_download_urls(item)
        return jsonify(payload), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except requests.RequestException:
        return jsonify({'error': 'Upstream service unreachable. Try again later.'}), 502


@downloader_bp.route('/reels', methods=['POST'])
def reels():
    data = request.get_json() or {}
    return _feed_response(lambda: downloader_service.fetch_reels(
        data.get('username', ''), data.get('max_id', '') or ''))


@downloader_bp.route('/posts', methods=['POST'])
def posts():
    data = request.get_json() or {}
    return _feed_response(lambda: downloader_service.fetch_posts(
        data.get('username', ''), data.get('max_id', '') or ''))


@downloader_bp.route('/stories', methods=['POST'])
def stories():
    data = request.get_json() or {}
    return _feed_response(lambda: downloader_service.fetch_stories(
        data.get('username', '')))


@downloader_bp.route('/resolve', methods=['POST'])
def resolve():
    data = request.get_json() or {}
    try:
        info = downloader_service.resolve_download(data.get('url', ''))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    payload = {
        'code': info.get('code'),
        'filename': info['filename'],
        'title': info['title'],
        'quality': info['quality'],
        'thumbnail': info.get('thumbnail') or None,
        'like_count': info.get('like_count'),
        'comment_count': info.get('comment_count'),
        'author': info.get('author') or None,
    }
    if downloader_service.is_allowed_media_url(info['video_url']):
        payload['download_url'] = _proxy_url(info['video_url'], info['filename'])
        payload['proxied'] = True
    else:
        # Upstream returned something we refuse to proxy — hand the raw URL
        # to the client as a last resort (opens in a new tab).
        payload['direct_url'] = info['video_url']
        payload['proxied'] = False
    return jsonify(payload), 200


@downloader_bp.route('/media', methods=['GET'])
def media():
    url = request.args.get('url', '')
    filename = request.args.get('filename', 'instagram_media.mp4')
    # Keep the filename header-safe.
    filename = ''.join(c for c in filename if c.isalnum() or c in '._-') or 'media.mp4'

    if not downloader_service.is_allowed_media_url(url):
        return jsonify({'error': 'URL not allowed.'}), 400

    # Forward the browser's Range header so <video> preview works (Safari
    # refuses to play sources that ignore Range) and seeking is possible.
    upstream_headers = {}
    if request.headers.get('Range'):
        upstream_headers['Range'] = request.headers['Range']

    try:
        upstream = requests.get(url, stream=True, timeout=30, headers=upstream_headers)
        upstream.raise_for_status()
    except requests.RequestException:
        return jsonify({'error': 'Media link expired. Please try again.'}), 502

    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"',
        'Content-Type': upstream.headers.get('Content-Type', 'application/octet-stream'),
        'Accept-Ranges': upstream.headers.get('Accept-Ranges', 'bytes'),
    }
    for passthrough in ('Content-Length', 'Content-Range'):
        if upstream.headers.get(passthrough):
            headers[passthrough] = upstream.headers[passthrough]

    return Response(
        stream_with_context(upstream.iter_content(chunk_size=64 * 1024)),
        headers=headers,
        status=upstream.status_code,  # 200, or 206 for range responses
    )
