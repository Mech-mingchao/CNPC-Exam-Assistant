from pathlib import Path
import re, unicodedata, hashlib
ROOT=Path(__file__).resolve().parents[1]
def normalize(text):
    text=unicodedata.normalize('NFKC',text or '')
    return re.sub(r'\s+','',text).replace('﹣','-').replace('−','-')
def canonical(stem,options):
    # Preserve negation, decimals, mathematical symbols and all option content.
    return normalize(stem)+'\x1f'+'\x1e'.join(sorted(normalize(v) for v in options.values()))
def qid(stem,options):return 'Q'+hashlib.sha256(canonical(stem,options).encode()).hexdigest()[:20]
OPTION=re.compile(r'(?<![A-Za-z])([A-H])\s*[.、:)]\s*')
QSTART=re.compile(r'(?m)^[ \t]*(?:第\s*(\d{1,4})\s*题[^\n]*|(\d{1,4})[ \t]*[.、](?!\d)[ \t]*|试题\s*(\d{1,4})\s*[:：.、]?\s*|例题\s*(\d{1,4})\s*[:：.、]?\s*)')
ANSWER=re.compile(r'(?:[【\[〖〔]\s*(?:参考)?(?:正确)?答案\s*[】\]〗〕]|(?:参考|正确)?答案\s*[:：]?\s*(?:是|为)?|本题(?:应)?选|故(?:正确)?(?:答案)?(?:为|选)|应选)\s*[:：]?\s*([A-H](?:\s*[,、，及和与]?\s*[A-H]){0,7})(?![a-zA-Z])')
EXPL=re.compile(r'(?:【\s*(?:答案)?解析\s*】|(?:答案)?解析\s*[:：]|【解答】)')
def safety_signature(text):
    t=normalize(text)
    return {'numbers':re.findall(r'[-+]?\d+(?:\.\d+)?[%‰]?',t),
            'negations':[(x,t.count(x)) for x in ['不正确','错误','不属于','不能','不可能','至少','至多','必然','可能','除外','不是','不符合','正确','属于','最大','最小']],
            'units':re.findall(r'千米|公里|米|小时|分钟|秒|万元|亿元|百分比|倍',t)}
def strip_number(text):
    return re.sub(r'^\s*(?:第\s*\d+\s*题[^\n]*\n|\d+[ \t]*[.、]\s*)','',text).strip()
