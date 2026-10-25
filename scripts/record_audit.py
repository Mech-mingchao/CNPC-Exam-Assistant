"""Record the source-page comparisons actually performed in this build session."""
import json,re
from common import ROOT,normalize
def run():
    qs=[json.loads(l) for l in (ROOT/'database/raw_questions.jsonl').read_text(encoding='utf-8').splitlines()]
    selected=json.loads((ROOT/'reviews/audit_selection.json').read_text(encoding='utf-8'))
    audit=[]
    for old in selected:
        matches=[q for q in qs if q['source_id']==old['source_id'] and q['source_location']==old['source_location'] and sorted(normalize(v) for v in q['options'].values())==sorted(normalize(v) for v in old['options'].values())]
        if not matches:continue
        q=matches[0]
        result='WITHHELD_CONTEXT_REQUIRED' if q['source_id']=='S0005' else 'SOURCE_MAPPING_CONFIRMED'
        notes='已对照原页，题目引用前置图表；必须保持待核对状态。' if result.startswith('WITHHELD') else '已对照保存的原始PDF页，核对题干、选项内容、原始答案及本题解析的对应关系；未声称证明原答案客观正确。'
        if q['source_id']=='S0089':notes+='抽样发现的(1)分句编号丢失已修正并加入回归测试。'
        audit.append(entry(q,result,notes))
    supplementary=[('S0087',None,'3441465667','D'),('S0087',None,'(4,13)(7,22)(10,31)(13,40)','B'),('S0135','2',None,'A'),('S0135','3',None,'A'),('S0135','4',None,'A'),('S0091',None,'并非一切中药都是苦味的','A')]
    for sid,num,contains,answer in supplementary:
        candidates=[q for q in qs if q['source_id']==sid and (num is None or q['original_number']==num) and (contains is None or normalize(contains) in normalize(q['question_text'])) and q['correct_answer']==answer]
        if candidates:audit.append(entry(candidates[0],'SOURCE_MAPPING_CONFIRMED','与本次已查看的原页逐项对照；属于来源对应关系核对，不代表整库正确率。'))
    (ROOT/'reviews/manual_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Recorded source-page audit comparisons:',len(audit))
def entry(q,result,notes):
    m=re.search(r'page:(\d+)',q['source_location']);page=m.group(1) if m else ''
    return {'question_id':q['question_id'],'occurrence_id':q['occurrence_id'],'source_id':q['source_id'],'source_archive':q['source_archive'],'source_file':q['source_file'],'source_location':q['source_location'],'question_text':q['question_text'],'options':q['options'],'original_answer':q['correct_answer'],'source_explanation':q['source_explanation'],'result':result,'notes':notes,'reviewer':'Codex source-page visual inspection','image':str(ROOT/'reviews'/f'{q["source_id"]}_page_{page}.png') if page else None}
if __name__=='__main__':run()
