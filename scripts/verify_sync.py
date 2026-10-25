"""Verify the synchronized original files and complete database mapping, read-only.

Python 3.10+; standard library only. This script does not rebuild the database.
"""
from pathlib import Path
import argparse,collections,hashlib,json,sqlite3,sys

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()

def verify(root):
    manifest=json.loads((root/'reports/sync_integrity_manifest.json').read_text(encoding='utf-8'))
    errors=[];checked=0
    for item in manifest['original_files']:
        path=root/item['path']
        if not path.resolve().is_relative_to(root.resolve()):raise ValueError('Invalid manifest path')
        if not path.is_file():errors.append({'path':item['path'],'reason':'missing'});continue
        if path.stat().st_size!=item['bytes'] or sha(path)!=item['sha256']:
            errors.append({'path':item['path'],'reason':'size or SHA256 mismatch; ensure git lfs pull completed'})
        checked+=1
    if errors:return {'passed':False,'checked_files':checked,'errors':errors}
    db=root/'database/questions.sqlite';baseline=manifest['database_baseline'];db_hash=sha(db)
    conn=sqlite3.connect(f'file:{db.as_posix()}?mode=ro&immutable=1',uri=True)
    integrity=[r[0] for r in conn.execute('PRAGMA integrity_check')]
    digest=hashlib.sha256();seen=set();counts=collections.Counter();mismatches=[]
    with (root/'database/questions.jsonl').open(encoding='utf-8') as f:
        for line in f:
            q=json.loads(line);key=q['question_id']
            if key in seen:mismatches.append({'question_id':key,'reason':'duplicate ID'})
            seen.add(key)
            row=conn.execute('SELECT payload,stem,answer,status FROM questions WHERE question_id=?',(key,)).fetchone()
            if not row or json.loads(row[0])!=q or (row[1],row[2],row[3])!=(q['question_text'],q['correct_answer'],q['verification_status']):
                mismatches.append({'question_id':key,'reason':'SQLite/JSONL full payload mismatch'})
            digest.update(json.dumps(q,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8'));digest.update(b'\n')
            counts['questions']+=1;counts[q['verification_status']]+=1
            counts['with_original_answer']+=bool(q['correct_answer']);counts['with_original_explanation']+=bool(q['source_explanation'])
    sqlcount=conn.execute('SELECT count(*) FROM questions').fetchone()[0];conn.close()
    actual={'integrity':integrity,'sqlite_questions':sqlcount,'jsonl_questions':len(seen),'payload_mismatches':len(mismatches),'database_sha256':db_hash,'jsonl_sha256':sha(root/'database/questions.jsonl'),'complete_payload_sequence_sha256':digest.hexdigest(),'counts':dict(counts)}
    if actual!=baseline:errors.append({'reason':'database baseline mismatch','actual':actual,'expected':baseline})
    if sha(db)!=db_hash:errors.append({'reason':'database changed during verification'})
    return {'passed':not errors and not mismatches,'checked_original_files':checked,'database':actual,'errors':errors,'payload_mismatches':mismatches,'verification_scope':'byte-identical original files plus complete question/options/answer/explanation/source records; not independent proof of answer correctness'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--output',type=Path);a=p.parse_args()
    result=verify(a.root.resolve());text=json.dumps(result,ensure_ascii=False,indent=2)
    if a.output:a.output.write_text(text,encoding='utf-8')
    print(text)
    return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
