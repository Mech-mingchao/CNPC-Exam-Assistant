"""End-to-end CLI checks; restore inactive state even on failure."""
import json,subprocess,sys,time
from common import ROOT
def run_script(script,*args):
    t0=time.monotonic()
    result=subprocess.run([sys.executable,str(ROOT/'scripts'/script),*args],capture_output=True,encoding='utf-8',timeout=12)
    if result.returncode:raise RuntimeError(result.stderr+result.stdout)
    return json.loads(result.stdout),time.monotonic()-t0
def run():
    state=ROOT/'database/exam_state.json';saved=state.read_text(encoding='utf-8') if state.exists() else '{"active":false}'
    report={}
    try:
        status,_=run_script('exam_mode.py','start');report['database_health']=status['health']
        exact,elapsed=run_script('exam_mode.py','lookup','--query-file',str(ROOT/'examples/query.json'))
        assert exact['decision']=='DIRECT_ORIGINAL'
        report['exact_lookup']={'decision':exact['decision'],'elapsed_seconds_including_process_start':elapsed}
        reordered,elapsed=run_script('exam_mode.py','lookup','--query-file',str(ROOT/'examples/query_reordered.json'))
        assert reordered['decision']=='DIRECT_ORIGINAL'
        assert reordered['answer']!=exact['answer']
        report['reordered_lookup']={'decision':reordered['decision'],'mapped_answer':reordered['answer'],'elapsed_seconds_including_process_start':elapsed}
        changed=json.loads((ROOT/'examples/query.json').read_text(encoding='utf-8'));changed['question_text']+='（本题将条件调整为123456789秒，要求选择错误项）'
        cp=ROOT/'examples/query_changed.json';cp.write_text(json.dumps(changed,ensure_ascii=False,indent=2),encoding='utf-8')
        fuzzy,elapsed=run_script('search_questions.py','--query-file',str(cp),'--budget','7')
        assert fuzzy.get('answer') is None
        report['changed_conditions']={'decision':fuzzy['decision'],'direct_answer_withheld':True,'elapsed_seconds_including_process_start':elapsed}
    finally:
        state.write_text(saved,encoding='utf-8')
    report['state_restored']=json.loads(state.read_text(encoding='utf-8'))
    (ROOT/'reports/runtime_smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':run()
