from pathlib import Path
import json,sys
import pymupdf as fitz
from common import ROOT
from read_sources import needs_ocr
def run():
    sources=json.loads((ROOT/'database/source_index.json').read_text(encoding='utf-8'))['files']
    dest=ROOT/'cache/ocr';dest.mkdir(exist_ok=True)
    images=ROOT/'cache/ocr_rendering';images.mkdir(exist_ok=True)
    jobs={}
    for rec in sources:
        if rec['type']!='.pdf':continue
        cache=ROOT/'cache'/f'{rec["source_id"]}.json'
        data=json.loads(cache.read_text(encoding='utf-8'))
        with fitz.open(rec['path']) as doc:
            for n,u in enumerate(data['units']):
                key=f'{rec["sha256"]}_{n+1}';out=dest/f'{key}.json'
                redo='--redo-windows' in sys.argv and out.exists() and json.loads(out.read_text(encoding='utf-8-sig')).get('method')=='ocr_windows' and json.loads(out.read_text(encoding='utf-8-sig')).get('reading_order')!='row_then_x_v2'
                if not redo and (out.exists() or u['method'].startswith('ocr')):continue
                if needs_ocr(doc[n],u['text']):
                    image=images/f'{key}.jpg'
                    if not image.exists():
                        # Windows OCR expects each side <= its documented engine limit (2600 here).
                        scale=min(2.0,2400/max(doc[n].rect.width,doc[n].rect.height))
                        doc[n].get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False).save(image,jpg_quality=90)
                    jobs[key]={'image':str(image),'output':str(out),'source_id':rec['source_id'],'page':n+1}
                    if '--probe' in sys.argv and len(jobs)>=2:break
        if '--probe' in sys.argv and len(jobs)>=2:break
    path=ROOT/'cache/windows_ocr_jobs.json'
    path.write_text(json.dumps(list(jobs.values()),ensure_ascii=False,indent=2),encoding='utf-8')
    print('Windows OCR jobs',len(jobs),flush=True)
if __name__=='__main__':run()
