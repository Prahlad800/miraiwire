"""Run `python worker.py` continuously or `python worker.py --once` for due feeds."""
import argparse
import calendar
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import html
import json
import logging
import os
from langdetect import detect, DetectorFactory, LangDetectException
DetectorFactory.seed = 0
from pathlib import Path
import re
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import feedparser
from feed_config import load_settings
from rss_images import image_from_entry
from app import app, connect

CONFIG = Path(__file__).with_name('feeds.json')

def now():
    return datetime.now(timezone.utc)

def stamp(value):
    return value.isoformat(timespec='seconds')

def plain(value):
    return html.unescape(re.sub('<[^>]+>', '', value or '')).strip()

def interval_minutes(feed, settings):
    provider = feed.get('provider', 'google_news')
    override = os.environ.get('RSS_' + provider.upper() + '_FETCH_MINUTES')
    value = int(feed.get('fetch_interval_minutes', settings.get('provider_intervals_minutes', {}).get(provider, override or settings['fetch_interval_minutes'])))
    if value < 1:
        raise ValueError('Fetch intervals must be positive')
    return value

def is_english(title, summary):
    if os.environ.get('RSS_ENGLISH_ONLY', 'true').lower() != 'true':
        return True
    try:
        return detect(title + ' ' + summary) == 'en'
    except LangDetectException:
        return False

def fetch_feed(feed, settings, database):
    attempted = now()
    saved = 0
    error = None
    try:
        req = Request(feed['url'], headers={'User-Agent': 'MiraiwireRSS/1.0'})
        with urlopen(req, timeout=settings['request_timeout_seconds']) as response:
            raw = response.read(5_000_001)
        if len(raw) > 5_000_000:
            raise ValueError('Feed exceeds 5 MB limit')
        parsed = feedparser.parse(raw)
        if not parsed.version or (parsed.bozo and not parsed.entries):
            raise ValueError('Invalid RSS/Atom response')
        with connect(database) as db:
            for entry in parsed.entries[:settings['max_items_per_feed']]:
                url = entry.get('link', '')
                title = plain(entry.get('title'))
                if not title or urlparse(url).scheme not in ('https', 'http'):
                    continue
                summary = plain(entry.get('summary'))
                if not is_english(title, summary):
                    continue
                date = entry.get('published_parsed') or entry.get('updated_parsed')
                published = datetime.fromtimestamp(calendar.timegm(date), timezone.utc) if date else attempted
                image = image_from_entry(entry)
                if not image:
                    continue
                source = plain(entry.get('source', {}).get('title', feed['name']))
                cursor = db.execute('INSERT OR IGNORE INTO news(title,url,summary,source,category,image_url,published_at,fetched_at) VALUES(?,?,?,?,?,?,?,?)', (title, url, summary, source, feed['category'], image, stamp(published), stamp(attempted)))
                saved += cursor.rowcount
                if cursor.rowcount == 0:
                    db.execute("UPDATE news SET image_url=? WHERE url=? AND (image_url IS NULL OR TRIM(image_url)='')", (image, url))
    except Exception as exc:
        error = str(exc)[:500]
        logging.warning('%s: %s', feed['name'], error)
    next_fetch = attempted + timedelta(minutes=interval_minutes(feed, settings))
    with connect(database) as db:
        db.execute('''INSERT INTO feed_status(feed_id,last_attempt_at,last_success_at,next_fetch_at,last_error,items_saved)
        VALUES(?,?,?,?,?,?) ON CONFLICT(feed_id) DO UPDATE SET
        last_attempt_at=excluded.last_attempt_at,
        last_success_at=COALESCE(excluded.last_success_at,feed_status.last_success_at),
        next_fetch_at=excluded.next_fetch_at,last_error=excluded.last_error,items_saved=excluded.items_saved''',
        (feed['id'], stamp(attempted), stamp(now()) if error is None else None, stamp(next_fetch), error, saved))
    return {'feed_id':feed['id'], 'saved':saved, 'error':error}

def run_once(database=None, config_path=CONFIG):
    database = database or app.config['DATABASE']
    settings = load_settings(config_path)
    if settings['fetch_interval_minutes'] < 1 or settings['request_timeout_seconds'] < 1 or settings['max_items_per_feed'] < 1:
        raise ValueError('Fetch settings must be positive')
    with connect(database) as db:
        statuses = {row['feed_id']:row['last_attempt_at'] for row in db.execute('SELECT feed_id,last_attempt_at FROM feed_status')}
    due = [feed for feed in settings['feeds'] if feed.get('enabled', True) and (not statuses.get(feed['id']) or datetime.fromisoformat(statuses[feed['id']]) + timedelta(minutes=interval_minutes(feed, settings)) <= now())]
    with ThreadPoolExecutor(max_workers=5) as pool:
        return list(pool.map(lambda feed: fetch_feed(feed, settings, database), due))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            results = run_once()
            logging.info('Processed %d feeds; saved %d new stories', len(results), sum(item['saved'] for item in results))
        except Exception as exc:
            logging.error('Fetch cycle failed (%s); retrying next cycle', type(exc).__name__)
            if args.once:
                raise SystemExit(1)
        if args.once:
            break
        time.sleep(30)
