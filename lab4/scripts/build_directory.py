from pathlib import Path
import re,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.common import DATA,read_json,read_jsonl,write_json,file_sha

def build():
    rules=read_json(ROOT/'config/directory_rules.json');docs={d['document_id']:d for d in read_jsonl(DATA/'documents/clean_documents.jsonl')};records=[]
    for id,aliases in rules.items():
        d=docs[id];fields={}
        for i,b in enumerate(d['blocks']):
            match=re.match(r'^(Адрес|Телефон|Часы при[её]ма|График работы)\s*:',b['text'],re.I)
            if match:
                key=match[1].casefold().replace('ё','е')
                end=b['end_char']
                if not b['text'].split(':',1)[1].strip() and i+1<len(d['blocks']):
                    following=d['blocks'][i+1]
                    if following['text'].startswith('- '):end=following['end_char']
                if key not in fields:fields[key]={'evidence':d['text'][b['start_char']:end],'start_char':b['start_char'],'end_char':end}
        if not fields:raise ValueError('No supported contact blocks: '+id)
        records.append({'id':id,'title':d['document_title'],'aliases':[d['document_title'],*aliases],
          'source':d['source'],'date':d['date'],'fetched_at':d['fetched_at'],'clean_sha256':d['clean_sha256'],'fields':fields})
    out={'corpus_documents':len(docs),'corpus_sha256':file_sha(DATA/'documents/clean_documents.jsonl'),
         'rules_sha256':file_sha(ROOT/'config/directory_rules.json'),'builder_sha256':file_sha(Path(__file__)),
         'scope':'Public department contacts only, extracted from frozen official university snapshots. No student records or live schedules.','departments':records}
    write_json(DATA/'tools/departments.json',out);print(f'Directory: {len(records)} departments; corpus: {len(docs)} documents')
if __name__=='__main__':build()
