"""Turso SQL-over-HTTP adapter; SQLite-compatible row and cursor surface."""
import json
import os
from urllib.parse import urlparse
from urllib.request import Request, urlopen

class Row(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)

class Cursor:
    def __init__(self, result):
        columns = [column['name'] for column in result.get('cols', [])]
        def decode(value):
            if value['type'] == 'null': return None
            if value['type'] == 'integer': return int(value['value'])
            if value['type'] == 'float': return float(value['value'])
            return value.get('value')
        self.rows = [Row(zip(columns, map(decode, row))) for row in result.get('rows', [])]
        self.rowcount = result.get('affected_row_count', 0)
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None
    def __iter__(self): return iter(self.rows)

class TursoConnection:
    # Each statement is atomic and committed remotely; no implicit local fallback.
    def __init__(self, url, token, engine='libsql'):
        parsed = urlparse(url)
        if parsed.scheme not in ('https', 'libsql', 'turso') or not parsed.hostname or not token:
            raise ValueError('Set TURSO_DATABASE_URL and TURSO_AUTH_TOKEN in backend/.env')
        self.endpoint = 'https://' + parsed.netloc + ('/v3/pipeline' if engine == 'turso' else '/v2/pipeline')
        self.token = token
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, sql, params=()):
        def encode(value):
            if value is None: return {'type':'null'}
            if isinstance(value, int): return {'type':'integer','value':str(value)}
            if isinstance(value, float): return {'type':'float','value':value}
            return {'type':'text','value':str(value)}
        payload = {'requests':[{'type':'execute','stmt':{'sql':sql,'args':[encode(v) for v in params]}},{'type':'close'}]}
        req = Request(self.endpoint, data=json.dumps(payload).encode(), headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        with urlopen(req, timeout=30) as response:
            result = json.load(response)['results'][0]
        if result['type'] == 'error':
            raise RuntimeError('Turso SQL request failed: '+result['error'].get('code', 'UNKNOWN'))
        return Cursor(result['response']['result'])
    def executescript(self, script):
        for sql in script.split(';'):
            if sql.strip(): self.execute(sql)
