from __future__ import annotations
import json
from pathlib import Path
from PIL import Image
import torch
from torch.utils.data import Dataset
from ml.native_multimodal.model import question_ids

class NativeTemporalVQADataset(Dataset):
    def __init__(self, manifest: str, answer_to_id: dict[str,int] | None = None):
        self.path = Path(manifest)
        self.rows = [json.loads(x) for x in self.path.read_text(encoding='utf-8').splitlines() if x.strip()]
        required = {'image_t1','image_t2','question','answer'}
        for i,r in enumerate(self.rows):
            missing = required - set(r)
            if missing: raise ValueError(f'{self.path}:{i+1} missing {sorted(missing)}')
        self.answer_to_id = answer_to_id
        self.answers = sorted({str(r['answer']).strip() for r in self.rows})
        if answer_to_id is None: self.answer_to_id = {a:i for i,a in enumerate(self.answers)}
        self.mean = torch.tensor([0.5,0.5,0.5]).view(3,1,1)
        self.std = torch.tensor([0.5,0.5,0.5]).view(3,1,1)
    def __len__(self): return len(self.rows)
    def _img(self, p):
        im = Image.open(p).convert('RGB').resize((256,256), Image.Resampling.BILINEAR)
        x = torch.from_numpy(__import__('numpy').asarray(im)).permute(2,0,1).float()/255.0
        return (x-self.mean)/self.std
    def __getitem__(self, i):
        r=self.rows[i]
        return {'t1':self._img(r['image_t1']), 't2':self._img(r['image_t2']),
                'question_ids':torch.tensor(question_ids(str(r['question'])),dtype=torch.long),
                'answer_id':self.answer_to_id[str(r['answer']).strip()], 'answer':str(r['answer']).strip()}

def collate(batch):
    maxlen=max(x['question_ids'].numel() for x in batch)
    q=torch.zeros(len(batch),maxlen,dtype=torch.long)
    for i,x in enumerate(batch): q[i,:x['question_ids'].numel()]=x['question_ids']
    return {'t1':torch.stack([x['t1'] for x in batch]), 't2':torch.stack([x['t2'] for x in batch]),
            'question_ids':q, 'answer_id':torch.tensor([x['answer_id'] for x in batch])}
