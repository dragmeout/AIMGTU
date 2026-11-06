from pathlib import Path
import argparse,sys,time
p=argparse.ArgumentParser();p.add_argument('--ready',required=True);p.add_argument('--output',required=True);a=p.parse_args()
Path(a.ready).write_text('ready',encoding='utf-8');assert sys.stdin.readline().strip()=='GO'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.common import DATA,read_jsonl,write_json,file_sha
from src.orchestration.controller import Assistant
from bench_common import evaluate
ids={'C01','D02','M01','M03','R01','R02','R03','R04','R05','R06','L01','L02'}
cases=[c for c in read_jsonl(DATA/'evaluation/ab_cases.jsonl') if c['id'] in ids];records=[];app=Assistant()
try:
    for c in cases:
        r=app.ask(c['question'],'B');r.update(case_id=c['id'],metrics=evaluate(c,r));records.append(r)
        print(f'MEM {len(records)}/{len(cases)} {c["id"]}',flush=True)
finally:app.close()
write_json(a.output,{'status':'passed','queries':len(records),'variant':'B','records':records,
                    'corpus_sha256':file_sha(DATA/'documents/clean_documents.jsonl'),
                    'directory_sha256':file_sha(DATA/'tools/departments.json')})
