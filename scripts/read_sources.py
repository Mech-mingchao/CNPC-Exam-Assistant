"""Full document text extraction, page provenance and OCR audit trail. Resumable."""
from pathlib import Path
import json, re, sys, traceback, copy, zipfile
import fitz
from docx import Document
ROOT=Path(__file__).resolve().parents[1]
OCR=None
def needs_ocr(page,text):
    compact=re.sub(r'\s','',text)
    chinese=len(re.findall(r'[\u4e00-\u9fff]',text))
    weird=sum('\u0370'<=c<='\u1fff' for c in compact)
    image_area=sum(fitz.Rect(i['bbox']).get_area() for i in page.get_image_info())
    return (len(compact)<45 or text.count('\ufffd')>max(5,len(text)*.05)
            or (len(compact)>80 and chinese<8)
            or weird>max(12,len(compact)*.07)
            or (image_area>page.rect.get_area()*.5 and len(compact)<350))
def ocr_image(image):
    global OCR
    if OCR is None:
        from rapidocr_onnxruntime import RapidOCR
        OCR=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=2)
    result,_=OCR(image)
    result=result or []
    return '\n'.join(r[1] for r in result), [{'box':r[0],'text':r[1],'confidence':float(r[2])} for r in result]
def read(rec):
    p=Path(rec['path']); suffix=rec['type']; units=[]
    meta={'source_id':rec['source_id'],'status':'read','units':units,'errors':[]}
    if p.stat().st_size==0:
        meta.update(status='empty_file',characters=0,ocr_units=0)
        meta['errors']=[{'error':'Original ZIP entry is zero bytes; not a valid document.'}]
        return meta
    if suffix=='.pdf':
        with fitz.open(p) as doc:
            for n,page in enumerate(doc):
                text=page.get_text('text',sort=True)
                native=text
                method='native'; boxes=[]
                images=page.get_images(full=True)
                # Sparse/garbled native text can hide scanned text. OCR all such pages.
                chars=len(re.sub(r'\s','',text))
                if needs_ocr(page,text):
                    import numpy as np
                    pix=page.get_pixmap(matrix=fitz.Matrix(1.8,1.8),alpha=False)
                    arr=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,pix.n)
                    ocrtext,boxes=ocr_image(arr)
                    if len(ocrtext)>len(text): text=ocrtext; method='ocr'
                units.append({'location':f'page:{n+1}','text':text,'native_text':native if method=='ocr' else None,'method':method,'ocr_boxes':boxes,'image_count':len(images),'requires_visual_review':bool(images) or method=='ocr','width':page.rect.width,'height':page.rect.height})
                if (n+1)%100==0: print(f'{rec["source_id"]} page {n+1}/{len(doc)}',flush=True)
    elif suffix=='.doc':
        cache=ROOT/'cache'/f'{rec["source_id"]}.word.txt'
        if not cache.exists():
            meta['status']='pending_doc_conversion'; return meta
        text=cache.read_text(encoding='utf-8-sig').replace('\r','\n').replace('\x07','\t')
        for n,line in enumerate(text.splitlines()):
            units.append({'location':f'paragraph:{n+1}','text':line,'method':'word_com','requires_visual_review': '\x01' in line or '\x08' in line})
    elif suffix=='.docx':
        doc=Document(p)
        # Iterate body XML in document order, including tables and hyperlinks.
        for n,child in enumerate(doc.element.body):
            ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            text='\n'.join(''.join(t.text or '' for t in para.findall('.//w:t',ns)) for para in child.findall('.//w:p',ns)) if child.tag.endswith('}tbl') else ''.join(t.text or '' for t in child.findall('.//w:t',ns))
            units.append({'location':f'body_block:{n+1}','text':text,'method':'ooxml','requires_visual_review':bool(child.xpath('.//w:drawing'))})
        # Preserve text in embedded pictures via OCR; never follow document links.
        with zipfile.ZipFile(p) as z:
            for name in z.namelist():
                if name.startswith('word/media/'):
                    try:
                        import numpy as np, io
                        from PIL import Image
                        im=Image.open(io.BytesIO(z.read(name))).convert('RGB')
                        text,boxes=ocr_image(np.array(im))
                        units.append({'location':name,'text':text,'method':'ocr_embedded','ocr_boxes':boxes,'requires_visual_review':True})
                    except Exception as e: meta['errors'].append({'location':name,'error':str(e)})
    elif suffix in ['.png','.jpg','.jpeg','.tif','.tiff']:
        text,boxes=ocr_image(str(p))
        units.append({'location':'image:1','text':text,'method':'ocr','ocr_boxes':boxes,'requires_visual_review':True})
    elif suffix in ['.txt','.html','.htm','.csv']:
        raw=p.read_bytes()
        for enc in ['utf-8-sig','gb18030','utf-16']:
            try: text=raw.decode(enc);break
            except UnicodeError: continue
        units=[{'location':'line:1','text':text,'method':'text','requires_visual_review':False}]
    else:
        meta['status']='unsupported';meta['errors'].append({'error':'No parser for '+suffix})
    meta['characters']=sum(len(x['text']) for x in units)
    meta['ocr_units']=sum(x['method'].startswith('ocr') for x in units)
    meta['sparse_units']=[u['location'] for u in units if len(u['text'].strip())<10]
    if meta['errors']: meta['status']='partial'
    return meta
