from __future__ import annotations
import hashlib

def chunk_documents(documents,embedder,size,overlap=32):
    if overlap>=size:raise ValueError('overlap must be smaller than chunk size')
    chunks=[]
    for doc in documents:
        tokenized=embedder.tokenizer.encode(doc['text'],add_special_tokens=False)
        # encode() is never truncated. Offsets point back into the exact lab-2 text.
        offsets=tokenized.offsets
        if not offsets:continue
        start,number=0,1
        while start<len(offsets):
            end=min(start+size,len(offsets))
            a,b=offsets[start][0],offsets[end-1][1]
            text=doc['text'][a:b]
            # SentencePiece may segment the first word differently when it becomes
            # the start of a fragment. Enforce the size on the actual fragment.
            while embedder.token_count(text)>size and end>start+1:
                end-=1;b=offsets[end-1][1];text=doc['text'][a:b]
            if not text.strip():raise ValueError('Empty token span')
            blocks=[x for x in doc['blocks'] if x['start_char']<b and x['end_char']>a]
            fields=['document_id','document_title','source','date','date_basis','document_type','department','validity_status','allowed_use','education_level','fetched_at','source_updated_at','document_version','clean_sha256','topic']
            c={k:doc.get(k) for k in fields}
            c.update(chunk_id=f"{doc['document_id']}:e5t{size}:{number:04d}",text=text,
                     text_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),
                     start_char=a,end_char=b,chunk_tokens=embedder.token_count(text),
                     pages=sorted({p for block in blocks for p in block['pages']}),
                     section_paths=list(dict.fromkeys(tuple(x['section_path']) for x in blocks)))
            c['retrieval_text']=embedder.title(doc['document_title'])+'\n'+text
            chunks.append(c)
            if end==len(offsets):break
            start=max(start+1,end-overlap);number+=1
    return chunks
