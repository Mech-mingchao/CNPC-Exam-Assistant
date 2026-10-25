import json,hashlib,collections
from pathlib import Path
import pymupdf as fitz
from common import ROOT
from extract_archives import digest
from read_sources import needs_ocr
def run():
    src=json.loads((ROOT/'database/source_index.json').read_text(encoding='utf-8'))
    errors=[];pdf_pages=0;ocr_pages=0;missing_ocr=[]
    for a in src['archives']:
        for p in [Path(a['original_path']),ROOT/'original_archives'/a['name']]:
            if digest(p)!=a['sha256']:errors.append({'file':str(p),'error':'archive SHA256 mismatch'})
    for s in src['files']:
        if digest(Path(s['path']))!=s['sha256']:errors.append({'source_id':s['source_id'],'error':'extracted SHA256 mismatch'})
        cache=ROOT/'cache'/f'{s["source_id"]}.json'
        if not cache.exists():errors.append({'source_id':s['source_id'],'error':'no text cache'});continue
        d=json.loads(cache.read_text(encoding='utf-8'))
        if s['type']=='.pdf':
            with fitz.open(s['path']) as pdf:
                if len(pdf)!=len(d['units']):errors.append({'source_id':s['source_id'],'error':'PDF page count mismatch'})
                pdf_pages+=len(pdf)
                for n,u in enumerate(d['units']):
                    if u['method'].startswith('ocr'):ocr_pages+=1
                    elif needs_ocr(pdf[n],u['text']):missing_ocr.append({'source_id':s['source_id'],'page':n+1})
    report={'archive_hashes_verified':len(src['archives'])*2,'file_hashes_verified':len(src['files']),'pdf_pages':pdf_pages,'ocr_source_pages':ocr_pages,'missing_ocr':missing_ocr,'errors':errors}
    (ROOT/'reports/source_integrity.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    if errors or missing_ocr:raise SystemExit(1)
if __name__=='__main__':run()
