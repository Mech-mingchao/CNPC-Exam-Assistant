"""Conservative extraction. Ambiguous links are retained as UNVERIFIED, never guessed."""
from pathlib import Path
import json,re,unicodedata,bisect,collections,csv,sqlite3,hashlib,difflib
from common import ROOT,normalize,canonical,qid,OPTION,QSTART,ANSWER,EXPL,strip_number

def clean(text):
    text=unicodedata.normalize('NFKC',text).replace('\r','\n')
    text=re.sub(r'(?<=[\u4e00-\u9fff])[ \t]+(?=[\u4e00-\u9fff])','',text)
    text=re.sub(r'\[\s*([A-H])\s*\]',lambda m:m[1]+'.',text)
    text=re.sub(r'(?m)(^[ \t]*)([a-h])(?=[ \t]*[.、:)])',lambda m:m[1]+m[2].upper(),text)
    # Remove promotional headers only; original raw units are preserved unchanged.
    text=re.sub(r'(?:各类国企|各类笔试|各类考试|包过各类|本资料仅限购买者)[^\n]*','',text)
    return text

def document(rec):
    p=ROOT/'cache'/f'{rec["source_id"]}.json'
    if not p.exists():return None
    d=json.loads(p.read_text(encoding='utf-8'))
    spans=[];parts=[];off=0
    for u in d['units']:
        s=clean(u['text'])+'\n\n'
        spans.append((off,off+len(s),u));parts.append(s);off+=len(s)
    return d,''.join(parts),spans

def location(spans,pos):
    starts=[s[0] for s in spans];i=max(0,bisect.bisect_right(starts,pos)-1)
    return spans[i][2]['location'] if spans else 'unknown'

def option_block(block):
    # Restrict options to before a labelled answer/explanation or answer-section heading.
    cutoff=len(block)
    for rx in [ANSWER,EXPL,re.compile(r'(?m)^\s*(?:参考答案|答案解析|答案与解析)\s*$')]:
        m=rx.search(block)
        if m:cutoff=min(cutoff,m.start())
    front=block[:cutoff];hits=list(OPTION.finditer(front))
    # Only one ordered option sequence is accepted.
    options={};first=None;used=[]
    for i,h in enumerate(hits):
        label=h.group(1)
        if first is None:
            if label!='A':continue
            first=h.start()
        if label in options:break
        end=hits[i+1].start() if i+1<len(hits) else len(front)
        options[label]=front[h.end():end].strip();used.append(h)
    if list(options)[:2]!=['A','B']:return None
    return {'stem':front[:first].strip(),'options':options,'cutoff':cutoff,'first':first,'matches':used}

def answer_from(block):
    m=ANSWER.search(block)
    if m:return ''.join(re.findall('[A-H]',m.group(1))),m.start(),m.end(),m.group(0)
    # Answer sections often use “17. B 【解析】...” without an answer label.
    m=re.match(r'^\s*(?:第\s*)?\d+\s*(?:题|[.、)])\s*(?:【解析】|解析[:：])?\s*([A-H](?:[ ,、，]*[A-H])*)\s*(?:[.。\s]|【解析】)',block)
    if m:return ''.join(re.findall('[A-H]',m.group(1))),m.start(1),m.end(1),m.group(0)
    return None

