# 中石油本地题库与限时辅助检索

已建立4个ZIP资料的持久化目录、逐页/逐段全文索引、标准题目候选、答案来源记录、去重及冲突清单。本批结果：16671条原始候选，去重10663条，其中2575条通过结构与来源映射检查。其余不能自动视为可信原题。当前未进入考试模式。

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
