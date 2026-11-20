"""Copy the site's Unsplash photos into the assets published by GitHub Pages."""

import argparse
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen


PHOTO_URL = re.compile(r'https://images\.unsplash\.com/photo-[a-z0-9-]+\?[^\s"\'<>#,]+')
METADATA = re.compile(r'<meta\b[^>]*>|<script type="application/ld\+json">.*?</script>', re.S)


def photo_file(url):
    address = urlsplit(url)
    size = parse_qs(address.query)
    filename = address.path.rsplit('/', 1)[-1] + '-' + size['w'][0]
    if 'h' in size:
        filename += 'x' + size['h'][0]
    return filename + '.jpg'


def download(url, target):
    options = {key: values[0] for key, values in parse_qs(urlsplit(url).query).items() if key != 'auto'}
    options['fm'] = 'jpg'
    request = Request(url.split('?', 1)[0] + '?' + urlencode(options), headers={'User-Agent': 'VkusnoProsto/1.0'})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=20) as response:
                data = response.read(4_000_001)
            if not data.startswith(b'\xff\xd8\xff') or len(data) > 4_000_000:
                raise ValueError(f'Invalid photo: {target.name}')
            target.write_bytes(data)
            return
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('site_url')
    args = parser.parse_args()
    assets = args.directory / 'assets' / 'photos'
    assets.mkdir(parents=True, exist_ok=True)
    pages = {p: p.read_text(encoding='utf-8') for p in args.directory.rglob('*.html')}
    photos = {photo_file(url): url for html in pages.values() for url in PHOTO_URL.findall(html)}

    with ThreadPoolExecutor(max_workers=8) as executor:
        jobs = [executor.submit(download, url, assets / name) for name, url in photos.items()
                if not (assets / name).is_file()]
        for job in jobs:
            job.result()

    site_path = urlsplit(args.site_url).path.rstrip('/')
    local_path = f'{site_path}/assets/photos/'
    absolute_path = f'{args.site_url.rstrip("/")}/assets/photos/'
    for page, html in pages.items():
        # Social previews and structured data require absolute image URLs.
        html = METADATA.sub(lambda tag: PHOTO_URL.sub(lambda m: absolute_path + photo_file(m[0]), tag[0]), html)
        html = PHOTO_URL.sub(lambda m: local_path + photo_file(m[0]), html)
        if 'https://images.unsplash.com/photo-' in html:
            raise ValueError(f'Unconverted image URL: {page}')
        page.write_text(html, encoding='utf-8', newline='\n')
    print(f'Published {len(photos)} photo variants on {len(pages)} pages.')


if __name__ == '__main__':
    main()
