"""SQLite news API. Run the separate worker to ingest RSS feeds."""
import os
import sqlite3
import re
from pathlib import Path
from flask import Flask, jsonify, request
from dotenv import load_dotenv
from database import TursoConnection
from seo import article_seo, listing_seo, news_slug, with_slug
from feed_config import load_settings

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / '.env')
SCHEMA = """
CREATE TABLE IF NOT EXISTS news (
 id INTEGER PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
 summary TEXT NOT NULL DEFAULT '', source TEXT NOT NULL, category TEXT NOT NULL,
 image_url TEXT, published_at TEXT NOT NULL, fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS news_date ON news(published_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS news_category ON news(category, published_at DESC);
CREATE TABLE IF NOT EXISTS feed_status (
 feed_id INTEGER PRIMARY KEY, last_attempt_at TEXT, last_success_at TEXT,
 next_fetch_at TEXT, last_error TEXT, items_saved INTEGER DEFAULT 0
);
"""

class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()

def connect(path):
    if str(path).startswith(('libsql://', 'https://', 'turso://')):
        return TursoConnection(str(path), os.environ.get('TURSO_AUTH_TOKEN', ''), os.environ.get('TURSO_DATABASE_ENGINE', 'libsql'))
    db = sqlite3.connect(str(path), timeout=30, factory=Connection)
    db.row_factory = sqlite3.Row
    return db

def initialize(path):
    remote = str(path).startswith(('libsql://', 'https://', 'turso://'))
    if not remote:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        if not remote:
            db.execute('PRAGMA journal_mode=WAL')
        db.executescript(SCHEMA)

