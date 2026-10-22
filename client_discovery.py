"""New-release room discovery for AppleMusicClient.

Split out of client.py to keep it under the size limit. `DiscoveryMixin`
relies on the host class for `_web_get` and `_amp_api_get`; all methods are
called as `AppleMusicClient` methods.
"""

import json
import logging
import re
import traceback

from storefronts import discovery_names_for, fallback_titles, locale_for

_MUSIC_BASE = "https://music.apple.com"

logger = logging.getLogger("client")


class DiscoveryMixin:
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
        from client import RateLimitError  # deferred: client imports this module

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
