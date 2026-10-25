"""Persistent local mode flag and bounded retrieval subprocess; no automated submission."""
import argparse,json,sqlite3,subprocess,sys,time
from common import ROOT
STATE=ROOT/'database/exam_state.json'
def health():
    db=ROOT/'database/questions.sqlite'
    conn=sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True)
    integrity=conn.execute('PRAGMA quick_check').fetchone()[0]
    total=conn.execute('SELECT count(*) FROM questions').fetchone()[0]
    verified=conn.execute("SELECT count(*) FROM questions WHERE status='VERIFIED'").fetchone()[0]
    bad=conn.execute("SELECT count(*) FROM questions WHERE status='VERIFIED' AND (answer IS NULL OR payload NOT LIKE '%answer_source%')").fetchone()[0]
    conn.close()
    if integrity!='ok' or bad or not total:raise RuntimeError('Database health validation failed')
    return {'integrity':integrity,'total':total,'verified':verified,'scope':'verified exact questions only; references and independent reasoning for the rest'}
def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['start','stop','status','lookup']);p.add_argument('--query-file');a=p.parse_args()
    if a.action=='start':
        status=health();state={'active':True,'started_at':time.time(),'target_seconds_per_question':30,'retrieval_subprocess_timeout_seconds':10,'health':status}
        STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(state,ensure_ascii=False));return
    if a.action=='stop':
        STATE.write_text(json.dumps({'active':False},ensure_ascii=False),encoding='utf-8');print('考试模式已退出');return
    state=json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {'active':False}
    if a.action=='status':print(json.dumps({'state':state,'health':health()},ensure_ascii=False));return
    if not state.get('active'):raise SystemExit('尚未进入考试模式。请运行 start。')
    if not a.query_file:raise SystemExit('lookup 需要 --query-file。')
    t0=time.monotonic()
    try:
        result=subprocess.run([sys.executable,str(ROOT/'scripts/search_questions.py'),'--query-file',a.query_file,'--budget','7'],capture_output=True,encoding='utf-8',timeout=10)
        if result.returncode:raise RuntimeError(result.stderr)
        output=json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        output={'decision':'RETRIEVAL_TIMEOUT','answer':None,'note':'检索子进程已超时终止，转独立推理；不猜造题库答案。'}
    output['remaining_target_seconds']=max(0,30-(time.monotonic()-t0))
    output['timing_scope']='Only local retrieval is programmatically bounded; chat input, model reasoning and network latency are outside this subprocess.'
    print(json.dumps(output,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
