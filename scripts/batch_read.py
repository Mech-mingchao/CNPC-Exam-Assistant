"""Parallel local OCR with page checkpoints; no external service or model API."""
from pathlib import Path
import json, re, traceback, os, time,sys
from concurrent.futures import ProcessPoolExecutor, as_completed
import pymupdf as fitz
from read_sources import ROOT, needs_ocr, ocr_image, read

def page_ocr(job):
    key,path,n,output=job
    import numpy as np
    with fitz.open(path) as doc:
        pix=doc[n].get_pixmap(matrix=fitz.Matrix(1.6,1.6),alpha=False)
        arr=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,pix.n)
        text,boxes=ocr_image(arr)
    data={'text':text,'ocr_boxes':boxes,'method':'ocr','requires_visual_review':True}
    Path(output).write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    return key,n,len(text)

def run():
    sources=json.loads((ROOT/'database/source_index.json').read_text(encoding='utf-8'))['files']
    checkpoint=ROOT/'cache/ocr';checkpoint.mkdir(exist_ok=True)
    jobs={};items=[];native_byhash={}
    for rec in sources:
        output=ROOT/'cache'/f'{rec["source_id"]}.json'
        old=json.loads(output.read_text(encoding='utf-8')) if output.exists() else None
        try:
            if rec['type']=='.pdf':
                if rec['sha256'] in native_byhash:
                    data=json.loads(json.dumps(native_byhash[rec['sha256']],ensure_ascii=False));data['source_id']=rec['source_id']
                else:
                    data=old if old and old['status']=='read' else {'source_id':rec['source_id'],'status':'read','units':[],'errors':[]}
                    with fitz.open(rec['path']) as doc:
                        if not data['units']:
                            for n,page in enumerate(doc):
                                data['units'].append({'location':f'page:{n+1}','text':page.get_text('text',sort=True),'method':'native','image_count':len(page.get_images()),'requires_visual_review':bool(page.get_images())})
                        for n,u in enumerate(data['units']):
                            cp=checkpoint/f'{rec["sha256"]}_{n+1}.json'
                            if u['method']=='ocr' and not cp.exists():
                                cp.write_text(json.dumps({k:u[k] for k in ['text','ocr_boxes','method','requires_visual_review']},ensure_ascii=False),encoding='utf-8')
                            if cp.exists():
                                u['native_text']=u.get('native_text',u['text']);u.update(json.loads(cp.read_text(encoding='utf-8-sig')))
                            elif needs_ocr(doc[n],u['text']):
                                jobs[(rec['sha256'],n)]=(rec['sha256'],rec['path'],n,str(cp))
                    native_byhash[rec['sha256']]=data
            else:
                data=old if old and old['status'] not in ['pending_doc_conversion','failed'] else read(rec)
            data['characters']=sum(len(u['text']) for u in data['units'])
            output.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
            items.append((rec,output))
        except Exception as e:
            output.write_text(json.dumps({'source_id':rec['source_id'],'status':'failed','units':[],'errors':[{'error':str(e),'traceback':traceback.format_exc()}]},ensure_ascii=False),encoding='utf-8')
            print('FAILED',rec['source_id'],str(e),flush=True)
    print(f'Native extraction complete: {len(items)} files; unique OCR pages pending: {len(jobs)}',flush=True)
    failures=[];t0=time.monotonic()
    selected=[] if '--merge-only' in sys.argv else list(jobs.values())[:2] if '--probe' in sys.argv else list(jobs.values())
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(page_ocr,j):j for j in selected}
        for i,f in enumerate(as_completed(futures),1):
            try:
                key,n,chars=f.result()
                if i%10==0 or i==len(jobs):print(f'OCR {i}/{len(jobs)} elapsed={time.monotonic()-t0:.1f}s last_chars={chars}',flush=True)
            except Exception as e:
                failures.append({'job':futures[f],'error':str(e)})
                if len(failures)<4:print('OCR FAILED',str(e),flush=True)
    for rec,output in items:
        data=json.loads(output.read_text(encoding='utf-8'))
        if rec['type']=='.pdf':
            for n,u in enumerate(data['units']):
                cp=checkpoint/f'{rec["sha256"]}_{n+1}.json'
                if cp.exists():
                    u['native_text']=u.get('native_text',u['text']);u.update(json.loads(cp.read_text(encoding='utf-8-sig')))
        data['characters']=sum(len(u['text']) for u in data['units'])
        data['ocr_units']=sum(u['method'].startswith('ocr') for u in data['units'])
        data['sparse_units']=[u['location'] for u in data['units'] if len(u['text'].strip())<10]
        output.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    (ROOT/'cache/ocr_failures.json').write_text(json.dumps(failures,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'cache/ocr_coverage.json').write_text(json.dumps({'unique_pages_pending_at_start':len(jobs),'selected_jobs':len(selected),'failed_jobs':len(failures),'merge_only':'--merge-only' in sys.argv},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Finished files={len(items)} OCR_failures={len(failures)}',flush=True)
if __name__=='__main__':run()
