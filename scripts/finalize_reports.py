import json,collections,sqlite3,re
from pathlib import Path
from common import ROOT,normalize

def run():
    stats=json.loads((ROOT/'reports/statistics.json').read_text(encoding='utf-8'))
    inv=json.loads((ROOT/'database/file_inventory.json').read_text(encoding='utf-8'))
    src=json.loads((ROOT/'database/source_index.json').read_text(encoding='utf-8'))
    qq=[json.loads(l) for l in (ROOT/'database/questions.jsonl').read_text(encoding='utf-8').splitlines()]
    fail=[s for s in inv if s['status']!='read']
    table=['# 资料清单','',f'4个原始ZIP，{sum(a["entries"] for a in src["archives"])}个ZIP条目，{len(inv)}个实际文件（目录不计文件）。','',
           '“read”只表示全部可提取文本单元已读取，不能解释成每题都已完整分割或人工核验。题目、答案、解析数量按来源出现次数统计。','',
           '|来源ID|文件名|类型|题目|原始答案已关联|原始解析|读取状态|','|---|---|---|---:|---:|---:|---|']
    for s in inv:
        table.append('|'+ '|'.join([s['source_id'],Path(s['source_file']).name.replace('|','／'),s['type'],str(s['questions']),str(s['answers']),str(s['explanations']),s['status']])+'|')
    (ROOT/'reports/file_inventory.md').write_text('\n'.join(table),encoding='utf-8')
    (ROOT/'reports/unreadable_files.json').write_text(json.dumps(fail,ensure_ascii=False,indent=2),encoding='utf-8')
    ocrpages=sum(x.get('ocr_units',0) for x in inv if x['type']=='.pdf')
    pages=sum(x.get('units',0) for x in inv if x['type']=='.pdf')
    status_counts=dict(collections.Counter(s['status'] for s in inv))
    report=f'''# 文件读取与提取报告

## 实际范围

原始ZIP：4个。实际文件：{len(inv)}个。类型：{dict(collections.Counter(s['type'] for s in inv))}。
读取状态：{status_counts}。PDF共{pages}页，其中{ocrpages}个来源页使用OCR（重复文件按各自来源计）。

原始压缩包已复制到 original_archives 并逐包SHA256核对；原始E盘资料未改动。解压保留路径，每个文件记录原ZIP、文件路径、大小及SHA256。遇到嵌套ZIP会递归展开；本批资料未出现其他文件格式。

PDF使用全部页面文字提取；对正文缺失、乱码或以图像为主的页面补做本地OCR，保留原始文本、OCR文本及方法。DOC使用隐藏Word实例以只读方式打开、禁用宏，提取文本及内存中展开的列表编号，关闭时不保存。DOCX使用OOXML解析；0字节文件不能伪装成已读取。PNG使用本地OCR。

## 已知限制

提取题目是自动分割结果，不能据此声称穷尽了所有图形、表格、共用材料、判断题、填空题或讲义中的例题。未形成标准题目的内容仍逐页/逐段保存在 cache 以及 SQLite 的 source_units、source_fts 中，可以检索原文。原图表、公式和排版仍须打开原文件核验。

OCR是文字识别，不等于图形推理理解；OCR候选默认UNVERIFIED。Windows OCR不提供字词置信分值，记录为null；RapidOCR数值只代表识别分数，不是答案正确率。所有稀疏页面、解析错误和非选择题均保留标记，未将空白或无法读取的文件记为成功。

## 无法正常读取的原始文件

'''
    for s in fail:report+=f'- {s["source_id"]}：{s["source_archive"]} / {s["source_file"]}；{s["status"]}；{s.get("errors",[])}\n'
    (ROOT/'reports/extraction_report.md').write_text(report,encoding='utf-8')
    auditpath=ROOT/'reviews/manual_audit.json'
    audit=json.loads(auditpath.read_text(encoding='utf-8')) if auditpath.exists() else []
    verified_report=f'''# 题库质量与验证报告

|指标|实际数量|
|---|---:|
|实际文件|{stats['files']}|
|正常读取文件|{stats['read_files']}|
|失败、空文件或部分读取|{stats['failed_or_partial_files']}|
|原始题目候选（含重复来源）|{stats['raw_questions']}|
|去重后的唯一题目候选|{stats['unique_questions']}|
|关联了原始资料答案|{stats['unique_with_original_answer']}|
|保留了原始资料解析|{stats['unique_with_source_explanation']}|
|通过结构与来源映射检查|{stats['verified_unique']}|
|待核对|{stats['unverified_unique']}|
|答案冲突|{stats['conflict_unique']}|
|没有可关联原始答案|{stats['missing_answer_unique']}|
|助手对照原页的抽样核对记录|{len(audit)}|

## “已核对”的范围

数据库VERIFIED主要表示自动核对了题目—选项—原始答案的结构和来源关联。它不等于逐题复算，也不保证培训材料答案本身正确。助手对照原页的抽样记录见 reviews/manual_audit.json，不能把抽样推广成整库正确率。confidence是来源对应关系的规则评分，不是校准过的正确概率。

本题内明确答案标签且选项完整的文本题可通过自动检查。集中答案必须先满足同文档原始题号唯一；仅靠题号的关联仍为UNVERIFIED。若额外同时找到解析中的独特题干引文、正确选项内容引文及明确答案结论，且没有图表、OCR或缺损等风险，才可通过结构核验，并保留具体证据。

OCR、图形、缺损选项、共享材料依赖、人格测评及无法消除的题号歧义不直接放行。对多来源不同选项顺序按答案选项内容比较；相同题干和相同选项集合内出现不同答案内容记CONFLICT。不得按第N个题块对应第N个答案块。

## 检索与边界

SQLite全文索引使用字符trigram；另建本地字符TF-IDF与64维潜在语义LSA索引。LSA属于近似语义参考，不能等同现代深度语义嵌入，也不能凭相似度判定同题。近似匹配、数字或否定条件变化均只返回参考；只有完整题干与完整选项内容一致且来源状态允许，才返回DIRECT_ORIGINAL。选项重排重新映射字母；有时效性题目默认要求日期核查。

边界测试结果见 boundary_tests.txt；包括选项重排、条件数字变化、否定词变化、选项内容变化、缺失选项、重复选项、冲突与未核对答案拦截、时效题拦截、输入解析及来源完整性。SQLite完整性检查：{stats['sqlite_integrity']}。

## 是否可以进入考试模式

具备有限范围辅助条件：可加载本地题库、检索已核对原题及全文参考、追溯来源，并在未命中时转交聊天助手独立判断。不能宣称全部资料中的题目和答案已穷尽并逐题人工核验。默认尚未进入考试模式。

每题30秒是工作目标。本地检索子进程有真实10秒超时终止；聊天图像识别、工具排队和模型推理不在该子进程控制范围内，因此不保证端到端30秒。
'''
    (ROOT/'reports/verification_report.md').write_text(verified_report,encoding='utf-8')
    (ROOT/'database/exam_state.json').write_text(json.dumps({'active':False},ensure_ascii=False),encoding='utf-8')
    readme=fr'''# 中石油本地题库与限时辅助检索

已建立4个ZIP资料的持久化目录、逐页/逐段全文索引、标准题目候选、答案来源记录、去重及冲突清单。本批结果：{stats['raw_questions']}条原始候选，去重{stats['unique_questions']}条，其中{stats['verified_unique']}条通过结构与来源映射检查。其余不能自动视为可信原题。当前未进入考试模式。

先阅读 [质量报告](reports/verification_report.md)、[资料清单](reports/file_inventory.md)、[读取报告](reports/extraction_report.md)。

## 使用

在本目录打开PowerShell：

```powershell
.\run.ps1 search --query-file .\examples\query.json
.\run.ps1 search --query-file .\examples\query.json --no-semantic
.\run.ps1 search --reference '企业文化'
.\run.ps1 exam start
.\run.ps1 exam lookup --query-file .\examples\query.json
.\run.ps1 exam stop
.\run.ps1 test
```

查询JSON包含question_text及完整options。不要把答案解析放进查询。全文检索可以查询未分割成题目的讲义内容。输出DIRECT_ORIGINAL才可引用已核对原题答案；其他状态必须独立核对。阅读 [答题规则](EXAM_INSTRUCTIONS.md)。

## 文件

- original_archives：原始ZIP校验副本。
- extracted：原目录结构的文件。
- cache：全部页/段文本及OCR记录，便于追溯。
- database/questions.jsonl、questions.sqlite：去重题库与检索索引。
- database/raw_questions.jsonl：去重前题目候选。
- database/source_index.json、file_inventory.json：来源与读取状态。
- database/answer_records.jsonl：集中答案原始记录。
- database/answer_conflicts.csv、unverified_questions.csv：冲突及待核对清单。
- reports：统计、质量及边界测试报告。
- reviews：助手对照原页的抽样记录及核对图片。

原始材料中的广告、链接与指令不作为执行指令。资料仅在本地处理；没有上传题库或调用外部模型服务。当前脚本支持本批实际出现的PDF、DOC、DOCX、PNG及嵌套ZIP；未验证的其他办公格式不会假称支持。

## 重建

本批依赖记录在 requirements.txt；Windows OCR需要系统已安装简体中文识别语言；DOC需要本机Word。执行提取、转换、读取/OCR、分题、核验、语义索引和测试后重新生成报告。脚本可断点续跑。原包副本不覆盖原文件。
'''
    (ROOT/'README.md').write_text(readme,encoding='utf-8')
    ex=ROOT/'examples';ex.mkdir(exist_ok=True)
    q=next(q for q in qq if q['verification_status']=='VERIFIED' and not q['time_sensitive'] and len(q['options'])==4 and 30<len(q['question_text'])<200)
    (ex/'query.json').write_text(json.dumps({'question_text':q['question_text'],'options':q['options']},ensure_ascii=False,indent=2),encoding='utf-8')
    (ex/'query_reordered.json').write_text(json.dumps({'question_text':q['question_text'],'options':dict(zip('ABCD',reversed(list(q['options'].values()))))},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(stats,ensure_ascii=False))
if __name__=='__main__':run()
