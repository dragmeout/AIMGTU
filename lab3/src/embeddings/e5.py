from __future__ import annotations
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer
from src.common import MODEL_DIR

class E5Embedding:
    """Pinned official E5 ONNX; masked mean pooling + L2 normalization."""
    def __init__(self,model_dir=None,threads=4):
        self.path=model_dir or MODEL_DIR/'e5'
        self.tokenizer=Tokenizer.from_file(str(self.path/'tokenizer.json'))
        self.tokenizer.no_truncation()
        self.tokenizer.enable_padding(pad_id=1,pad_token='<pad>')
        options=ort.SessionOptions();options.intra_op_num_threads=threads;options.inter_op_num_threads=1
        options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session=ort.InferenceSession(str(self.path/'model.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
        self.input_names={n.name for n in self.session.get_inputs()}

    def token_count(self,text):return len(self.tokenizer.encode(text,add_special_tokens=False).ids)

    def title(self,title):
        ids=self.tokenizer.encode(title,add_special_tokens=False).ids[:32]
        return self.tokenizer.decode(ids,skip_special_tokens=True)

    def encode(self,texts,kind='passage',batch_size=8):
        if kind not in ('passage','query'):raise ValueError('Unknown embedding kind')
        arrays=[]
        for start in range(0,len(texts),batch_size):
            encoded=self.tokenizer.encode_batch([f'{kind}: {t}' for t in texts[start:start+batch_size]])
            if any(len(x.ids)>512 for x in encoded):raise ValueError('E5 input exceeds 512 tokens; split text explicitly')
            ids=np.asarray([x.ids for x in encoded],dtype=np.int64)
            mask=np.asarray([x.attention_mask for x in encoded],dtype=np.int64)
            inputs={'input_ids':ids,'attention_mask':mask}
            if 'token_type_ids' in self.input_names:inputs['token_type_ids']=np.zeros_like(ids)
            hidden=self.session.run(None,{k:v for k,v in inputs.items() if k in self.input_names})[0]
            if hidden.ndim!=3:raise ValueError(f'Unexpected E5 output shape: {hidden.shape}')
            vectors=(hidden*mask[...,None]).sum(axis=1)/mask.sum(axis=1)[:,None]
            vectors=vectors/np.maximum(np.linalg.norm(vectors,axis=1,keepdims=True),1e-12)
            arrays.append(vectors.astype(np.float32))
        return np.concatenate(arrays) if arrays else np.empty((0,384),dtype=np.float32)