def extract(rec):
    loaded=document(rec)
    if not loaded:return [],[],{'status':'missing_cache'}
    d,text,spans=loaded
    boundaries=list(QSTART.finditer(text));questions=[];answer_records=[];covered=[]
    explicit=[m for m in boundaries if m.group(1)]
    if len(explicit)>=5:boundaries=explicit
    for i,m in enumerate(boundaries):
        end=boundaries[i+1].start() if i+1<len(boundaries) else len(text)
        block=text[m.start():end];op=option_block(block)
        num=next((x for x in m.groups() if x),None)
        full_a_count=len(re.findall(r'(?m)^[ \t]*A[ \t]*[.、:)]',block))
        if op and len(op['stem'])>=6 and len(block)<35000 and full_a_count<=1:
            stem=strip_number(op['stem'])
            # The “第1题，共105题” heading is metadata, not part of the stem.
            stem=re.sub(r'^第\s*\d+\s*题[^\n]*\n','',stem).strip()
            if len(stem)<3:continue
            questions.append(make_question(rec,d,spans,block,m.start(),end,stem,op,num))
            covered.append((m.start(),end))
        else:
            a=answer_from(block)
            if a:answer_records.append({'source_id':rec['source_id'],'original_number':num,'answer':a[0],'text':block,'offset':m.start(),'location':location(spans,m.start()),'answer_source':location(spans,m.start()+a[1])})
            else:
                # Retain explicit non-choice questions without inventing their answers.
                nonchoice=re.search(r'(?:【答案】|(?:参考|正确)?答案\s*[:：])\s*([^\n]+)',block)
                if nonchoice:
                    stem=strip_number(block[:nonchoice.start()]).strip()
                    if re.search(r'判断|填空|简答|问答|[?？]|_{2,}',stem) and 6<len(stem)<5000:
                        q=make_question(rec,d,spans,block,m.start(),end,stem,{'options':{},'cutoff':nonchoice.start()},num)
                        q['correct_answer']=nonchoice.group(1).strip();q['question_type']='判断' if re.search(r'正确|错误|判断|对错',stem+q['correct_answer']) else '填空或简答'
                        q['answer_source']={'source_id':rec['source_id'],'location':location(spans,m.start()+nonchoice.start()),'raw_text':nonchoice.group(0)}
                        q['answer_match_method']='explicit_nonchoice_answer';q['verification_status']='UNVERIFIED';q['confidence']=.7
                        q['review_reasons']=['非选择题保留原始答案，需逐题核验']
                        questions.append(q)
    # Unnumbered EPI collections: each A–D group followed by an explicit answer.
    # Recover only outside recognised numbered question ranges.
    anchors=list(re.finditer(r'(?m)^[ \t]*A\s*[.、:)]',text))
    last_stop=0
    for i,a in enumerate(anchors):
        if any(s<=a.start()<e for s,e in covered):continue
        nexta=anchors[i+1].start() if i+1<len(anchors) else len(text)
        tail=text[a.start():nexta]
        ans=ANSWER.search(tail)
        if not ans:continue
        # Stem is the paragraph preceding A. Keep multi-line wrapped stem intact.
        prefix=text[last_stop:a.start()].rstrip()
        blank=list(re.finditer(r'\n[ \t]*\n',prefix))
        start=last_stop+(blank[-1].end() if blank else 0)
        if a.start()-start>5000:start=max(last_stop,a.start()-5000)
        expl=EXPL.search(tail,ans.end())
        # End explanation at a blank paragraph before the following question.
        after=tail[ans.end():]
        breaks=list(re.finditer(r'\n[ \t]*\n',after))
        stop=a.start()+ans.end()+(breaks[-1].start() if breaks else len(after))
        block=text[start:stop];op=option_block(block)
        if op and len(op['options'])>=4 and 3<=len(op['stem'])<=5000:
            questions.append(make_question(rec,d,spans,block,start,stop,strip_number(op['stem']),op,None))
            last_stop=stop
    # Some MBTI questionnaires use bare question numbers and A/B without punctuation.
    # Their scoring columns must never be interpreted as correct answers.
    if not questions and 'MBTI' in rec['source_file']:
        traits=list(re.finditer(r'(?m)^[ \t]*(\d{1,3})[ \t]*(?:[.、][ \t]*|\n)',text))
        for i,m in enumerate(traits):
            end=traits[i+1].start() if i+1<len(traits) else len(text)
            block=text[m.end():end]
            aa=re.search(r'(?<![A-Za-z])A\s*[.、:]?\s*(?=[\u4e00-\u9fff])',block)
            bb=re.search(r'(?<![A-Za-z])B\s*[.、:]?\s*(?=[\u4e00-\u9fff])',block[aa.end():]) if aa else None
            if not aa or not bb:continue
            bstart=aa.end()+bb.start();bend=aa.end()+bb.end()
            btext=block[bend:]
            btext=re.split(r'(?m)^\s*[AB]\s*$|○',btext,maxsplit=1)[0].strip()
            stem=block[:aa.start()].strip()
            opts={'A':block[aa.end():bstart].strip(' ,，\n\t'),'B':btext}
            if not stem or not all(opts.values()):continue
            q=make_question(rec,d,spans,text[m.start():end],m.start(),end,stem,{'options':opts,'cutoff':len(text[m.start():end])},m.group(1))
            q.update(question_type='人格测评',correct_answer=None,source_explanation=None,explanation=None,answer_source=None,confidence=0,verification_status='UNVERIFIED',review_reasons=['人格测评无统一标准答案；评分列不作为正确答案'])
            questions.append(q)
    # Separate answer mapping uses original ID plus unique question within this document.
    bynum=collections.defaultdict(list);abynum=collections.defaultdict(list)
    for q in questions:
        if q['original_number']:bynum[q['original_number']].append(q)
    for a in answer_records:abynum[a['original_number']].append(a)
    for num,qs in bynum.items():
        aa=abynum[num]
        if len(qs)!=1 or len(aa)!=1:continue
        q=qs[0];a=aa[0]
        if q['correct_answer']:continue
        if not all(c in q['options'] for c in a['answer']):continue
        q['correct_answer']=a['answer'];q['answer_source']={'source_id':rec['source_id'],'location':a['answer_source'],'original_number':num,'raw_text':a['text'][:5000]}
        q['answer_match_method']='unique_original_number_same_document'
        q['source_explanation']=EXPL.split(a['text'],maxsplit=1)[-1].strip() if EXPL.search(a['text']) else None
        q['explanation']=q['source_explanation']
        q['confidence']=.6
        q['review_reasons'].append('集中答案仅题号唯一对应；尚缺逐题内容核对')
        # Original ID alone is insufficient. Require independent distinctive stem AND
        # selected-option quotations in the explanation plus explicit conclusion.
        exp=normalize(q['source_explanation'] or '')
        match=difflib.SequenceMatcher(None,normalize(q['question_text']),exp,autojunk=False).find_longest_match()
        quote=normalize(q['question_text'])[match.a:match.a+match.size]
        selected=[normalize(q['options'][c]) for c in a['answer']]
        conclusion=re.search(r'(?:故(?:本题)?(?:正确)?(?:答案)?(?:选|为)|正确答案(?:是|为)|答案(?:选|为))\s*'+re.escape(a['answer']),normalize(a['text']))
        remaining=[r for r in q['review_reasons'] if r not in ['没有可靠的本题内原始答案标签','集中答案仅题号唯一对应；尚缺逐题内容核对']]
        if match.size>=12 and all(len(v)>=4 and v in exp for v in selected) and conclusion and not remaining:
            q['verification_status']='VERIFIED';q['confidence']=.95
            q['verification_method']='unique_id_plus_distinctive_stem_and_selected_option_quotes_and_explicit_conclusion'
            q['verification_evidence']={'stem_quote':quote,'selected_option_quotes':selected,'conclusion':conclusion.group(0)}
            q['review_reasons']=[]
    return questions,answer_records,{'status':d['status'],'characters':d.get('characters',0),'units':len(d['units']),'ocr_units':d.get('ocr_units',0),'errors':d.get('errors',[]),'candidate_numbered_blocks':len(boundaries),'unclassified_numbered_blocks':len(boundaries)-sum(q['original_number'] is not None for q in questions)-len(answer_records)}

