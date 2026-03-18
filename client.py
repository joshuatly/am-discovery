import urllib.request
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

    # -----------------------------------------------------------------
    # All artist releases (albums, singles, EPs, live, compilations…)
    # -----------------------------------------------------------------
    _RELEASE_SECTION_KW = [
        # English
        'album', 'single', 'ep', 'live', 'compilation', 'collection',
        'soundtrack', 'latest', 'release', 'mixtape',
        # Chinese
        '專輯', '單曲', '最新發行', '精選', '現場', '合輯', '最新',
        # Japanese
        'アルバム', 'シングル', '最新リリース', 'ライブ',
        # Malay
        'terbaru', 'lagu',
    ]
    _SKIP_SECTION_KW = [
        'appears on', 'fans also', 'similar', 'followers', 'playlist',
        '參與作品', '粉絲', '喜歡此歌手', 'video', 'mv', '影片',
    ]

    def get_artist_all_releases(self, url, storefront):
        """Fetch every release listed on an artist page (albums, singles, EPs, live, etc.)."""
        req = urllib.request.Request(url, headers=self.headers)
        try:
            with urllib.request.urlopen(req) as response:
                html = response.read().decode('utf-8')

            match = re.search(r'<script type="application/json" id="serialized-server-data">(.*?)</script>', html)
            if not match:
                return []
            data = json.loads(match.group(1))

            try:
                if isinstance(data, dict) and 'data' in data:
                    content = data['data'][0]['data']
                    sections = content.get('sections', [])
                elif isinstance(data, list):
                    content = data[0]['data']['data'][0]['data']
                    sections = content.get('sections', [])
                else:
                    sections = []
            except Exception:
                return []

            releases = []
            seen = set()

            for sec in sections:
                header = sec.get('header', '')
                if isinstance(header, dict):
                    title = header.get('item', {}).get('titleLink', {}).get('title', '')
                elif not header and 'dictionary' in sec:
                    title = sec['dictionary'].get('title', '')
                else:
                    title = str(header)

                title_lower = title.lower() if title else ''

                if any(kw in title_lower for kw in self._SKIP_SECTION_KW):
                    continue
                if not any(kw in title_lower for kw in self._RELEASE_SECTION_KW):
                    continue

                for item in sec.get('items', []):
                    actual = item.get('item', item)
                    if not actual:
                        continue

                    title_val, artist_val, url_val, adam_id = None, None, None, None

                    if 'attributes' in actual:
                        attrs = actual['attributes']
                        title_val = attrs.get('title') or attrs.get('name')
                        artist_val = attrs.get('artistName')
                        url_val = attrs.get('url')
                    else:
                        if actual.get('titleLinks'):
                            title_val = actual['titleLinks'][0].get('title')
                        if actual.get('subtitleLinks'):
                            artist_val = actual['subtitleLinks'][0].get('title')
                        desc = actual.get('contentDescriptor', {})
                        url_val = desc.get('url')
                        adam_id = desc.get('identifiers', {}).get('storeAdamID')

                    if not adam_id and url_val:
                        m = re.search(r'/(\d+)(?:\?.*)?$', url_val)
                        adam_id = m.group(1) if m else actual.get('id')
                        if adam_id and '-' in str(adam_id):
                            adam_id = str(adam_id).split('-')[-1].strip()

                    if title_val and url_val and adam_id and adam_id not in seen:
                        seen.add(adam_id)
                        releases.append({
                            'storeAdamID': adam_id,
                            'title': title_val,
                            'artist': artist_val,
                            'url': url_val,
                            'storefronts': [storefront],
                        })
            return releases
        except Exception:
            return []

    def get_artist_new_releases(self, url, storefront):
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
            except Exception: return []
            
            new_releases = []
            for sec in sections:
                title = sec.get('header', '')
                if isinstance(title, dict):
                    title = title.get('item', {}).get('titleLink', {}).get('title', str(title))
                elif not title and 'dictionary' in sec and 'title' in sec['dictionary']:
                    title = sec['dictionary']['title']
                
                title_lower = str(title).lower() if title else ""
                
                # For artists, we usually want "Albums", "Singles & EPs", "Latest Release"
                # "專輯", "單曲及 EP", "最新發行" etc.
                allowed_sections = ['album', 'single', 'ep', 'latest release', '專輯', '單曲', '最新發行', '最新リリース', 'アルバム', 'シングル', 'terbaru']
                if any(kw in title_lower for kw in allowed_sections):
                    items = sec.get('items', [])
                    for item in items:
                        actual_item = item.get('item', item)
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
                            
                        # Only add if we don't already have it
                        if title_val and url_val and adam_id:
                            release_info = {
                                'storeAdamID': adam_id,
                                'title': title_val,
                                'artist': artist_val,
                                'url': url_val,
                                'storefronts': [storefront]
                            }
                            # check duplicates within the artist page (latest release vs albums)
                            if not any(r['storeAdamID'] == adam_id for r in new_releases):
                                new_releases.append(release_info)
            return new_releases
        except Exception: return []

    def _get_catalog_attributes(self, adam_id: str, storefront: str) -> dict:
        """Fetch catalog attributes for an album via the Apple Music API."""
        url = f"https://amp-api.music.apple.com/v1/catalog/{storefront}/albums/{adam_id}?extend=extendedAssetUrls"
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
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            attrs = data.get('data', [{}])[0].get('attributes', {})
            return attrs
        except Exception as e:
            print(f"[catalog] Failed to fetch attributes for {adam_id}/{storefront}: {e}")
            return {}

    def get_album_full_info(self, url: str) -> dict:
        """Fetch full album metadata from its Apple Music page.
        Returns a dict with: release_date, artwork_url, track_count, genre,
        description, artist_id, artist_url, audio_formats (all may be None if not found).
        """
        req = urllib.request.Request(url, headers=self.headers)
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
        data = None
        try:
            with urllib.request.urlopen(req) as response:
                html = response.read().decode('utf-8')
            match = re.search(r'<script type="application/json" id="serialized-server-data">(.*?)</script>', html)
            if not match:
                return result
            data = json.loads(match.group(1))

            # Walk the sections list to find album-detail-header
            sections = []
            try:
                if isinstance(data, list):
                    sections = data[0]['data']['data'][0]['data'].get('sections', [])
                elif isinstance(data, dict):
                    sections = data['data'][0]['data'].get('sections', [])
            except Exception:
                pass

            for sec in sections:
                sec_id = sec.get('id', '')
                if 'album-detail-header' not in sec_id:
                    continue
                items = sec.get('items', [])
                if not items:
                    continue
                item = items[0]

                # Artwork
                artwork = item.get('artwork', {})
                if isinstance(artwork, dict):
                    art_dict = artwork.get('dictionary', artwork)
                    art_url = art_dict.get('url')
                    if art_url:
                        result['artwork_url'] = art_url.replace('{w}x{h}bb.{f}', '500x500bb.webp')

                # Track count
                result['track_count'] = item.get('trackCount')

                # Genre + year from quaternaryTitle e.g. "廣東歌/香港流行樂 · 2026年"
                qt = item.get('quaternaryTitle', '')
                if qt and ' · ' in qt:
                    parts = qt.split(' · ')
                    result['genre'] = parts[0].strip()

                # Description
                modal = item.get('modalPresentationDescriptor', {})
                result['description'] = modal.get('paragraphText')

                # Title from titleLinks
                title_links = item.get('titleLinks', [])
                if title_links:
                    result['title'] = title_links[0].get('title')

                # Artist ID & URL from subtitleLinks — prefer the link with a valid artist segue
                subtitle_links = item.get('subtitleLinks', [])
                for sl in subtitle_links:
                    try:
                        dest = sl['segue']['destination']['contentDescriptor']
                        adam = dest.get('identifiers', {}).get('storeAdamID')
                        if adam:
                            result['artist'] = sl.get('title')
                            result['artist_id'] = str(adam)
                            result['artist_url'] = dest.get('url')
                            break
                    except Exception:
                        continue
                # Fallback: first subtitle that isn't a bare 4-digit year
                if not result['artist'] and subtitle_links:
                    title = subtitle_links[0].get('title')
                    if title and not re.match(r'^\d{4}$', title):
                        result['artist'] = title

                break  # found the header section

            # Tracklist — scan remaining sections
            result['tracks'] = self._extract_tracks(sections)

        except Exception as e:
            print(f"Error fetching album info for {url}: {e}")

        # Fetch release date + audio format traits from catalog API
        try:
            m = re.search(r'music\.apple\.com/([a-z]{2})/album/(?:[^/]+/)?(\d+)', url)
            if m:
                sf, adam_id = m.group(1), m.group(2)
                attrs = self._get_catalog_attributes(adam_id, sf)
                if attrs:
                    result['release_date'] = attrs.get('releaseDate') or self._extract_release_date(data)
                    formats = list(attrs.get('audioTraits') or [])
                    if attrs.get('isMasteredForItunes'):
                        formats.append('adm')
                    result['audio_formats'] = formats if formats else None
        except Exception as e:
            print(f"[catalog] Error fetching catalog attributes for {url}: {e}")

        # Fallback: parse release date from page if catalog API didn't provide it
        if not result['release_date'] and data is not None:
            result['release_date'] = self._extract_release_date(data)

        return result

    def _parse_track_item(self, item: dict):
        title = None
        track_number = None
        duration_ms = None

        # API-style: attributes wrapper
        attrs = item.get('attributes') or {}
        if isinstance(attrs, dict) and attrs:
            title = attrs.get('name') or attrs.get('title')
            track_number = attrs.get('trackNumber')
            duration_ms = attrs.get('durationInMillis')

        # Web-scrape style: titleLinks array
        if not title:
            tl = item.get('titleLinks') or []
            if tl and isinstance(tl, list):
                title = (tl[0] or {}).get('title')

        # Direct fields fallback
        if not title:
            title = item.get('title') or item.get('name') or item.get('primaryTitle')
        if not track_number:
            track_number = item.get('trackNumber')
        if not duration_ms:
            duration_ms = (item.get('durationInMillis') or
                           item.get('durationMs') or
                           item.get('duration'))

        if not title:
            return None
        return {'title': title, 'track_number': track_number, 'duration_ms': duration_ms}

    def _extract_tracks(self, sections: list) -> list:
        print(f"[Tracks] total sections={len(sections)}: "
              + ", ".join(f"'{s.get('id','?')}'({len(s.get('items',[]))})" for s in sections),
              flush=True)
        best = []
        best_score = 0
        for sec in sections:
            sec_id = sec.get('id', '')
            if 'album-detail-header' in sec_id:
                continue
            items = sec.get('items', [])
            if not items:
                continue
            tracks = []
            score = 0
            for item in items:
                actual = item.get('item', item)
                if not isinstance(actual, dict):
                    continue
                t = self._parse_track_item(actual)
                if t:
                    tracks.append(t)
                    # Only real track signals count — title-only matches score 0
                    score += 10 if t.get('track_number') else 0
                    score += 5  if t.get('duration_ms')  else 0
            if not tracks and items:
                sample = items[0].get('item', items[0]) if isinstance(items[0], dict) else items[0]
                print(f"[Tracks] section '{sec_id}' sample keys: "
                      f"{list(sample.keys()) if isinstance(sample, dict) else type(sample)}", flush=True)
            print(f"[Tracks] section '{sec_id}': {len(items)} items → "
                  f"{len(tracks)} parsed, score={score}", flush=True)
            # Must have at least one item with a real track signal to be considered
            if score > 0 and score > best_score:
                best_score = score
                best = tracks
        print(f"[Tracks] best section: {len(best)} tracks (score={best_score})", flush=True)
        return best

    def _extract_release_date(self, data) -> str:
        """Recursive search for a release-date description string in the data blob."""
        desc = None

        def find_desc(obj):
            nonlocal desc
            if desc:
                return
            if isinstance(obj, dict):
                if 'description' in obj and isinstance(obj['description'], str):
                    if any(k in obj['description'] for k in ['202', '201', '首歌', 'Songs', '曲']):
                        desc = obj['description']
                for v in obj.values():
                    find_desc(v)
            elif isinstance(obj, list):
                for v in obj:
                    find_desc(v)

        find_desc(data)
        if not desc:
            return None

        # Chinese/Japanese: 2026年3月12日
        m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', desc)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

        month_map = {
            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05', 'jun': '06',
            'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12',
            'mac': '03', 'mei': '05', 'ogos': '08', 'okt': '10', 'dis': '12'
        }
        m2 = re.search(r'(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})', desc)
        if m2:
            day, mo_str, year = m2.groups()
            return f"{year}-{month_map.get(mo_str[:3].lower(), '01')}-{int(day):02d}"
        m3 = re.search(r'([a-zA-Z]+)\s+(\d{1,2}),?\s+(\d{4})', desc)
        if m3:
            mo_str, day, year = m3.groups()
            return f"{year}-{month_map.get(mo_str[:3].lower(), '01')}-{int(day):02d}"
        year_m = re.search(r'\b((?:19|20)\d{2})\b', desc)
        if year_m:
            return f"{year_m.group(1)}-00-00"
        return None

    def get_album_release_date(self, url):
        req = urllib.request.Request(url, headers=self.headers)
        try:
            with urllib.request.urlopen(req) as response:
                html = response.read().decode('utf-8')
            match = re.search(r'<script type="application/json" id="serialized-server-data">(.*?)</script>', html)
            if not match: return "Unknown"
            data = json.loads(match.group(1))
            
            # recursive search for description
            desc = None
            def find_desc(obj):
                nonlocal desc
                if desc: return
                if isinstance(obj, dict):
                    if 'description' in obj and isinstance(obj['description'], str):
                        # check if it looks like a release blurb
                        if '202' in obj['description'] or '首歌' in obj['description'] or 'Songs' in obj['description'] or '曲' in obj['description']:
                            desc = obj['description']
                    for v in obj.values(): find_desc(v)
                elif isinstance(obj, list):
                    for v in obj: find_desc(v)
            find_desc(data)
            
            if desc:
                # Try to parse Chinese/Japanese format: "2026年3月12日"
                m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', desc)
                if m:
                    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                    
                # Try English / Malay formats like "12 March 2026" or "March 12, 2026"
                month_map = {
                    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05', 'jun': '06',
                    'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12',
                    'mac': '03', 'mei': '05', 'ogos': '08', 'okt': '10', 'dis': '12' # Malay months
                }
                
                # Format: 12 March 2026
                m2 = re.search(r'(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})', desc)
                if m2:
                    day, mo_str, year = m2.groups()
                    mo_prefix = mo_str[:3].lower()
                    mo_num = month_map.get(mo_prefix, '01')
                    return f"{year}-{mo_num}-{int(day):02d}"
                    
                # Format: March 12, 2026
                m3 = re.search(r'([a-zA-Z]+)\s+(\d{1,2}),?\s+(\d{4})', desc)
                if m3:
                    mo_str, day, year = m3.groups()
                    mo_prefix = mo_str[:3].lower()
                    mo_num = month_map.get(mo_prefix, '01')
                    return f"{year}-{mo_num}-{int(day):02d}"
                    
                # basic fallback
                year_m = re.search(r'(202\d)', desc)
                if year_m: return f"{year_m.group(1)}-00-00 (fallback)"
            return "Unknown"
        except Exception: return "Unknown"

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
