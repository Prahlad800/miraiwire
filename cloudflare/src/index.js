import feedConfig from '../../backend/feeds.json' with {type:'json'};
import {TursoDatabase} from './database.js';
import {allFeeds,intervalMinutes,PROVIDERS,runScheduled} from './rss.js';
import {articleSeo,listingSeo} from './seo.js';
const IMAGE="image_url IS NOT NULL AND TRIM(image_url) != ''";
const headers={'Content-Type':'application/json; charset=utf-8','Access-Control-Allow-Origin':'*','Access-Control-Allow-Methods':'GET, OPTIONS','Access-Control-Allow-Headers':'Content-Type','X-Content-Type-Options':'nosniff','Cache-Control':'no-store'};
const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers});
class BadRequest extends Error {}
function pagination(params) {
  const rawPage=params.get('page') ?? '1',rawLimit=params.get('limit') ?? '20';
  if (!/^\d+$/.test(rawPage) || !/^\d+$/.test(rawLimit)) throw new BadRequest('Invalid request parameters');
  const page=Number(rawPage),limit=Number(rawLimit);
  if (!Number.isSafeInteger(page)||page<1||limit<1||limit>100||!Number.isSafeInteger((page-1)*limit)) throw new BadRequest('Invalid request parameters');
  return {page,limit};
}
const listResult=(data,total,page,limit)=>({data,page,limit,total,total_pages:Math.ceil(total/limit)});
export function createHandler({config=feedConfig,dbFactory=env=>new TursoDatabase(env)}={}) {
  return async function handler(request,env) {
    if(request.method==='OPTIONS') return new Response(null,{status:204,headers});
    if(request.method!=='GET') return json({error:'Method not allowed'},405);
    const {pathname:path,searchParams:params}=new URL(request.url);
    if(path==='/health') return json({status:'ok'});
    if(!['/ready','/api/v1/home','/api/v1/news/search','/api/v1/feeds','/api/v1/feeds/details'].includes(path) && !/^\/api\/v1\/news\/\d+(\/related)?$/.test(path)) return json({error:'Not found'},404);
    try {
      const db=dbFactory(env);
      await db.ensureSchema();
      if(path==='/ready') {
        const result=await db.query('SELECT COUNT(*) AS total FROM news');
        return json({status:'ready',database:'turso',news_count:result.rows[0].total});
      }
      if(path.startsWith('/api/v1/feeds')) {
        const states=(await db.query('SELECT * FROM feed_status')).rows;
        const lookup=new Map(states.map(state=>[state.feed_id,state]));
        const feeds=allFeeds(config);
        if(path.endsWith('/details')) {
          const data=feeds.map(feed=>{
            const state=lookup.get(feed.id)||{},minutes=intervalMinutes(feed,config);
            return {...feed,fetch_interval_minutes:minutes,last_attempt_at:state.last_attempt_at || null,last_success_at:state.last_success_at || null,
              next_fetch_at:state.last_attempt_at ? new Date(Date.parse(state.last_attempt_at)+minutes*60000).toISOString() : null,last_error:state.last_error || null,items_saved:state.items_saved || 0};
          });
          return json({data,total:data.length,language:config.language || 'en'});
        }
        const result={language:config.language || 'en'};
        for(const provider of PROVIDERS) {
          const group=feeds.filter(feed=>feed.provider===provider);
          const dates=group.map(feed=>lookup.get(feed.id)?.last_success_at).filter(Boolean).sort((a,b)=>Date.parse(a)-Date.parse(b));
          result[provider]={fetch_interval_minutes:intervalMinutes({provider},config),last_fetched_at:dates.at(-1)||null,
            feeds:group.map(({id,name,category,enabled,provider,language})=>({id,name,category,enabled,provider,language}))};
        }
        return json(result);
      }
      const match=path.match(/^\/api\/v1\/news\/(\d+)(\/related)?$/);
      if(match) {
        const id=Number(match[1]);
        if(!Number.isSafeInteger(id)) return json({error:'News not found'},404);
        const story=(await db.query(`SELECT * FROM news WHERE id=? AND ${IMAGE}`,[id])).rows[0];
        if(!story) return json({error:'News not found'},404);
        if(!match[2]) return json({data:story,seo:articleSeo(story,env)});
        const {page,limit}=pagination(params);
        const [count,rows]=await db.batch([
          {sql:`SELECT COUNT(*) AS total FROM news WHERE category=? AND id!=? AND ${IMAGE}`,args:[story.category,id]},
          {sql:`SELECT * FROM news WHERE category=? AND id!=? AND ${IMAGE} ORDER BY published_at DESC,id DESC LIMIT ? OFFSET ?`,args:[story.category,id,limit,(page-1)*limit]},
        ]);
        return json(listResult(rows.rows,count.rows[0].total,page,limit));
      }
      const {page,limit}=pagination(params), clauses=[IMAGE],args=[];
      const searching=path==='/api/v1/news/search', query=(params.get('q')||'').trim(),category=(params.get('category')||'').trim();
      if(searching) {
        if(!query||query.length>200) throw new BadRequest('q is required (1-200 characters)');
        const escaped=query.replace(/[\\%_]/g,value=>'\\'+value);
        clauses.push("(title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\')");
        args.push('%'+escaped+'%','%'+escaped+'%');
      }
      if(category){clauses.push('category=?');args.push(category);}
      const where=' WHERE '+clauses.join(' AND ');
      const [count,rows]=await db.batch([
        {sql:'SELECT COUNT(*) AS total FROM news'+where,args},
        {sql:'SELECT * FROM news'+where+' ORDER BY published_at DESC,id DESC LIMIT ? OFFSET ?',args:[...args,limit,(page-1)*limit]},
      ]);
      return json({...listResult(rows.rows,count.rows[0].total,page,limit),seo:listingSeo(rows.rows,env,category,searching ? query : '',page)});
    } catch(error) {
      if(error instanceof BadRequest) return json({error:error.message},400);
      console.error('Database request failed',error?.constructor?.name || 'Error');
      return path==='/ready' ? json({status:'unavailable'},503) : json({error:'Database temporarily unavailable'},503);
    }
  };
}
export default {
  fetch:createHandler(),
  async scheduled(controller,env,ctx) {
    const results=await runScheduled(new TursoDatabase(env),feedConfig,env);
    console.log('RSS scheduled fetch',JSON.stringify(results));
  },
};
