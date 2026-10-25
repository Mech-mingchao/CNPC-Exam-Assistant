"""Read-only originals; safe recursive ZIP extraction with reproducible provenance."""
from pathlib import Path
import zipfile, hashlib, json, shutil
ROOT = Path(__file__).resolve().parents[1]
INPUT = Path(r'E:\三桶油考试资料\【00】三桶油')
NAMES = ['中石油笔试通关资料1.zip','中石油笔试通关资料2_01.zip','中石油笔试通关资料2_02.zip','中石油笔试通关资料2_03.zip']
def digest(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''): h.update(b)
    return h.hexdigest()
def run():
    for d in ['original_archives','extracted','database','reports','scripts','cache','reviews']: (ROOT/d).mkdir(exist_ok=True)
    records=[]; archives=[]; errors=[]
    def unpack(path, dest, original, chain):
        dest.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                name=info.filename
                if not (info.flag_bits & 0x800):
                    try: name=name.encode('cp437').decode('gb18030')
                    except (UnicodeError,LookupError): pass
                target=(dest/name).resolve()
                if not target.is_relative_to(dest.resolve()):
                    errors.append({'archive':original,'file':name,'error':'unsafe path'}); continue
                if info.is_dir(): target.mkdir(parents=True,exist_ok=True); continue
                target.parent.mkdir(parents=True,exist_ok=True)
                if not target.exists() or target.stat().st_size!=info.file_size:
                    with z.open(info) as src,open(target,'wb') as out: shutil.copyfileobj(src,out)
                rec={'source_id':f'S{len(records)+1:04d}','source_archive':original,'archive_chain':chain,'source_file':name,'path':str(target),'type':target.suffix.lower(),'bytes':target.stat().st_size,'sha256':digest(target)}
                records.append(rec)
                if target.suffix.lower()=='.zip':
                    try: unpack(target,target.with_name(target.name+'_contents'),original,chain+[name])
                    except Exception as e: errors.append({'archive':original,'file':name,'error':str(e)})
    for name in NAMES:
        src=INPUT/name; dst=ROOT/'original_archives'/name
        if not dst.exists(): shutil.copy2(src,dst)
        h=digest(src)
        if digest(dst)!=h: raise ValueError('Archive copy hash mismatch: '+name)
        with zipfile.ZipFile(src) as z:
            archives.append({'name':name,'original_path':str(src),'sha256':h,'entries':len(z.infolist()),'file_count':sum(not i.is_dir() for i in z.infolist())})
        unpack(dst,ROOT/'extracted'/src.stem,name,[name])
    data={'archives':archives,'files':records,'errors':errors}
    (ROOT/'database/source_index.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'archives':len(archives),'files':len(records),'errors':errors},ensure_ascii=False))
if __name__=='__main__':run()
