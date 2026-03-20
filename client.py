import urllib.request
import urllib.parse
import json
import re
import logging
import traceback
from datetime import datetime
import concurrent.futures

import time
import base64
import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_MUSIC_BASE = "https://music.apple.com"
_AMP_API_BASE = "https://amp-api.music.apple.com"
_BROWSE_PATH = "/us/browse"

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
_MINIMAL_HEADERS = {"User-Agent": "Mozilla/5.0"}

logger = logging.getLogger(__name__)


def _load_cors_proxy() -> str:
    """Return cors_proxy from config.json, or empty string if not set."""
    config_path = os.path.join(_BASE_DIR, "config.json")
    try:
        with open(config_path) as f:
            return json.load(f).get("cors_proxy", "") or ""
    except Exception:
        return ""


class AppleMusicClient:
    def __init__(self, user_token=None):
        self.user_token = user_token
        self._cors_proxy = _load_cors_proxy()
        self.bearer_token = self._get_bearer_token()

        self._web_headers = {"User-Agent": _UA}
        if self.user_token:
            self._web_headers["Cookie"] = f"media-user-token={self.user_token}"
        if self.bearer_token:
            self._web_headers["Authorization"] = f"Bearer {self.bearer_token}"

        self._amp_headers = {
            "User-Agent": _UA,
            "Origin": _MUSIC_BASE,
            "Referer": f"{_MUSIC_BASE}/",
        }
        if self.bearer_token:
            self._amp_headers["Authorization"] = f"Bearer {self.bearer_token}"
        if self.user_token:
            self._amp_headers["Music-User-Token"] = self.user_token

    def _get_bearer_token(self):
        token_file = os.path.join(_BASE_DIR, "bearer_token.txt")
        token = None

        # Check if exists and valid
        if os.path.exists(token_file):
            with open(token_file, "r") as f:
                token = f.read().strip()
            if token and not self._is_jwt_expired(token):
                return token

        # Fetch new token
        token = self._fetch_new_bearer_token()
        if token:
            with open(token_file, "w") as f:
                f.write(token)
            return token
        return None

    def _is_jwt_expired(self, token):
        try:
            payload = token.split('.')[1]
            payload += '=' * (-len(payload) % 4)
            decoded = json.loads(base64.b64decode(payload).decode('utf-8'))
            exp = decoded.get('exp', 0)
            return time.time() >= exp
        except Exception:
            return True

    def _apply_proxy(self, url: str) -> str:
        if self._cors_proxy:
            return self._cors_proxy + urllib.parse.quote(url, safe="")
        return url

    def _web_get(self, url: str, headers: dict = None, timeout: int = 10) -> str | None:
        url = self._apply_proxy(url)
        logger.debug("[web] GET %s", url)
        req = urllib.request.Request(url, headers=self._web_headers if headers is None else headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode('utf-8')
        except Exception:
            return None

    def _fetch_new_bearer_token(self):
        try:
            html = self._web_get(_MUSIC_BASE + _BROWSE_PATH, headers=_MINIMAL_HEADERS)
            if not html:
                logger.warning("Failed to fetch Apple Music browse page")
                return None
            m = re.search(r'src="(/assets/index-[^"]+\.js)"', html)
            if not m:
                m = re.search(r'src="(/assets/index-legacy[^"]+\.js)"', html)
            if m:
                js_url = _MUSIC_BASE + m.group(1)
                js_content = self._web_get(js_url, headers=_MINIMAL_HEADERS)
                if not js_content:
                    logger.warning("Failed to fetch Apple Music JS bundle")
                    return None
                tokens = re.findall(r'\"(eyJ[A-Za-z0-9-_]+[=]{0,2}\.[A-Za-z0-9-_]+[=]{0,2}\.[A-Za-z0-9-_.+/=]+)\"', js_content)
                if tokens:
                    return tokens[0]
        except Exception as e:
            logger.warning("Error fetching bearer token: %s", e)
        return None

    def _amp_api_get(self, path: str, params: dict = None) -> dict:
        """GET from amp-api.music.apple.com, returns parsed JSON or {}."""
        query = ('?' + urllib.parse.urlencode(params)) if params else ''
        url = self._apply_proxy(f"{_AMP_API_BASE}{path}{query}")
        req = urllib.request.Request(url, headers=self._amp_headers)
        logger.debug("[amp-api] GET %s", url)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            logger.warning("[amp-api] GET %s failed: %s", url, e)
            return {}

    def get_album_full_info(self, url: str) -> dict:
        """Fetch full album metadata via the catalog API."""
        result = {
            "title": None,
            "artist": None,
            "release_date": None,
            "artwork_url": None,
            "track_count": None,
            "genre": None,
            "description": None,
            "artist_id": None,
            "artist_url": None,
            "tracks": [],
            "audio_formats": None,
        }
        m = re.search(r'music\.apple\.com/([a-z]{2})/album/(?:[^/]+/)?(\d+)', url)
        if not m:
            return result
        storefront, adam_id = m.group(1), m.group(2)

        data = self._amp_api_get(
            f"/v1/catalog/{storefront}/albums/{adam_id}",
            {"include": "tracks,artists", "extend": "extendedAssetUrls"}
        )

        item = (data.get('data') or [{}])[0]
        attrs = item.get('attributes', {})
        rels = item.get('relationships', {})

        result['title'] = attrs.get('name')
        result['artist'] = attrs.get('artistName')
        result['release_date'] = attrs.get('releaseDate')
        result['track_count'] = attrs.get('trackCount')

        art_url = attrs.get('artwork', {}).get('url')
        if art_url:
            result['artwork_url'] = re.sub(r'\{w\}x\{h\}bb\.[a-z]+', '500x500bb.jpg', art_url)

        genre_names = attrs.get('genreNames') or []
        result['genre'] = genre_names[0] if genre_names else None

        result['description'] = (attrs.get('editorialNotes') or {}).get('standard')

        formats = list(attrs.get('audioTraits') or [])
        if attrs.get('isMasteredForItunes'):
            formats.append('adm')
        result['audio_formats'] = formats if formats else None

        artists_data = rels.get('artists', {}).get('data') or []
        if artists_data:
            artist_item = artists_data[0]
            result['artist_id'] = artist_item.get('id')
            result['artist_url'] = (artist_item.get('attributes') or {}).get('url')

        tracks = []
        for t in (rels.get('tracks', {}).get('data') or []):
            tattrs = t.get('attributes') or {}
            title = tattrs.get('name')
            if title:
                tracks.append({
                    'title': title,
                    'track_number': tattrs.get('trackNumber'),
                    'duration_ms': tattrs.get('durationInMillis'),
                })
        result['tracks'] = tracks

        return result


    def get_room_new_releases(self, url, storefront):
        html = self._web_get(url)
        if not html:
            return []

        match = re.search(r'<script type="application/json" id="serialized-server-data">(.*?)</script>', html)
        if not match:
            return []
        data = json.loads(match.group(1))

        content = None
        try:
            if isinstance(data, dict) and 'data' in data:
                content = data['data'][0]['data']
                sections = content.get('sections', [])
            elif isinstance(data, list):
                content = data[0]['data']['data'][0]['data']
                sections = content.get('sections', [])
            else:
                sections = []
        except Exception as e:
            logger.warning("Error extracting sections: %s %s", type(e), e)
            traceback.print_exc()
            return []

        logger.debug("Found %d sections in room.", len(sections))
        if not sections and content is not None and isinstance(content, dict):
            logger.debug("Content keys: %s", list(content.keys()))

        new_releases = []
        for sec in sections:
            title = sec.get('header', '')
            if isinstance(title, dict):
                title = title.get('item', {}).get('titleLink', {}).get('title', str(title))
            elif not title and 'dictionary' in sec and 'title' in sec['dictionary']:
                title = sec['dictionary']['title']

            logger.debug("Checking section: %s", title)

            title_lower = title.lower() if isinstance(title, str) else str(title).lower()
            if any(kw in title_lower for kw in ['new', '新', 'release', 'terbaru', '最新', 'リリース']):
                items = sec.get('items', [])
                for item in items:
                    actual_item = item.get('item', item)

                    # Item fallback
                    if not actual_item: continue

                    title_val, artist_val, url_val, adam_id = None, None, None, None

                    if 'attributes' in actual_item:
                        attrs = actual_item['attributes']
                        title_val = attrs.get('title') or attrs.get('name')
                        artist_val = attrs.get('artistName')
                        url_val = attrs.get('url')
                    else:
                        if actual_item.get('titleLinks'):
                            title_val = actual_item['titleLinks'][0].get('title')

                        if actual_item.get('subtitleLinks'):
                            artist_val = actual_item['subtitleLinks'][0].get('title')

                        desc = actual_item.get('contentDescriptor', {})
                        url_val = desc.get('url')
                        adam_id = desc.get('identifiers', {}).get('storeAdamID')

                    if not adam_id and url_val:
                        adam_m = re.search(r'/(\d+)(?:\?.*)?$', url_val)
                        adam_id = adam_m.group(1) if adam_m else actual_item.get('id')
                        if adam_id and "-" in str(adam_id): adam_id = str(adam_id).split('-')[-1].strip()

                    if title_val and url_val and adam_id:
                        release_info = {
                            'storeAdamID': adam_id,
                            'title': title_val,
                            'artist': artist_val,
                            'url': url_val,
                            'storefronts': [storefront]
                        }
                        new_releases.append(release_info)
                break
        return new_releases

    _VIEW_MAP = {
        "full-albums":        "main-albums",
        "compilation-albums": "compilation-albums",
        "live-albums":        "live-albums",
        "singles":            "singles-eps",
    }

    def get_artist_all_releases(self, url, storefront):
        """Fetch every release listed for an artist via the catalog API (paginated, grouped by type)."""
        m = re.search(r'music\.apple\.com/([a-z]{2})/artist/(?:[^/]+/)?(\d+)', url)
        if not m:
            return []
        sf, artist_id = m.group(1), m.group(2)

        view_keys = list(self._VIEW_MAP.keys())
        params = {
            "views": ",".join(view_keys),
            **{f"limit[{v}]": "100" for v in view_keys},
        }
        data = self._amp_api_get(f"/v1/catalog/{sf}/artists/{artist_id}", params)
        if not data:
            return []

        artist_item = (data.get("data") or [{}])[0]
        views = artist_item.get("views") or {}

        releases = []
        seen = set()

        for view_key, release_type in self._VIEW_MAP.items():
            view_data = views.get(view_key) or {}
            items = view_data.get("data") or []
            next_link = view_data.get("next")

            for item in items:
                adam_id = item.get("id")
                attrs = item.get("attributes", {})
                title_val = attrs.get("name")
                artist_val = attrs.get("artistName")
                item_url = attrs.get("url")
                if adam_id and title_val and adam_id not in seen:
                    seen.add(adam_id)
                    releases.append({
                        "storeAdamID": adam_id,
                        "title": title_val,
                        "artist": artist_val,
                        "url": item_url,
                        "storefronts": [storefront],
                        "release_type": release_type,
                    })

            # Paginate this view independently
            while next_link:
                next_path = next_link.split("?")[0]
                offset_m = re.search(r"offset=(\d+)", next_link)
                page_params = {"limit": "100"}
                if offset_m:
                    page_params["offset"] = offset_m.group(1)
                page_data = self._amp_api_get(next_path, page_params)
                if not page_data:
                    break
                for item in page_data.get("data") or []:
                    adam_id = item.get("id")
                    attrs = item.get("attributes", {})
                    title_val = attrs.get("name")
                    artist_val = attrs.get("artistName")
                    item_url = attrs.get("url")
                    if adam_id and title_val and adam_id not in seen:
                        seen.add(adam_id)
                        releases.append({
                            "storeAdamID": adam_id,
                            "title": title_val,
                            "artist": artist_val,
                            "url": item_url,
                            "storefronts": [storefront],
                            "release_type": release_type,
                        })
                next_link = page_data.get("next")

        return releases

    def get_artist_new_releases(self, url, storefront):
        """Fetch latest releases for an artist via the catalog API (first page only)."""
        m = re.search(r'music\.apple\.com/([a-z]{2})/artist/(?:[^/]+/)?(\d+)', url)
        if not m:
            return []
        sf, artist_id = m.group(1), m.group(2)

        data = self._amp_api_get(
            f"/v1/catalog/{sf}/artists/{artist_id}/albums",
            {"limit": "25"}
        )

        releases = []
        for item in data.get('data', []):
            adam_id = item.get('id')
            attrs = item.get('attributes', {})
            title_val = attrs.get('name')
            artist_val = attrs.get('artistName')
            item_url = attrs.get('url')
            if adam_id and title_val:
                releases.append({
                    'storeAdamID': adam_id,
                    'title': title_val,
                    'artist': artist_val,
                    'url': item_url,
                    'storefronts': [storefront],
                })
        return releases


    def check_storefront_availability(self, adam_id: str, storefronts: list) -> dict:
        """
        Concurrently checks availability of an album across multiple storefronts.
        Returns a dictionary with 'available' and 'unavailable' lists.
        """
        available = []
        unavailable = []

        def _check_sf(sf):
            url = f"{_MUSIC_BASE}/{sf}/album/{adam_id}"
            return sf, self._web_get(url, timeout=5) is not None

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = executor.map(_check_sf, storefronts)

        for sf, is_avail in results:
            if is_avail:
                available.append(sf)
            else:
                unavailable.append(sf)

        return {"available": available, "unavailable": unavailable}
