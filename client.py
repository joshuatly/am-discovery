import base64
import concurrent.futures
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from client_discovery import DiscoveryMixin

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class RateLimitError(Exception):
    """Raised when the Apple Music API returns HTTP 429."""


_MUSIC_BASE = "https://music.apple.com"
_AMP_API_BASE = "https://amp-api.music.apple.com"
_BROWSE_PATH = "/us/browse"

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
_MINIMAL_HEADERS = {"User-Agent": "Mozilla/5.0"}

_VIEW_MAP = {
    "full-albums": "main-albums",
    "compilation-albums": "compilation-albums",
    "live-albums": "live-albums",
    "singles": "singles-eps",
}


logger = logging.getLogger(__name__)


def _load_cors_proxy() -> str:
    """Return cors_proxy from config.json, or empty string if not set."""
    config_path = os.path.join(_BASE_DIR, "config.json")
    try:
        with open(config_path) as f:
            return json.load(f).get("cors_proxy", "") or ""
    except Exception:
        return ""


class AppleMusicClient(DiscoveryMixin):
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
            with open(token_file) as f:
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
            payload = token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            decoded = json.loads(base64.b64decode(payload).decode("utf-8"))
            exp = decoded.get("exp", 0)
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
                return resp.read().decode("utf-8")
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
                tokens = re.findall(
                    r"\"(eyJ[A-Za-z0-9-_]+[=]{0,2}\.[A-Za-z0-9-_]+[=]{0,2}\.[A-Za-z0-9-_.+/=]+)\"",
                    js_content,
                )
                if tokens:
                    return tokens[0]
        except Exception as e:
            logger.warning("Error fetching bearer token: %s", e)
        return None

    def _amp_api_get(self, path: str, params: dict = None) -> dict:
        """GET from amp-api.music.apple.com, returns parsed JSON or {}."""
        query = ("?" + urllib.parse.urlencode(params)) if params else ""
        url = self._apply_proxy(f"{_AMP_API_BASE}{path}{query}")
        req = urllib.request.Request(url, headers=self._amp_headers)
        logger.debug("[amp-api] GET %s", url)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                logger.warning("[amp-api] Rate limited (429): %s", url)
                raise RateLimitError("Apple Music API rate limit exceeded") from e
            logger.warning("[amp-api] GET %s failed: %s", url, e)
            return {}
        except Exception as e:
            logger.warning("[amp-api] GET %s failed: %s", url, e)
            return {}

    def catalog_get_raw(self, path: str, params: dict = None) -> tuple[int, dict | str]:
        """GET from amp-api.music.apple.com and return (status_code, body).

        Unlike _amp_api_get, errors are not swallowed — the HTTP status and
        response body (or error message string) are always returned so callers
        can surface the real Apple Music response.
        """
        query = ("?" + urllib.parse.urlencode(params)) if params else ""
        url = self._apply_proxy(f"{_AMP_API_BASE}{path}{query}")
        req = urllib.request.Request(url, headers=self._amp_headers)
        logger.debug("[amp-api raw] GET %s", url)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode("utf-8"))
            except Exception:
                body = {"error": str(e)}
            return e.code, body
        except Exception as e:
            return 0, {"error": str(e)}

    def get_album_full_info(self, url: str) -> dict:
        """Fetch full album metadata via the catalog API."""
        result = {
            "title": None,
            "artist": None,
            "release_date": None,
            "artwork_url": None,
            "track_count": None,
            "music_video_count": 0,
            "genre": None,
            "description": None,
            "artist_id": None,
            "artist_url": None,
            "tracks": [],
            "audio_formats": None,
            "upc": None,
        }
        m = re.search(r"music\.apple\.com/([a-z]{2})/album/(?:[^/]+/)?(\d+)", url)
        if not m:
            return result
        storefront, adam_id = m.group(1), m.group(2)

        data = self._amp_api_get(
            f"/v1/catalog/{storefront}/albums/{adam_id}",
            {"include": "tracks,artists", "extend": "extendedAssetUrls"},
        )

        item = (data.get("data") or [{}])[0]
        attrs = item.get("attributes", {})
        rels = item.get("relationships", {})

        result["title"] = attrs.get("name")
        result["artist"] = attrs.get("artistName")
        result["release_date"] = attrs.get("releaseDate")
        result["track_count"] = attrs.get("trackCount")

        art_url = attrs.get("artwork", {}).get("url")
        if art_url:
            result["artwork_url"] = re.sub(r"\{w\}x\{h\}bb\.[a-z]+", "500x500bb.jpg", art_url)

        genre_names = attrs.get("genreNames") or []
        result["genre"] = genre_names[0] if genre_names else None

        result["description"] = (attrs.get("editorialNotes") or {}).get("standard")
        result["upc"] = attrs.get("upc")

        formats = list(attrs.get("audioTraits") or [])
        if attrs.get("isMasteredForItunes"):
            formats.append("adm")
        result["audio_formats"] = formats or None

        artists_data = rels.get("artists", {}).get("data") or []
        artists = []
        for a in artists_data:
            attrs = a.get("attributes") or {}
            art_url = attrs.get("artwork", {}).get("url")
            genre_names = attrs.get("genreNames") or []
            artists.append(
                {
                    "id": a.get("id"),
                    "name": attrs.get("name"),
                    "url": attrs.get("url"),
                    "artwork_url": re.sub(r"\{w\}x\{h\}bb\.[a-z]+", "200x200bb.jpg", art_url) if art_url else None,
                    "genre": genre_names[0] if genre_names else None,
                },
            )
        result["artists"] = artists
        if artists:
            result["artist_id"] = artists[0]["id"]
            result["artist_url"] = artists[0]["url"]

        tracks = []
        mv_count = 0
        for t in rels.get("tracks", {}).get("data") or []:
            tattrs = t.get("attributes") or {}
            title = tattrs.get("name")
            if title:
                is_mv = t.get("type") == "music-videos"
                if is_mv:
                    mv_count += 1
                tracks.append(
                    {
                        "title": title,
                        "track_number": tattrs.get("trackNumber"),
                        "duration_ms": tattrs.get("durationInMillis"),
                        "is_music_video": is_mv,
                    },
                )
        result["tracks"] = tracks
        result["music_video_count"] = mv_count

        return result

    def get_artist_all_releases(self, url, storefront):
        """Fetch every release listed for an artist via the catalog API (paginated, grouped by type)."""
        m = re.search(r"music\.apple\.com/([a-z]{2})/artist/(?:[^/]+/)?(\d+)", url)
        if not m:
            return [], {}
        sf, artist_id = m.group(1), m.group(2)

        view_keys = list(_VIEW_MAP.keys())
        params = {
            "views": ",".join(view_keys),
            **{f"limit[{v}]": "100" for v in view_keys},
            "extend": "bornOrFormed,origin,artistBio",
        }
        data = self._amp_api_get(f"/v1/catalog/{sf}/artists/{artist_id}", params)
        if not data:
            return [], {}

        artist_item = (data.get("data") or [{}])[0]
        artist_attrs = artist_item.get("attributes", {})
        views = artist_item.get("views") or {}

        art_url = artist_attrs.get("artwork", {}).get("url", "")
        artist_info = {
            "name": artist_attrs.get("name"),
            "artwork_url": re.sub(r"\{w\}x\{h\}bb\.[a-z]+", "200x200bb.jpg", art_url) if art_url else None,
            "genre": (artist_attrs.get("genreNames") or [None])[0],
            "born_or_formed": artist_attrs.get("bornOrFormed"),
            "origin": artist_attrs.get("origin"),
            "artist_bio": artist_attrs.get("artistBio"),
            "is_group": artist_attrs.get("isGroup"),
        }

        releases = []
        seen = set()

        for view_key, release_type in _VIEW_MAP.items():
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
                    releases.append(
                        {
                            "storeAdamID": adam_id,
                            "title": title_val,
                            "artist": artist_val,
                            "url": item_url,
                            "storefronts": [storefront],
                            "release_type": release_type,
                        },
                    )

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
                        releases.append(
                            {
                                "storeAdamID": adam_id,
                                "title": title_val,
                                "artist": artist_val,
                                "url": item_url,
                                "storefronts": [storefront],
                                "release_type": release_type,
                            },
                        )
                next_link = page_data.get("next")

        return releases, artist_info

    def get_artist_new_releases(self, url, storefront):
        """Fetch latest releases for an artist via the catalog API (first page only)."""
        m = re.search(r"music\.apple\.com/([a-z]{2})/artist/(?:[^/]+/)?(\d+)", url)
        if not m:
            return []
        sf, artist_id = m.group(1), m.group(2)

        data = self._amp_api_get(f"/v1/catalog/{sf}/artists/{artist_id}/albums", {"limit": "25"})

        releases = []
        for item in data.get("data", []):
            adam_id = item.get("id")
            attrs = item.get("attributes", {})
            title_val = attrs.get("name")
            artist_val = attrs.get("artistName")
            item_url = attrs.get("url")
            if adam_id and title_val:
                releases.append(
                    {
                        "storeAdamID": adam_id,
                        "title": title_val,
                        "artist": artist_val,
                        "url": item_url,
                        "storefronts": [storefront],
                    },
                )
        return releases

    def search(
        self,
        term: str,
        storefront: str = "us",
        types: str = "songs,music-videos,albums,playlists,artists",
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Search the Apple Music catalog. Returns the raw API response dict."""
        return self._amp_api_get(
            f"/v1/catalog/{storefront}/search",
            {"term": term, "types": types, "limit": limit, "offset": offset},
        )

    def get_artist_info_only(self, artist_id: str, storefront: str) -> dict:
        """Fetch extended artist attributes without fetching releases."""
        params = {"extend": "bornOrFormed,origin,artistBio"}
        data = self._amp_api_get(f"/v1/catalog/{storefront}/artists/{artist_id}", params)
        if not data:
            return {}
        artist_item = (data.get("data") or [{}])[0]
        artist_attrs = artist_item.get("attributes", {})
        art_url = artist_attrs.get("artwork", {}).get("url", "")
        return {
            "name": artist_attrs.get("name"),
            "artwork_url": re.sub(r"\{w\}x\{h\}bb\.[a-z]+", "200x200bb.jpg", art_url) if art_url else None,
            "genre": (artist_attrs.get("genreNames") or [None])[0],
            "born_or_formed": artist_attrs.get("bornOrFormed"),
            "origin": artist_attrs.get("origin"),
            "artist_bio": artist_attrs.get("artistBio"),
            "is_group": artist_attrs.get("isGroup"),
        }

    def _view_items(self, path: str, view: str, params: dict, limit: int) -> list:
        """Fetch a catalog entity's `views[<view>].data` block, limited."""
        data = self._amp_api_get(path, params)
        return ((data.get("data") or [{}])[0].get("views", {}).get(view, {}).get("data") or [])[:limit]

    def get_similar_artists(self, artist_id: str, storefront: str = "us", limit: int = 10) -> list:
        """Fetch Apple Music's similar-artists view for an artist."""
        items = self._view_items(
            f"/v1/catalog/{storefront}/artists/{artist_id}",
            "similar-artists",
            {"views": "similar-artists", "extend": "artistBio,bornOrFormed,origin"},
            limit,
        )
        out = []
        for it in items:
            a = it.get("attributes", {})
            art = a.get("artwork", {}).get("url", "")
            g = a.get("genreNames") or []
            out.append(
                {
                    "id": it.get("id"),
                    "name": a.get("name"),
                    "url": a.get("url"),
                    "artwork_url": re.sub(r"\{w\}x\{h\}bb\.[a-z]+", "300x300bb.jpg", art) if art else None,
                    "genre": g[0] if g else None,
                    "born_or_formed": a.get("bornOrFormed"),
                    "origin": a.get("origin"),
                    "artist_bio": a.get("artistBio"),
                    "is_group": a.get("isGroup"),
                }
            )
        return out

    def get_you_might_also_like(self, album_id: str, storefront: str = "us", limit: int = 10) -> list:
        """Fetch Apple Music's you-might-also-like view for an album."""
        items = self._view_items(
            f"/v1/catalog/{storefront}/albums/{album_id}",
            "you-might-also-like",
            {"views": "you-might-also-like"},
            limit,
        )
        out = []
        for it in items:
            a = it.get("attributes", {})
            art = a.get("artwork", {}).get("url", "")
            rel = it.get("relationships", {}).get("artists", {}).get("data") or []
            artists = [
                {
                    "id": r.get("id"),
                    "name": (r.get("attributes") or {}).get("name"),
                    "url": (r.get("attributes") or {}).get("url"),
                }
                for r in rel
            ]
            if not artists and a.get("artistName"):
                artists = [{"name": a.get("artistName"), "url": None}]
            out.append(
                {
                    "store_adam_id": it.get("id"),
                    "title": a.get("name"),
                    "artist": a.get("artistName"),
                    "artists": artists,
                    "artwork_url": re.sub(r"\{w\}x\{h\}bb\.[a-z]+", "500x500bb.jpg", art) if art else None,
                    "release_date": a.get("releaseDate"),
                    "url": a.get("url"),
                    "storefronts": [storefront],
                    "watched": False,
                }
            )
        return out

    def search_artists(self, term: str, storefront: str = "us", limit: int = 25) -> list:
        """Search for artists by name.

        Returns a list of artist dicts with id, name, url, artwork_url, and extended info.
        """
        data = self._amp_api_get(
            f"/v1/catalog/{storefront}/search",
            {"term": term, "types": "artists", "limit": limit, "extend": "bornOrFormed,origin,artistBio"},
        )
        artists = []
        for item in data.get("results", {}).get("artists", {}).get("data") or []:
            attrs = item.get("attributes", {})
            art_url = attrs.get("artwork", {}).get("url", "")
            artwork_url = re.sub(r"\{w\}x\{h\}bb\.[a-z]+", "200x200bb.jpg", art_url) if art_url else None
            genre_names = attrs.get("genreNames") or []
            artists.append(
                {
                    "id": item.get("id"),
                    "name": attrs.get("name"),
                    "url": attrs.get("url"),
                    "artwork_url": artwork_url,
                    "genre": genre_names[0] if genre_names else None,
                    "born_or_formed": attrs.get("bornOrFormed"),
                    "origin": attrs.get("origin"),
                    "artist_bio": attrs.get("artistBio"),
                    "is_group": attrs.get("isGroup"),
                },
            )
        return artists

    def check_storefront_availability(self, adam_id: str, storefronts: list) -> dict:
        """Concurrently checks availability of an album across multiple storefronts.
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
