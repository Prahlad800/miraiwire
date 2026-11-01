import { XMLParser, XMLValidator } from 'fast-xml-parser';
import { franc } from 'franc-min';
export const PROVIDERS=['google_news','the_hindu','bbc'];
export function allFeeds(config) {return PROVIDERS.flatMap(provider => (config[provider]?.feeds || []).map(feed => ({...feed,provider,language:config.language || 'en'})));}
export function intervalMinutes(feed,config) {
  const value=Number(feed.fetch_interval_minutes ?? config[feed.provider]?.fetch_interval_minutes ?? 30);
  if (!Number.isFinite(value) || value<1) throw new Error('Invalid feed interval');
  return value;
}
const array=value => value == null ? [] : Array.isArray(value) ? value : [value];
const text=value => typeof value==='object' && value!==null ? String(value['#text'] || '') : String(value || '');
export const plain=value => text(value).replace(/<[^>]*>/g,'').replace(/&nbsp;/g,' ').replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&#39;/g,"'").trim();
const httpUrl=(value,base) => {try {const u=new URL(value,base); return ['http:','https:'].includes(u.protocol) ? u.href : null;} catch {return null;}};
export function imageFromEntry(entry,link) {
  const candidates=[];
  for (const item of array(entry['media:content'])) {
    if (item['@_medium']==='video' || /^(video|audio)\//.test(item['@_type'] || '')) continue;
    candidates.push(item['@_url']);
  }
  candidates.push(...array(entry['media:thumbnail']).map(item => item['@_url']));
  candidates.push(...array(entry.enclosure).filter(item => /^image\//.test(item['@_type'] || '')).map(item => item['@_url']));
  candidates.push(...array(entry.link).filter(item => item['@_rel']==='enclosure' && /^image\//.test(item['@_type'] || '')).map(item => item['@_href']));
  for (const markup of [entry.description,entry.summary,entry['content:encoded'],entry.content]) {
    const re=/<img\b[^>]*?\s(?:src|data-src)\s*=\s*["']([^"']+)["']/gi;
    for (const match of text(markup).matchAll(re)) candidates.push(match[1]);
  }
  return candidates.filter(Boolean).map(value => httpUrl(value,link)).find(Boolean) || null;
}
export function parseFeed(xml,feed,{englishOnly=true,maxItems=50,now=new Date()}={}) {
  // Reject DTDs/custom entities before parsing untrusted RSS.
  if (/<!DOCTYPE|<!ENTITY/i.test(xml) || XMLValidator.validate(xml)!==true) throw new Error('Invalid RSS/Atom response');
  const doc=new XMLParser({ignoreAttributes:false,processEntities:true,parseTagValue:false}).parse(xml);
  const channel=doc.rss?.channel || doc.feed;
  if (!channel) throw new Error('Invalid RSS/Atom response');
  const declared=text(channel.language || doc.feed?.['@_xml:lang']);
  if (englishOnly && declared && !/^en(?:[-_]|$)/i.test(declared)) return [];
  const rows=[];
  for (const entry of array(channel.item || channel.entry).slice(0,maxItems)) {
    const title=plain(entry.title);
    const rawLink=typeof entry.link==='string' ? entry.link : array(entry.link).find(item => !item['@_rel'] || item['@_rel']==='alternate')?.['@_href'];
    const url=httpUrl(rawLink);
    const summary=plain(entry.description || entry.summary || entry['content:encoded'] || entry.content);
    const image_url=imageFromEntry(entry,url);
    if (!title || !url || !image_url) continue;
    if (englishOnly && franc((title+' '+summary).slice(0,600),{minLength:10})!=='eng') continue;
    const date=new Date(text(entry.pubDate || entry.published || entry.updated));
    rows.push({title,url,summary,source:plain(entry.source) || feed.name,category:feed.category,image_url,
      published_at:Number.isNaN(date.getTime()) ? now.toISOString() : date.toISOString(),fetched_at:now.toISOString()});
  }
  return rows;
}
async function readBounded(response,limit=1_000_000) {
  if (!response.ok) {await response.body?.cancel(); throw new Error(`RSS HTTP ${response.status}`);}
  const reader=response.body.getReader(), chunks=[]; let size=0;
  try {
    while (true) {const {done,value}=await reader.read(); if (done) break; size+=value.byteLength; if(size>limit) throw new Error('RSS exceeds 1 MB'); chunks.push(value);}
  } finally {await reader.cancel().catch(()=>{});}
  const bytes=new Uint8Array(size); let offset=0;
  for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
  return new TextDecoder().decode(bytes);
}
export async function runScheduled(db,config,env,fetcher=fetch,now=new Date()) {
  await db.ensureSchema();
  const statuses=(await db.query('SELECT * FROM feed_status')).rows;
  const state=new Map(statuses.map(row=>[row.feed_id,row]));
  const due=allFeeds(config).filter(feed => feed.enabled && (!state.get(feed.id)?.last_attempt_at ||
    Date.parse(state.get(feed.id).last_attempt_at)+intervalMinutes(feed,config)*60000<=now.getTime()));
  // Oldest due first prevents starvation; one feed per tick by default fits a small Cron budget.
  due.sort((a,b)=>(Date.parse(state.get(a.id)?.last_attempt_at) || 0)-(Date.parse(state.get(b.id)?.last_attempt_at) || 0) || a.id-b.id);
  const cap=Math.min(4,Math.max(1,Number(env.RSS_MAX_FEEDS_PER_RUN) || 1));
  const results=[];
  for (const feed of due.slice(0,cap)) {
    const attempted=now.toISOString(),minutes=intervalMinutes(feed,config), next=new Date(now.getTime()+minutes*60000).toISOString();
    // Atomic claim prevents overlapping Cron invocations from ingesting the same due feed.
    const claim=await db.query(`INSERT INTO feed_status(feed_id,last_attempt_at,next_fetch_at) VALUES(?,?,?)
      ON CONFLICT(feed_id) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,next_fetch_at=excluded.next_fetch_at
      WHERE feed_status.last_attempt_at IS NULL OR julianday(feed_status.last_attempt_at)<=julianday(?) RETURNING feed_id`,
      [feed.id,attempted,next,new Date(now.getTime()-minutes*60000).toISOString()]);
    if (!claim.rows.length) continue;
    let saved=0,error=null;
    try {
      const response=await fetcher(feed.url,{headers:{'User-Agent':'MiraiwireRSS/1.0'},signal:AbortSignal.timeout(15000)});
      const xml=await readBounded(response);
      const rows=parseFeed(xml,feed,{englishOnly:env.RSS_ENGLISH_ONLY!=='false',maxItems:Math.min(100,Number(env.RSS_MAX_ITEMS_PER_FEED)||50),now});
      if (rows.length) {
        const results=await db.batch(rows.map(row=>({sql:`INSERT INTO news(title,url,summary,source,category,image_url,published_at,fetched_at)
          VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET image_url=excluded.image_url
          WHERE news.image_url IS NULL OR TRIM(news.image_url)=''`,args:Object.values(row)})));
        saved=results.reduce((sum,result)=>sum+result.affected,0);
      }
    } catch (failure) {
      error=failure instanceof Error && !failure.message.includes('token') ? failure.message.slice(0,160) : 'Feed fetch failed';
    }
    await db.query(`UPDATE feed_status SET last_success_at=CASE WHEN ? IS NULL THEN ? ELSE last_success_at END,
      last_error=?,items_saved=? WHERE feed_id=?`,[error,attempted,error,saved,feed.id]);
    results.push({feed_id:feed.id,saved,error});
  }
  return results;
}
