from html.parser import HTMLParser
from urllib.parse import urljoin,urlparse
class Images(HTMLParser):
    def __init__(self):
        super().__init__(); self.urls=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag.lower()=='img':
            value=attrs.get('src') or attrs.get('data-src')
            if value: self.urls.append(value)
def image_from_entry(entry):
    candidates=[]
    for item in entry.get('media_content',[]):
        if item.get('medium')=='video' or item.get('type','').startswith(('video/','audio/')): continue
        candidates.append(item.get('url',''))
    candidates.extend(item.get('url','') for item in entry.get('media_thumbnail',[]))
    candidates.extend(item.get('href','') for item in entry.get('enclosures',[]) if item.get('type','').startswith('image/'))
    parser=Images()
    parser.feed(entry.get('summary',''))
    for content in entry.get('content',[]): parser.feed(content.get('value',''))
    candidates.extend(parser.urls)
    for value in candidates:
        url=urljoin(entry.get('link',''),value.strip())
        if urlparse(url).scheme in ('https','http') and urlparse(url).hostname:
            return url
    return None
