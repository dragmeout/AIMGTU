from src.common import DATA,read_json,read_jsonl,file_sha
from src.security.policy import approved_url,normalize

class Directory:
    def __init__(self):
        data=read_json(DATA/'tools/departments.json');self.records=data['departments']
        assert data['corpus_sha256']==file_sha(DATA/'documents/clean_documents.jsonl')
        docs={d['document_id']:d for d in read_jsonl(DATA/'documents/clean_documents.jsonl')}
        self.by_id={r['id']:r for r in self.records}
        for r in self.records:
            doc=docs[r['id']];assert approved_url(r['source'])
            assert r['clean_sha256']==doc['clean_sha256'] and r['source']==doc['source']
            for f in r['fields'].values():assert doc['text'][f['start_char']:f['end_char']]==f['evidence']
    def matches(self,question):
        q=normalize(question)
        return [r['id'] for r in self.records if any(normalize(a) in q for a in r['aliases'])]
    def source(self,r):
        return {'id':'S1','document_id':r['id'],'title':r['title'],'url':r['source'],'pages':[],
                'date':r['date'],'fetched_at':r['fetched_at'],'cited':True,'origin':'structured_snapshot'}
    def get_contact_information(self,department_id):
        if department_id not in self.by_id:raise ValueError('unknown_department')
        r=self.by_id[department_id]
        fields='\n'.join(f['evidence'] for f in r['fields'].values())
        return {'answer':f"{r['title']}\n{fields}\n[S1]",'sources':[self.source(r)],'department_id':r['id'],
                'snapshot_warning':'Контакты взяты из сохранённого снимка, а не из онлайн-проверки.'}
    def find_department(self,department_id):
        if department_id not in self.by_id:raise ValueError('unknown_department')
        r=self.by_id[department_id]
        return {'answer':r['title']+' [S1]','sources':[self.source(r)],'department_id':r['id']}
