"""Exact matching is the only automatic answer path. Fuzzy/LSA results are references."""
import argparse,json,sqlite3,time,re,sys
from common import ROOT,normalize,canonical,OPTION,safety_signature,strip_number

def query_parts(text):
    import unicodedata
    text=unicodedata.normalize('NFKC',text)
    hits=list(OPTION.finditer(text));options={}
    for i,m in enumerate(hits):
        if m.group(1) in options:return strip_number(text),{}
        options[m.group(1)]=text[m.end():hits[i+1].start() if i+1<len(hits) else len(text)].strip()
    return strip_number(text[:hits[0].start()] if hits else text),options

def map_answer(q,options):
    if q['verification_status']!='VERIFIED' or not q.get('correct_answer_content'):return None,'原始答案未通过对应关系核验或存在冲突'
    if q['time_sensitive']:return None,'题目有时效性，需先核查适用日期'
    if sorted(normalize(v) for v in options.values())!=sorted(normalize(v) for v in q['options'].values()):return None,'选项内容或数量不同'
    out=[]
    for content in q['correct_answer_content']:
        labels=[k for k,v in options.items() if normalize(v)==normalize(content)]
        if len(labels)!=1:return None,'答案选项内容无法唯一对应'
        out.append(labels[0])
    return sorted(out),None

def fts_expression(text):
    t=re.sub(r'[^\w\u4e00-\u9fff]','',normalize(text))
    grams=list(dict.fromkeys(t[i:i+3] for i in range(max(0,len(t)-2))))
    if not grams:return None
    step=max(1,len(grams)//18);grams=grams[::step][:20]
    return ' OR '.join('"'+g+'"' for g in grams)

def search(stem,options=None,limit=5,budget=8,semantic=True):
    t0=time.monotonic();deadline=t0+budget;options=options or {}
    conn=sqlite3.connect(f'file:{(ROOT/"database/questions.sqlite").as_posix()}?mode=ro',uri=True)
    conn.set_progress_handler(lambda:1 if time.monotonic()>deadline else 0,2000)
    results=[];direct=None
    try:
        exact=conn.execute('SELECT payload FROM questions WHERE stem_norm=?',(normalize(stem),)).fetchall()
        for row in exact:
            q=json.loads(row[0]);ans,reason=map_answer(q,options)
            r=pack(q,1,'exact_stem',ans,reason);results.append(r)
            if ans:direct=r
        if direct:return {'decision':'DIRECT_ORIGINAL','answer':direct['mapped_answer'],'match':direct,'elapsed_seconds':time.monotonic()-t0,'budget_seconds':budget}
        pool={r['question_id']:r for r in results}
        expr=fts_expression(stem)
        if expr and time.monotonic()<deadline:
            rows=conn.execute('SELECT q.payload FROM question_fts f JOIN questions q ON q.question_id=f.question_id WHERE question_fts MATCH ? ORDER BY bm25(question_fts) LIMIT 180',(expr,)).fetchall()
            from rapidfuzz.fuzz import ratio
            for row in rows:
                q=json.loads(row[0]);score=ratio(normalize(stem),normalize(q['question_text']))/100
                if q['question_id'] not in pool:pool[q['question_id']]=pack(q,score,'fuzzy_reference',None,'近似题仅供参考，必须独立核对条件并求解')
        if semantic and time.monotonic()<deadline-2 and (ROOT/'database/semantic_model.joblib').exists():
            import numpy as np,joblib
            from sklearn.preprocessing import normalize as vnorm
            from threadpoolctl import threadpool_limits
            model=joblib.load(ROOT/'database/semantic_model.joblib');vectors=np.load(ROOT/'database/semantic_vectors.npy',mmap_mode='r')
            with threadpool_limits(limits=1):
                v=vnorm(model['svd'].transform(model['vectorizer'].transform([stem])))[0];scores=vectors@v
            for idx in np.argsort(scores)[-limit:][::-1]:
                key=model['ids'][idx]
                if key not in pool:
                    q=json.loads(conn.execute('SELECT payload FROM questions WHERE question_id=?',(key,)).fetchone()[0])
                    pool[key]=pack(q,float(scores[idx]),'lsa_semantic_reference',None,'局部潜在语义相似，不代表同题')
        candidates=sorted(pool.values(),key=lambda r:(r['match_type']=='exact_stem',r['similarity']),reverse=True)[:limit]
        for c in candidates:
            c['condition_signature_equal']=safety_signature(stem)==safety_signature(c['question_text'])
        return {'decision':'REFERENCE_ONLY' if candidates else 'NO_MATCH','answer':None,'candidates':candidates,'elapsed_seconds':time.monotonic()-t0,'budget_seconds':budget,'note':'不得把候选答案作为本题标准答案；需独立判断。'}
    except sqlite3.OperationalError as e:
        return {'decision':'TIMEOUT_OR_DATABASE_ERROR','answer':None,'error':str(e),'elapsed_seconds':time.monotonic()-t0}
    finally:conn.close()

def pack(q,score,kind,answer,reason):
    keys=['question_id','question_text','question_type','options','correct_answer','correct_answer_content','source_explanation','ai_explanation','source_archive','source_file','source_location','answer_source','verification_status','verification_method','answer_match_method','review_reasons','time_sensitive','material_year_hints','context_before','answer_conflicts']
    result={k:q.get(k) for k in keys};result.update(similarity=score,match_type=kind,mapped_answer=answer,restriction=reason)
    result['all_sources']=[{k:s.get(k) for k in ['source_archive','source_file','source_location','correct_answer','verification_status']} for s in q.get('sources',[])]
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('query',nargs='?');p.add_argument('--query-file');p.add_argument('--limit',type=int,default=5);p.add_argument('--budget',type=float,default=8);p.add_argument('--no-semantic',action='store_true');p.add_argument('--reference',action='store_true');a=p.parse_args()
    if a.query_file:
        raw=open(a.query_file,encoding='utf-8-sig').read()
        try:
            obj=json.loads(raw);stem=obj.get('question_text',obj.get('stem',''));options=obj.get('options',{})
        except json.JSONDecodeError:stem,options=query_parts(raw)
    else:stem,options=query_parts(a.query or sys.stdin.read())
    if not stem.strip():raise SystemExit('请输入题目文字或 --query-file 文件。')
    if a.reference:
        conn=sqlite3.connect(ROOT/'database/questions.sqlite');expr=fts_expression(stem)
        rows=conn.execute('SELECT source_id,location,text FROM source_fts WHERE source_fts MATCH ? ORDER BY bm25(source_fts) LIMIT ?',(expr,a.limit)).fetchall() if expr else []
        print(json.dumps({'reference_passages':[{'source_id':s,'location':l,'text':t} for s,l,t in rows]},ensure_ascii=False,indent=2));return
    print(json.dumps(search(stem,options,a.limit,a.budget,not a.no_semantic),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
