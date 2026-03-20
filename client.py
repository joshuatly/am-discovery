import urllib.request
import urllib.parse
import json
import re
from datetime import datetime
import concurrent.futures

import time
import base64
import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class AppleMusicClient:
    def __init__(self, user_token=None):
        self.user_token = user_token
        self.bearer_token = self._get_bearer_token()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Cookie": f"media-user-token={self.user_token}" if self.user_token else "",
        }
        if self.bearer_token:
            self.headers["Authorization"] = f"Bearer {self.bearer_token}"

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
        except:
            return True

    def _fetch_new_bearer_token(self):
        try:
            req = urllib.request.Request("https://music.apple.com/us/browse", headers={"User-Agent": "Mozilla/5.0"})
            html = urllib.request.urlopen(req).read().decode('utf-8')
            m = re.search(r'src="(/assets/index-[^"]+\.js)"', html)
            if not m:
                m = re.search(r'src="(/assets/index-legacy[^"]+\.js)"', html)
            if m:
                js_url = "https://music.apple.com" + m.group(1)
                js_req = urllib.request.Request(js_url, headers={"User-Agent": "Mozilla/5.0"})
                js_content = urllib.request.urlopen(js_req).read().decode('utf-8')
                tokens = re.findall(r'\"(eyJ[A-Za-z0-9-_]+[=]{0,2}\.[A-Za-z0-9-_]+[=]{0,2}\.[A-Za-z0-9-_.+/=]+)\"', js_content)
                if tokens:
                    return tokens[0]
        except Exception as e:
            print("Error fetching bearer token:", e)
        return None

    def get_room_new_releases(self, url, storefront):
        req = urllib.request.Request(url, headers=self.headers)
        try:
            with urllib.request.urlopen(req) as response:
                html = response.read().decode('utf-8')
                
            match = re.search(r'<script type="application/json" id="serialized-server-data">(.*?)</script>', html)
            if not match: return []
            data = json.loads(match.group(1))
            
            try:
                if isinstance(data, dict) and 'data' in data:
                    content = data['data'][0]['data']
                    sections = content.get('sections', [])
                elif isinstance(data, list):
                    content = data[0]['data']['data'][0]['data']
                    sections = content.get('sections', [])
                else: sections = []
            except Exception as e:
                import traceback
                print("Error extracting sections:", type(e), e)
                traceback.print_exc()
                return []
            
            print(f"Found {len(sections)} sections in room.", flush=True)
            if not sections and 'content' in locals() and isinstance(content, dict):
                print(f"Content keys: {list(content.keys())}")
            
            new_releases = []
            for sec in sections:
                title = sec.get('header', '')
                if isinstance(title, dict):
                    title = title.get('item', {}).get('titleLink', {}).get('title', str(title))
                elif not title and 'dictionary' in sec and 'title' in sec['dictionary']:
                    title = sec['dictionary']['title']
                
                print(f"Checking section: {title}")
                
                title_lower = title.lower() if isinstance(title, str) else str(title).lower()
                if any(kw in title_lower for kw in ['new', '新', 'release', 'terbaru', '最新', 'リリース']):
                    items = sec.get('items', [])
                    for item in items:
                        actual_item = item.get('item', item)
                        title_val, artist_val, url_val = None, None, None
                        
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
        except Exception: return []

    def get_artist_all_releases(self, url, storefront):
        """Fetch every release listed for an artist via the catalog API (paginated)."""
        m = re.search(r'music\.apple\.com/([a-z]{2})/artist/(?:[^/]+/)?(\d+)', url)
        if not m:
            return []
        sf, artist_id = m.group(1), m.group(2)

        releases = []
        seen = set()
        next_path = f"/v1/catalog/{sf}/artists/{artist_id}/albums"
        params = {"limit": "100"}

        while next_path:
            data = self._amp_api_get(next_path, params)
            if not data:
                break
            for item in data.get('data', []):
                adam_id = item.get('id')
                attrs = item.get('attributes', {})
                title_val = attrs.get('name')
                artist_val = attrs.get('artistName')
                item_url = attrs.get('url')
                if adam_id and title_val and adam_id not in seen:
                    seen.add(adam_id)
                    releases.append({
                        'storeAdamID': adam_id,
                        'title': title_val,
                        'artist': artist_val,
                        'url': item_url,
                        'storefronts': [storefront],
                    })
            next_link = data.get('next')
            if next_link:
                next_path = next_link.split('?')[0]
                offset_m = re.search(r'offset=(\d+)', next_link)
                params = {"limit": "100", "offset": offset_m.group(1)} if offset_m else {"limit": "100"}
            else:
                break
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

    def _amp_api_get(self, path: str, params: dict = None) -> dict:
        """GET from amp-api.music.apple.com, returns parsed JSON or {}."""
        query = ('?' + urllib.parse.urlencode(params)) if params else ''
        url = f"https://amp-api.music.apple.com{path}{query}"
        headers = {
            "User-Agent": self.headers["User-Agent"],
            "Origin": "https://music.apple.com",
            "Referer": "https://music.apple.com/",
        }
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        if self.user_token:
            headers["Music-User-Token"] = self.user_token
        req = urllib.request.Request(url, headers=headers)
        print(f"[amp-api] GET {path}{query}", flush=True)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            print(f"[amp-api] GET {path} failed: {e}")
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

    def check_storefront_availability(self, adam_id: str, storefronts: list) -> dict:
        """
        Concurrently checks availability of an album across multiple storefronts.
        Returns a dictionary with 'available' and 'unavailable' lists.
        """
        available = []
        unavailable = []
        
        def _check_sf(sf):
            url = f"https://music.apple.com/{sf}/album/{adam_id}"
            req = urllib.request.Request(url, headers=self.headers)
            try:
                urllib.request.urlopen(req, timeout=5)
                return sf, True
            except Exception:
                return sf, False

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = executor.map(_check_sf, storefronts)
            
        for sf, is_avail in results:
            if is_avail:
                available.append(sf)
            else:
                unavailable.append(sf)
                
        # Preserve input order
        available = [sf for sf in storefronts if sf in available]
        unavailable = [sf for sf in storefronts if sf in unavailable]
        
        return {"available": available, "unavailable": unavailable}
