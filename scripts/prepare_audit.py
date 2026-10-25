import json,re
from pathlib import Path
import pymupdf as fitz
from common import ROOT
def run():
    selected=json.loads((ROOT/'reviews/audit_selection.json').read_text(encoding='utf-8'))
    src={x['source_id']:x for x in json.loads((ROOT/'database/source_index.json').read_text(encoding='utf-8'))['files']}
    paths=[]
    for q in selected:
        if src[q['source_id']]['type']!='.pdf':continue
        page=int(re.search(r'page:(\d+)',q['source_location']).group(1))
        out=ROOT/'reviews'/f'{q["source_id"]}_page_{page}.png'
        with fitz.open(src[q['source_id']]['path']) as d:d[page-1].get_pixmap(matrix=fitz.Matrix(1.4,1.4),alpha=False).save(out)
        paths.append(str(out))
    print(json.dumps(paths,ensure_ascii=False,indent=2))
if __name__=='__main__':run()
