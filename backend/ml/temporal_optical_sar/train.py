from __future__ import annotations
import argparse
from pathlib import Path
import torch
from torch.utils.data import DataLoader
from .dataset import TemporalOpticalSARDataset, collate
from .model import TemporalOpticalSARVQA

def main():
    p=argparse.ArgumentParser(); p.add_argument('--manifest',required=True); p.add_argument('--output',default='ml/checkpoints/temporal_optical_sar_v1.pt'); p.add_argument('--epochs',type=int,default=5); p.add_argument('--batch-size',type=int,default=2); p.add_argument('--lr',type=float,default=1e-3); p.add_argument('--device',default='auto'); a=p.parse_args()
    device='cuda' if a.device=='auto' and torch.cuda.is_available() else ('cpu' if a.device=='auto' else a.device)
    ds=TemporalOpticalSARDataset(a.manifest); dl=DataLoader(ds,batch_size=a.batch_size,shuffle=True,collate_fn=collate)
    model=TemporalOpticalSARVQA(len(ds.answer_to_id)).to(device); opt=torch.optim.AdamW(model.parameters(),lr=a.lr)
    model.train()
    for _ in range(a.epochs):
        for b in dl:
            opt.zero_grad(); logits=model(*(b[k].to(device) for k in ('optical_t1','sar_t1','optical_t2','sar_t2','question_ids'))); loss=torch.nn.functional.cross_entropy(logits,b['answer_id'].to(device)); loss.backward(); opt.step()
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True)
    torch.save({'state_dict':model.state_dict(),'answer_to_id':ds.answer_to_id,'id_to_answer':{v:k for k,v in ds.answer_to_id.items()},'model_type':'temporal_optical_sar_vqa','question_buckets':4096,'image_size':256},out)
    print(f'Saved {out}')
if __name__=='__main__': main()
