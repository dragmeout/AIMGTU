from __future__ import annotations
import time
from pathlib import Path
import faiss
import numpy as np
from src.common import ROOT,DATA,read_json,read_jsonl,write_json,write_jsonl,file_sha
from .chunking import chunk_documents

CORPUS=DATA/'documents/clean_documents.jsonl'

def index_path(size):return DATA/'indices'/f'e5_{size}'

def build_index(embedder,size,force=False):
    path=index_path(size);meta_path=path/'manifest.json';corpus_sha=file_sha(CORPUS)
    if meta_path.exists() and not force:
        m=read_json(meta_path)
        if m['corpus_sha256']==corpus_sha and m['chunker_sha256']==file_sha(Path(__file__).with_name('chunking.py')) and m['embedding_code_sha256']==file_sha(ROOT/'src/embeddings/e5.py'):
            return VectorStore(path)
    path.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter()
    docs=read_jsonl(CORPUS);chunks=chunk_documents(docs,embedder,size)
    vectors=embedder.encode([c['retrieval_text'] for c in chunks])
    if vectors.shape!=(len(chunks),384) or not np.isfinite(vectors).all():raise ValueError('Invalid embeddings')
    index=faiss.IndexFlatIP(384);index.add(vectors)
    faiss.write_index(index,str(path/'vectors.faiss'));write_jsonl(path/'chunks.jsonl',chunks)
    write_json(meta_path,{'corpus_sha256':corpus_sha,'chunker_sha256':file_sha(Path(__file__).with_name('chunking.py')),
                         'chunk_tokens':size,'overlap_tokens':32,'documents':len(docs),'chunks':len(chunks),
                         'dimensions':384,'distance':'inner_product_of_L2_normalized_vectors',
                         'embedding_model':'intfloat/multilingual-e5-small','revision':'614241f622f53c4eeff9890bdc4f31cfecc418b3',
                         'embedding_onnx_sha256':'ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665',
                         'embedding_code_sha256':file_sha(ROOT/'src/embeddings/e5.py'),
                         'seconds':round(time.perf_counter()-start,3),
                         'index_sha256':file_sha(path/'vectors.faiss'),'chunks_sha256':file_sha(path/'chunks.jsonl')})
    return VectorStore(path)

class VectorStore:
    def __init__(self,path):
        self.path=Path(path);self.manifest=read_json(self.path/'manifest.json')
        for name,key in [('vectors.faiss','index_sha256'),('chunks.jsonl','chunks_sha256')]:
            if file_sha(self.path/name)!=self.manifest[key]:raise ValueError('Index/checksum mismatch; rebuild index')
        self.chunks=read_jsonl(self.path/'chunks.jsonl');self.index=faiss.read_index(str(self.path/'vectors.faiss'))
        if self.index.ntotal!=len(self.chunks):raise ValueError('Index/chunk count mismatch')
    def search(self,query_vector,k):
        if not 1<=k<=len(self.chunks):raise ValueError('Invalid top-k')
        scores,ids=self.index.search(np.asarray(query_vector,dtype=np.float32).reshape(1,-1),k)
        return [{**self.chunks[int(i)],'score':float(s)} for s,i in zip(scores[0],ids[0])]
