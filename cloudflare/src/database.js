export const SCHEMA = [
  `CREATE TABLE IF NOT EXISTS news (id INTEGER PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
   summary TEXT NOT NULL DEFAULT '', source TEXT NOT NULL, category TEXT NOT NULL,
   image_url TEXT, published_at TEXT NOT NULL, fetched_at TEXT NOT NULL)`,
  'CREATE INDEX IF NOT EXISTS news_date ON news(published_at DESC, id DESC)',
  'CREATE INDEX IF NOT EXISTS news_category ON news(category, published_at DESC)',
  `CREATE TABLE IF NOT EXISTS feed_status (feed_id INTEGER PRIMARY KEY, last_attempt_at TEXT,
   last_success_at TEXT, next_fetch_at TEXT, last_error TEXT, items_saved INTEGER DEFAULT 0)`,
];
export class DatabaseError extends Error {}
const initialized = new Map();
const encode = value => value == null ? {type:'null'} : typeof value === 'number'
  ? {type:Number.isInteger(value) ? 'integer' : 'float', value:Number.isInteger(value) ? String(value) : value}
  : {type:'text',value:String(value)};
const decode = value => value.type === 'null' ? null : ['integer','float'].includes(value.type) ? Number(value.value) : value.value;
export class TursoDatabase {
  constructor(env, fetcher = fetch) {
    const address = new URL(env.TURSO_DATABASE_URL || 'https://missing.invalid');
    if (!env.TURSO_DATABASE_URL || !env.TURSO_AUTH_TOKEN || !['https:','libsql:','turso:'].includes(address.protocol)) {
      throw new DatabaseError('Turso credentials are missing or invalid');
    }
    this.endpoint = `https://${address.host}/${env.TURSO_DATABASE_ENGINE === 'turso' ? 'v3' : 'v2'}/pipeline`;
    this.token = env.TURSO_AUTH_TOKEN;
    this.fetcher = (...args) => fetcher(...args);
  }
  async batch(statements) {
    const requests = statements.map(({sql,args=[]}) => ({type:'execute',stmt:{sql,args:args.map(encode)}}));
    requests.push({type:'close'});
    const response = await this.fetcher(this.endpoint, {
      method:'POST',headers:{Authorization:`Bearer ${this.token}`,'Content-Type':'application/json'},
      body:JSON.stringify({requests}),signal:AbortSignal.timeout(30000),
    });
    if (!response.ok) { await response.body?.cancel(); throw new DatabaseError(`Turso HTTP ${response.status}`); }
    const payload = await response.json();
    return statements.map((_,i) => {
      const result = payload.results?.[i];
      if (result?.type !== 'ok' || !result.response?.result) throw new DatabaseError('Turso SQL request failed');
      const data = result.response.result;
      return {rows:(data.rows || []).map(row => Object.fromEntries(data.cols.map((col,j) => [col.name,decode(row[j])]))), affected:data.affected_row_count || 0};
    });
  }
  async query(sql,args=[]) { return (await this.batch([{sql,args}]))[0]; }
  async ensureSchema() {
    const key = this.endpoint + this.token;
    if (!initialized.has(key)) {
      const pending = this.batch(SCHEMA.map(sql => ({sql}))).catch(error => { initialized.delete(key); throw error; });
      initialized.set(key,pending);
    }
    await initialized.get(key);
  }
}