def run():
    sources=json.loads((ROOT/'database/source_index.json').read_text(encoding='utf-8'))['files']
    byhash={}
    for rec in sources:
        out=ROOT/'cache'/f'{rec["source_id"]}.json'
        if out.exists():
            old=json.loads(out.read_text(encoding='utf-8'))
            if old['status'] not in ['pending_doc_conversion','failed']: byhash[rec['sha256']]=out; continue
        try:
            if rec['sha256'] in byhash:
                data=json.loads(byhash[rec['sha256']].read_text(encoding='utf-8'));data['source_id']=rec['source_id'];data['duplicate_binary_of']=byhash[rec['sha256']].stem
            else: data=read(rec)
        except Exception as e: data={'source_id':rec['source_id'],'status':'failed','units':[],'errors':[{'error':str(e),'traceback':traceback.format_exc()}]}
        out.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        if data['status'] not in ['pending_doc_conversion','failed']: byhash[rec['sha256']]=out
        print(f'{rec["source_id"]} {data["status"]} units={len(data["units"])} chars={data.get("characters",0)} OCR={data.get("ocr_units",0)}',flush=True)
def repair_ocr():
    import numpy as np
    sources=json.loads((ROOT/'database/source_index.json').read_text(encoding='utf-8'))['files']
    repaired={}
    for rec in sources:
        out=ROOT/'cache'/f'{rec["source_id"]}.json'
        if rec['type']!='.pdf' or not out.exists():continue
        data=json.loads(out.read_text(encoding='utf-8'))
        if rec['sha256'] in repaired:
            data=json.loads(repaired[rec['sha256']].read_text(encoding='utf-8'));data['source_id']=rec['source_id']
        else:
            with fitz.open(rec['path']) as doc:
                for n,u in enumerate(data['units']):
                    if u['method']=='native' and needs_ocr(doc[n],u['text']):
                        pix=doc[n].get_pixmap(matrix=fitz.Matrix(1.8,1.8),alpha=False)
                        arr=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,pix.n)
                        text,boxes=ocr_image(arr)
                        u['native_text']=u['text'];u['text']=text;u['method']='ocr';u['ocr_boxes']=boxes;u['requires_visual_review']=True
                        print(f'OCR repaired {rec["source_id"]} page {n+1} chars={len(text)}',flush=True)
        data['characters']=sum(len(u['text']) for u in data['units'])
        data['ocr_units']=sum(u['method'].startswith('ocr') for u in data['units'])
        out.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');repaired[rec['sha256']]=out
if __name__=='__main__':
    if '--repair-ocr' in sys.argv:repair_ocr()
    else:run()
