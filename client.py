import base64
import concurrent.futures
import json
import logging
import os
import re
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request

from storefronts import discovery_names_for, fallback_titles, locale_for

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

    def discover_room_url(self, storefront):
        """Discover the New Release room URL from the /{storefront}/new page.

        Returns the full room URL (e.g. https://music.apple.com/jp/room/6760868920)
        or None if no matching section is found.
        """
        url = f"{_MUSIC_BASE}/{storefront}/new"
        html = self._web_get(url)
        if not html:
            return None

        match = re.search(
            r'<script type="application/json" id="serialized-server-data">(.*?)</script>',
            html,
        )
        if not match:
            return None
        data = json.loads(match.group(1))

        try:
            if isinstance(data, dict) and "data" in data:
                content = data["data"][0]["data"]
                sections = content.get("sections", [])
            elif isinstance(data, list):
                content = data[0]["data"]["data"][0]["data"]
                sections = content.get("sections", [])
            else:
                sections = []
        except Exception as e:
            logger.warning("Error extracting sections for room discovery: %s %s", type(e), e)
            return None

        titles = fallback_titles()
        for sec in sections:
            title = sec.get("header", "")
            room_url = None

            if isinstance(title, dict):
                title_link = title.get("item", {}).get("titleLink", {})
                title_text = title_link.get("title", "")
                link_url = title_link.get("url", "")
                if link_url:
                    room_url = f"{_MUSIC_BASE}{link_url}" if link_url.startswith("/") else link_url
            elif not title and "dictionary" in sec and "title" in sec["dictionary"]:
                title_text = sec["dictionary"]["title"]
            else:
                title_text = title if isinstance(title, str) else str(title)

            title_lower = title_text.lower() if isinstance(title_text, str) else ""
            if any(t in title_lower for t in titles):
                if room_url:
                    sf_match = re.search(r"music\.apple\.com/(\w+)/room/", room_url)
                    if sf_match and sf_match.group(1) != storefront:
                        logger.error(
                            "[%s] Room URL storefront mismatch (got %s): %s",
                            storefront.upper(),
                            sf_match.group(1),
                            room_url,
                        )
                        return None
                    logger.info(
                        "[%s] Discovered new release room: %s",
                        storefront.upper(),
                        room_url,
                    )
                    return room_url
                logger.error(
                    "[%s] Found new release section '%s' but no room URL",
                    storefront.upper(),
                    title_text,
                )
                return None

        logger.error("[%s] No new release section found on /new page", storefront.upper())
        return None

    def discover_new_release_room_id(self, storefront):
        """Find the New Releases room ID via the amp-api editorial groupings endpoint.

        Primary match: a resource under `resources["editorial-elements"]`
        whose `attributes.name` matches a known localized discovery title.
        Fallback: a resource with `attributes.emphasize == true` and
        `"albums"` in `attributes.resourceTypes` (Apple marks the featured
        new-release row this way regardless of locale).

        Returns a (room_id, last_modified) tuple. Both are None if no
        matching room was found; last_modified may be None even on a hit
        if the API response omits it.
        """
        locale = locale_for(storefront)
        names = [n.lower() for n in discovery_names_for(storefront)]
        params = {
            "name": "music",
            "platform": "web",
            "tabs": "nonsubscriber",
            "l": locale,
            "format[resources]": "map",
        }
        data = self._amp_api_get(f"/v1/editorial/{storefront}/groupings", params)
        if not data:
            return None, None

        resources = data.get("resources") or {}
        elements = resources.get("editorial-elements") or {}

        for res_id, res in elements.items():
            attrs = (res or {}).get("attributes") or {}
            name = attrs.get("name") or ""
            if name and name.lower() in names:
                room_id = str(attrs.get("contentId") or res_id)
                last_modified = attrs.get("lastModifiedDate")
                logger.info(
                    "[%s] Discovered new release room via API (name match): %s (last_modified=%s)",
                    storefront.upper(),
                    room_id,
                    last_modified,
                )
                return room_id, last_modified

        for res_id, res in elements.items():
            attrs = (res or {}).get("attributes") or {}
            resource_types = attrs.get("resourceTypes") or []
            if attrs.get("emphasize") is True and "albums" in resource_types:
                room_id = str(attrs.get("contentId") or res_id)
                last_modified = attrs.get("lastModifiedDate")
                logger.info(
                    "[%s] Discovered new release room via API (emphasize fallback): %s (last_modified=%s)",
                    storefront.upper(),
                    room_id,
                    last_modified,
                )
                return room_id, last_modified

        logger.warning(
            "[%s] No matching room in groupings response (looked for %s)",
            storefront.upper(),
            names,
        )
        return None, None

    def _parse_room_albums(self, data, storefront):
        """Extract album records from an editorial room API response."""
        releases = []
        resources = data.get("resources") or {}
        albums = resources.get("albums") or {}
        for adam_id, res in albums.items():
            attrs = (res or {}).get("attributes") or {}
            title = attrs.get("name")
            url = attrs.get("url")
            if not title or not url:
                continue
            releases.append(
                {
                    "storeAdamID": str(adam_id),
                    "title": title,
                    "artist": attrs.get("artistName"),
                    "url": url,
                    "storefronts": [storefront],
                },
            )
        return releases

    def get_room_albums(self, storefront, room_id, max_albums=200):
        """Fetch albums from an editorial room, paginating via /contents?offset=.

        Returns a list of release dicts in the same shape as get_room_new_releases.
        """
        locale = locale_for(storefront)
        first_params = {
            "art[url]": "c,f",
            "extend": "offers,seoDescription,seoTitle",
            "extend[albums]": "artistUrl",
            "fields[albums]": (
                "artistName,artistUrl,artwork,contentRating,editorialArtwork,"
                "editorialNotes,name,playParams,releaseDate,url,trackCount"
            ),
            "format[resources]": "map",
            "include[albums]": "artists",
            "l": locale,
            "platform": "web",
        }
        data = self._amp_api_get(f"/v1/editorial/{storefront}/rooms/{room_id}", first_params)
        releases = self._parse_room_albums(data, storefront)

        if len(releases) >= max_albums or len(releases) < 100:
            return releases[:max_albums]

        next_params = {
            "l": locale,
            "platform": "web",
            "format[resources]": "map",
            "offset": len(releases) + 1,
        }
        data2 = self._amp_api_get(
            f"/v1/editorial/{storefront}/rooms/{room_id}/contents",
            next_params,
        )
        releases.extend(self._parse_room_albums(data2, storefront))
        return releases[:max_albums]

    def discover_new_releases(self, storefront):
        """Discover new releases for a storefront.

        Tries the amp-api editorial groupings + rooms endpoints first (up to
        200 albums); falls back to the HTML scraper if that path returns
        nothing. Returns a (releases, room_id, room_last_modified) tuple;
        room_id and room_last_modified are None if discovery failed entirely
        (and room_last_modified is always None for the HTML fallback path).
        """
        try:
            room_id, last_modified = self.discover_new_release_room_id(storefront)
        except RateLimitError:
            raise
        except Exception as e:
            logger.warning("[%s] API room discovery failed: %s", storefront.upper(), e)
            room_id, last_modified = None, None

        if room_id:
            releases = self.get_room_albums(storefront, room_id)
            if releases:
                return releases, room_id, last_modified
            logger.warning(
                "[%s] API returned room %s but no albums; falling back to HTML",
                storefront.upper(),
                room_id,
            )

        room_url = self.discover_room_url(storefront)
        if not room_url:
            return [], None, None
        fallback_id = room_url.rstrip("/").split("/")[-1]
        return self.get_room_new_releases(room_url, storefront), fallback_id, None

    def get_room_new_releases(self, url, storefront):
        html = self._web_get(url)
        if not html:
            return []

        match = re.search(
            r'<script type="application/json" id="serialized-server-data">(.*?)</script>',
            html,
        )
        if not match:
            return []
        data = json.loads(match.group(1))

        content = None
        try:
            if isinstance(data, dict) and "data" in data:
                content = data["data"][0]["data"]
                sections = content.get("sections", [])
            elif isinstance(data, list):
                content = data[0]["data"]["data"][0]["data"]
                sections = content.get("sections", [])
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
        titles = fallback_titles()
        for sec in sections:
            title = sec.get("header", "")
            if isinstance(title, dict):
                title = title.get("item", {}).get("titleLink", {}).get("title", str(title))
            elif not title and "dictionary" in sec and "title" in sec["dictionary"]:
                title = sec["dictionary"]["title"]

            logger.debug("Checking section: %s", title)

            title_lower = title.lower() if isinstance(title, str) else str(title).lower()
            if any(t in title_lower for t in titles):
                items = sec.get("items", [])
                for item in items:
                    actual_item = item.get("item", item)

                    # Item fallback
                    if not actual_item:
                        continue

                    title_val, artist_val, url_val, adam_id = None, None, None, None

                    if "attributes" in actual_item:
                        attrs = actual_item["attributes"]
                        title_val = attrs.get("title") or attrs.get("name")
                        artist_val = attrs.get("artistName")
                        url_val = attrs.get("url")
                    else:
                        if actual_item.get("titleLinks"):
                            title_val = actual_item["titleLinks"][0].get("title")

                        if actual_item.get("subtitleLinks"):
                            artist_val = actual_item["subtitleLinks"][0].get("title")

                        desc = actual_item.get("contentDescriptor", {})
                        url_val = desc.get("url")
                        adam_id = desc.get("identifiers", {}).get("storeAdamID")

                    if not adam_id and url_val:
                        adam_m = re.search(r"/(\d+)(?:\?.*)?$", url_val)
                        adam_id = adam_m.group(1) if adam_m else actual_item.get("id")
                        if adam_id and "-" in str(adam_id):
                            adam_id = str(adam_id).split("-")[-1].strip()

                    if title_val and url_val and adam_id:
                        release_info = {
                            "storeAdamID": adam_id,
                            "title": title_val,
                            "artist": artist_val,
                            "url": url_val,
                            "storefronts": [storefront],
                        }
                        new_releases.append(release_info)
                break
        return new_releases

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