def create_app(config=None):
    app = Flask(__name__)
    app.config['DATABASE'] = os.environ.get('NEWS_DATABASE', str(BASE / 'data' / 'news.sqlite3'))
    if os.environ.get('DATABASE_DRIVER', 'sqlite') == 'turso':
        app.config['DATABASE'] = os.environ.get('TURSO_DATABASE_URL', '')
        if not app.config['DATABASE']:
            raise ValueError('TURSO_DATABASE_URL is required for DATABASE_DRIVER=turso')
    if config:
        app.config.update(config)
    initialize(app.config['DATABASE'])

    @app.get('/health')
    def health():
        return jsonify(status='ok')

    @app.get('/ready')
    def ready():
        try:
            with connect(app.config['DATABASE']) as db:
                count = db.execute('SELECT COUNT(*) FROM news').fetchone()[0]
            return jsonify(status='ready', database='turso' if str(app.config['DATABASE']).startswith(('libsql://','https://','turso://')) else 'sqlite', news_count=count)
        except Exception:
            return jsonify(status='unavailable'), 503

    @app.get('/api/v1/feeds')
    def feeds():
        from worker import CONFIG, interval_minutes
        import json
        settings = load_settings(CONFIG)
        with connect(app.config['DATABASE']) as db:
            statuses = {row['feed_id']:dict(row) for row in db.execute('SELECT * FROM feed_status')}
        result = {'language':settings.get('language', 'en')}
        for provider in ('google_news', 'the_hindu', 'bbc'):
            provider_feeds = [feed for feed in settings['feeds'] if feed.get('provider', 'google_news') == provider]
            successful = [statuses[feed['id']]['last_success_at'] for feed in provider_feeds
                if feed['id'] in statuses and statuses[feed['id']].get('last_success_at')]
            result[provider] = {
                'fetch_interval_minutes':interval_minutes({'provider':provider}, settings),
                'last_fetched_at':max(successful) if successful else None,
                'feeds':[{key:feed.get(key, 'en' if key == 'language' else provider if key == 'provider' else None)
                    for key in ('id', 'name', 'category', 'enabled', 'provider', 'language')}
                    for feed in provider_feeds]
            }
        return jsonify(result)

    @app.get('/api/v1/feeds/details')
    def feed_details():
        from worker import CONFIG, interval_minutes
        import json
        from datetime import datetime, timedelta
        settings = load_settings(CONFIG)
        with connect(app.config['DATABASE']) as db:
            statuses = {row['feed_id']:dict(row) for row in db.execute('SELECT * FROM feed_status')}
        data = []
        for feed in settings['feeds']:
            state = statuses.get(feed['id'], {})
            minutes = interval_minutes(feed, settings)
            last = state.get('last_attempt_at')
            next_at = (datetime.fromisoformat(last) + timedelta(minutes=minutes)).isoformat(timespec='seconds') if last else None
            data.append(dict(feed, fetch_interval_minutes=minutes, last_attempt_at=last,
                last_success_at=state.get('last_success_at'), next_fetch_at=next_at,
                last_error=state.get('last_error'), items_saved=state.get('items_saved', 0)))
        return jsonify(data=data, total=len(data), language='en')

    @app.errorhandler(400)
    def bad_request(error):
        return jsonify(error='Invalid request parameters'), 400

    def pagination():
        try:
            page = int(request.args.get('page', 1))
            limit = int(request.args.get('limit', 20))
            if page < 1 or not 1 <= limit <= 100:
                raise ValueError()
            return page, limit
        except ValueError:
            from werkzeug.exceptions import BadRequest
            raise BadRequest()

    def listing(search=False):
        page, limit = pagination()
        clauses, params = ["image_url IS NOT NULL AND TRIM(image_url) != ''"], []
        if search:
            query = request.args.get('q', '').strip()
            if not query or len(query) > 200:
                return jsonify(error='q is required (1-200 characters)'), 400
            escaped = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            clauses.append("(title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\')")
            params.extend(['%' + escaped + '%'] * 2)
        category = request.args.get('category', '').strip()
        if category:
            clauses.append('category = ?')
            params.append(category)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        with connect(app.config['DATABASE']) as db:
            total = db.execute('SELECT COUNT(*) FROM news' + where, params).fetchone()[0]
            rows = db.execute('SELECT * FROM news' + where + ' ORDER BY published_at DESC, id DESC LIMIT ? OFFSET ?', params + [limit, (page-1)*limit]).fetchall()
        stories = [with_slug(dict(row)) for row in rows]
        return jsonify(data=stories, seo=listing_seo(stories, category, request.args.get('q', '').strip() if search else '', page), page=page, limit=limit, total=total, total_pages=(total+limit-1)//limit)

    @app.get('/api/v1/home')
    def home():
        return listing()

    @app.get('/api/v1/news/search')
    def search():
        return listing(True)

    def resolve_story(news_key):
        numeric = re.fullmatch(r'[0-9]+', news_key)
        suffix = numeric or re.search(r'-([0-9]+)$', news_key)
        if not suffix:
            return None
        news_id = int(news_key if numeric else suffix.group(1))
        if news_id > 9223372036854775807:
            return None
        with connect(app.config['DATABASE']) as db:
            row = db.execute("SELECT * FROM news WHERE id=? AND image_url IS NOT NULL AND TRIM(image_url) != ''", (news_id,)).fetchone()
        if row is None:
            return None
        story = dict(row)
        return story if numeric or news_slug(story) == news_key else None

    @app.get('/api/v1/news/<news_key>')
    def detail(news_key):
        story = resolve_story(news_key)
        if story is None:
            return jsonify(error='News not found'), 404
        return jsonify(data=with_slug(story), seo=article_seo(story))

    @app.get('/api/v1/news/<news_key>/related')
    def related(news_key):
        page, limit = pagination()
        story = resolve_story(news_key)
        if story is None:
            return jsonify(error='News not found'), 404
        with connect(app.config['DATABASE']) as db:
            total = db.execute("SELECT COUNT(*) FROM news WHERE category=? AND id!=? AND image_url IS NOT NULL AND TRIM(image_url) != ''", (story['category'], story['id'])).fetchone()[0]
            rows = db.execute("SELECT * FROM news WHERE category=? AND id!=? AND image_url IS NOT NULL AND TRIM(image_url) != '' ORDER BY published_at DESC, id DESC LIMIT ? OFFSET ?", (story['category'], story['id'], limit, (page-1)*limit)).fetchall()
        return jsonify(data=[with_slug(dict(item)) for item in rows], page=page, limit=limit, total=total, total_pages=(total+limit-1)//limit)

    return app

app = create_app()
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)
