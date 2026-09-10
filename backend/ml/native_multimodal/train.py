from __future__ import annotations
import argparse, json
from pathlib import Path
import torch
from torch.utils.data import DataLoader
from ml.native_multimodal.dataset import NativeTemporalVQADataset, collate
from ml.native_multimodal.model import NativeTemporalMultimodalVQA

def main():
    p=argparse.ArgumentParser(); p.add_argument('--manifest',required=True); p.add_argument('--output',default='ml/checkpoints/native_temporal_vqa_v1.pt')
    p.add_argument('--epochs',type=int,default=5); p.add_argument('--batch-size',type=int,default=4); p.add_argument('--lr',type=float,default=1e-3); p.add_argument('--device',default='auto')
    a=p.parse_args(); device='cuda' if a.device=='auto' and torch.cuda.is_available() else ('cpu' if a.device=='auto' else a.device)
    ds=NativeTemporalVQADataset(a.manifest); loader=DataLoader(ds,batch_size=a.batch_size,shuffle=True,collate_fn=collate)
    model=NativeTemporalMultimodalVQA(len(ds.answer_to_id)).to(device); opt=torch.optim.AdamW(model.parameters(),lr=a.lr)
    model.train()
    for _ in range(a.epochs):
        for b in loader:
            opt.zero_grad(); logits=model(b['t1'].to(device),b['t2'].to(device),b['question_ids'].to(device)); loss=torch.nn.functional.cross_entropy(logits,b['answer_id'].to(device)); loss.backward(); opt.step()
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True)
    torch.save({'state_dict':model.state_dict(),'answer_to_id':ds.answer_to_id,'id_to_answer':{v:k for k,v in ds.answer_to_id.items()},'model_type':'native_temporal_multimodal_vqa','question_buckets':4096,'image_size':256},out)
    print(f'Saved {out}')
if __name__=='__main__': main()
