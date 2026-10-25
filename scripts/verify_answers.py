"""Deduplicate by stem AND option content; record every original source and conflict."""
import json,collections,sqlite3,csv,re
from common import ROOT,normalize,canonical

def write_csv(path,rows,fields):
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def build():
    records=[json.loads(l) for l in (ROOT/'database/raw_questions.jsonl').read_text(encoding='utf-8').splitlines()]
    groups=collections.defaultdict(list)
    for q in records:groups[q['question_id']].append(q)
    unique=[];conflicts=[];unverified=[]
    for key,qq in groups.items():
        answers=collections.defaultdict(list)
        for q in qq:
            if q['correct_answer'] and all(c in q['options'] for c in q['correct_answer']):
                content=tuple(sorted(normalize(q['options'][c]) for c in q['correct_answer']))
                answers[content].append(q)
        best=max(qq,key=lambda q:(q['verification_status']=='VERIFIED',bool(q['correct_answer']),bool(q['source_explanation']),len(q['question_text'])))
        item=dict(best);item['sources']=qq;item['source_count']=len(qq)
        item['canonical_key']=canonical(item['question_text'],item['options'])
        item['answer_conflicts']=[]
        if len(answers)>1:
            item['verification_status']='CONFLICT';item['confidence']=0
            for content,occ in answers.items():
                conflict={'question_id':key,'answer_content':' | '.join(content),'occurrences':' | '.join(q['occurrence_id'] for q in occ),'source_files':' | '.join(q['source_file'] for q in occ)}
                conflicts.append(conflict);item['answer_conflicts'].append(conflict)
        # Equal labels across reordered options do not imply equal answer content.
        item['correct_answer_content']=[item['options'][c] for c in item['correct_answer']] if item['correct_answer'] and all(c in item['options'] for c in item['correct_answer']) else []
        if len({normalize(v) for v in item['options'].values()})!=len(item['options']):
            item['verification_status']='UNVERIFIED';item['review_reasons'].append('选项内容重复，无法唯一映射')
        if item['verification_status']!='VERIFIED':unverified.append({'question_id':key,'status':item['verification_status'],'reason':' | '.join(item['review_reasons']),'answer':item['correct_answer'],'source_file':item['source_file'],'source_location':item['source_location']})
        unique.append(item)
    with open(ROOT/'database/questions.jsonl','w',encoding='utf-8') as f:
        for q in unique:f.write(json.dumps(q,ensure_ascii=False)+'\n')
    write_csv(ROOT/'database/answer_conflicts.csv',conflicts,['question_id','answer_content','occurrences','source_files'])
    write_csv(ROOT/'database/unverified_questions.csv',unverified,['question_id','status','reason','answer','source_file','source_location'])
    inventory=json.loads((ROOT/'database/file_inventory.json').read_text(encoding='utf-8'))
    dbpath=ROOT/'database/questions.sqlite'
    conn=sqlite3.connect(dbpath)
    conn.executescript('''DROP TABLE IF EXISTS questions; DROP TABLE IF EXISTS question_fts; DROP TABLE IF EXISTS sources; DROP TABLE IF EXISTS source_units; DROP TABLE IF EXISTS source_fts;
    CREATE TABLE questions(question_id TEXT PRIMARY KEY, stem TEXT, stem_norm TEXT, canonical_key TEXT, status TEXT, answer TEXT, payload TEXT);
    CREATE INDEX idx_stem ON questions(stem_norm); CREATE INDEX idx_canonical ON questions(canonical_key);
    CREATE VIRTUAL TABLE question_fts USING fts5(question_id UNINDEXED, stem, options, tokenize='trigram');
    CREATE TABLE sources(source_id TEXT PRIMARY KEY, archive TEXT, source_file TEXT, status TEXT, payload TEXT);
    CREATE TABLE source_units(unit_id INTEGER PRIMARY KEY,source_id TEXT,location TEXT,method TEXT,text TEXT);
    CREATE VIRTUAL TABLE source_fts USING fts5(source_id UNINDEXED,location UNINDEXED,text,tokenize='trigram');''')
    for q in unique:
        conn.execute('INSERT INTO questions VALUES(?,?,?,?,?,?,?)',(q['question_id'],q['question_text'],normalize(q['question_text']),q['canonical_key'],q['verification_status'],q['correct_answer'],json.dumps(q,ensure_ascii=False)))
        conn.execute('INSERT INTO question_fts VALUES(?,?,?)',(q['question_id'],q['question_text'],' '.join(q['options'].values())))
    for rec in inventory:
        conn.execute('INSERT INTO sources VALUES(?,?,?,?,?)',(rec['source_id'],rec['source_archive'],rec['source_file'],rec['status'],json.dumps(rec,ensure_ascii=False)))
        cache=ROOT/'cache'/f'{rec["source_id"]}.json'
        if cache.exists():
            for u in json.loads(cache.read_text(encoding='utf-8'))['units']:
                conn.execute('INSERT INTO source_units(source_id,location,method,text) VALUES(?,?,?,?)',(rec['source_id'],u['location'],u['method'],u['text']))
                if len(normalize(u['text']))>=3:conn.execute('INSERT INTO source_fts VALUES(?,?,?)',(rec['source_id'],u['location'],u['text']))
    conn.commit();check=conn.execute('PRAGMA integrity_check').fetchone()[0];conn.close()
    stats={'archives':4,'files':len(inventory),'read_files':sum(x['status']=='read' for x in inventory),'failed_or_partial_files':sum(x['status']!='read' for x in inventory),'raw_questions':len(records),'unique_questions':len(unique),'unique_with_original_answer':sum(bool(x['correct_answer']) for x in unique),'unique_with_source_explanation':sum(bool(x['source_explanation']) for x in unique),'verified_unique':sum(x['verification_status']=='VERIFIED' for x in unique),'unverified_unique':sum(x['verification_status']=='UNVERIFIED' for x in unique),'conflict_unique':sum(x['verification_status']=='CONFLICT' for x in unique),'missing_answer_unique':sum(not x['correct_answer'] for x in unique),'ocr_units':sum(x.get('ocr_units',0) for x in inventory),'sqlite_integrity':check}
    (ROOT/'reports/statistics.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(stats,ensure_ascii=False))
if __name__=='__main__':build()