def make_question(rec,d,spans,block,start,end,stem,op,num):
    if '【例题】' in stem:stem=stem.split('【例题】',1)[1].lstrip(':： ').strip()
    relevant=[u for s,e,u in spans if e>start and s<end]
    ans=answer_from(block[op['cutoff']:]);anspos=op['cutoff']+(ans[1] if ans else 0)
    answer=ans[0] if ans else None
    expmatch=EXPL.search(block,op['cutoff'])
    explanation=block[expmatch.end():].strip() if expmatch else None
    if explanation and normalize(explanation) in ['略','无','暂无','暂无解析','解析略']:explanation=None
    reasons=[]
    if len(op['options'])<4 or any(not normalize(v) for v in op['options'].values()):reasons.append('选项缺失或为空')
    if any(c in block for c in ['\x01','\x08','\ufffd']):reasons.append('公式、图形或编码占位符')
    if any(u['method'].startswith('ocr') for u in relevant):reasons.append('OCR文本需对照原页核验')
    if re.search(r'如图|下图|图中|看图|上图|所示|图形|根据.{0,8}(?:资料|材料)|上述材料|根据上文|根据原文|表中|表格|下表|上表|文中|这段文字|这段话|根据定义',stem):
        # Long self-contained reading questions can be safe. Short references need context.
        if len(stem)<160 or re.search(r'图|表|上述材料|根据原文',stem):reasons.append('依赖图表、共用材料或上下文')
    if '图形' in rec['source_file']:reasons.append('图形题须对照原图及选项')
    if '性格' in rec['source_file'] or '人格' in rec['source_file']:reasons.append('人格或性格测评不设统一标准答案')
    if len(stem)>5000:reasons.append('题块可能包含额外说明')
    if len(normalize(stem))<12 and not re.search(r'[?？()（）_\d]',stem):reasons.append('题干过短或可能为被截断的子条目')
    if answer and not all(c in op['options'] for c in answer):reasons.append('答案字母不在选项中')
    if answer and len(set(answer))!=len(answer):reasons.append('答案含重复字母，可能是多题集中答案序列')
    if answer and len(answer)>len(op['options']):reasons.append('答案数量超过选项数量')
    if answer and len(answer)>1 and re.search(r'单项选择|单选题',block[:op['cutoff']]):reasons.append('单选题出现多字母答案')
    if len(re.findall(r'(?m)^[ \t]*A[ \t]*[.、:)]',block))>1:reasons.append('题块内包含多个选项组，边界需核验')
    if re.search(r'第[一二三四五六七八九十\d]+段|上文|原文|上题|下列材料|下列资料|与资料|根据材料|根据资料|该年度|该年|该地区|根据以上',stem):reasons.append('需要核对题干引用的共享材料')
    if re.search(r'\d[。]\d',' '.join(op['options'].values())):reasons.append('选项数字标点异常，需核对原文')
    variants=sorted(set(''.join(re.findall('[A-H]',m.group(1))) for m in ANSWER.finditer(block[op['cutoff']:])))
    if len(variants)>1:reasons.append('本题内答案标签或解析结论出现不同字母，需核验')
    if not answer:reasons.append('没有可靠的本题内原始答案标签')
    labels=list(op['options'])
    if labels!=list('ABCDEFGH')[:len(labels)]:reasons.append('选项顺序不连续')
    verified=bool(answer) and not reasons
    rawloc=location(spans,start);endloc=location(spans,max(start,end-1))
    q={'question_id':None,'occurrence_id':rec['source_id']+'_'+str(start),'source_id':rec['source_id'],'original_number':num,'question_text':stem,'question_type':'多选' if answer and len(answer)>1 else '单选' if len(op['options'])>=2 else '未知','options':op['options'],'correct_answer':answer,'explanation':explanation,'source_explanation':explanation,'ai_explanation':None,'source_archive':rec['source_archive'],'source_file':rec['source_file'],'source_location':rawloc if rawloc==endloc else rawloc+'..'+endloc,'source_offset':start,'answer_source':{'source_id':rec['source_id'],'location':location(spans,start+anspos),'raw_text':ans[3]} if ans else None,'confidence':.98 if verified else .7 if answer else 0,'verification_status':'VERIFIED' if verified else 'UNVERIFIED','verification_method':'automated_inline_label_and_option_integrity' if verified else None,'answer_match_method':'explicit_answer_in_same_question_block' if answer else None,'review_reasons':reasons,'material_year_hints':sorted(set(re.findall(r'20\d{2}',rec['source_file']))),'time_sensitive':bool(re.search(r'目前|今年|现任|最新|截至|现行|近期|本年',stem)),'raw_block':block,'source_methods':sorted(set(u['method'] for u in relevant)),'context_before':None}
    q['question_id']=qid(stem,op['options'])
    q['source_answer_variants']=variants
    if re.search(r'多选|多项选择',block[:op['cutoff']]):q['question_type']='多选'
    # Keep preceding source context for independent solving, never include it in exact matching.
    if any('依赖' in r for r in reasons):
        prior=[u['text'] for s,e,u in spans if e<=start][-3:]
        q['context_before']='\n'.join(prior)[-12000:]
    return q

def run():
    source=json.loads((ROOT/'database/source_index.json').read_text(encoding='utf-8'))
    allq=[];answers=[];inventory=[]
    for rec in source['files']:
        qs,aa,stats=extract(rec);allq.extend(qs);answers.extend(aa)
        inventory.append(dict(rec,**stats,questions=len(qs),answers=sum(bool(q['correct_answer']) for q in qs),explanations=sum(bool(q['source_explanation']) for q in qs)))
    (ROOT/'database/raw_questions.jsonl').write_text(''.join(json.dumps(q,ensure_ascii=False)+'\n' for q in allq),encoding='utf-8')
    (ROOT/'database/answer_records.jsonl').write_text(''.join(json.dumps(a,ensure_ascii=False)+'\n' for a in answers),encoding='utf-8')
    (ROOT/'database/file_inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'raw_questions':len(allq),'answer_records':len(answers),'files':len(inventory)},ensure_ascii=False))
if __name__=='__main__':run()
