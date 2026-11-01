"""Grouped RSS configuration; runtime fetch timestamps live in the database."""
import json
from pathlib import Path
CONFIG=Path(__file__).with_name('feeds.json')
PROVIDERS=('google_news','the_hindu','bbc')
def load_settings(path=CONFIG):
    raw=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if 'feeds' in raw:
        return raw  # Backward-compatible with old configuration files.
    settings={'language':raw.get('language','en'),'fetch_interval_minutes':30,
              'request_timeout_seconds':15,'max_items_per_feed':100,
              'provider_intervals_minutes':{},'feeds':[]}
    for provider in PROVIDERS:
        group=raw.get(provider,{})
        settings['provider_intervals_minutes'][provider]=group.get('fetch_interval_minutes',30)
        for feed in group.get('feeds',[]):
            settings['feeds'].append(dict(feed,provider=provider,language=raw.get('language','en')))
    return settings
