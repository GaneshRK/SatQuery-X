from __future__ import annotations
import argparse, json
from pathlib import Path
import torch
from torch import nn
from torch.utils.data import DataLoader
from .dataset import OpticalSARDataset
from .model import OpticalSARNet

def main():
    p=argparse.ArgumentParser(description='Train supervised optical-SAR fusion segmentation model.')
    p.add_argument('--manifest',required=True); p.add_argument('--output',default='ml/checkpoints/optical_sar_v1.pt')
    p.add_argument('--epochs',type=int,default=10); p.add_argument('--batch-size',type=int,default=4); p.add_argument('--lr',type=float,default=1e-3)
    p.add_argument('--num-classes',type=int,default=4); p.add_argument('--device',default='auto')
    a=p.parse_args(); device='cuda' if a.device=='auto' and torch.cuda.is_available() else ('cpu' if a.device=='auto' else a.device)
    ds=OpticalSARDataset(a.manifest); dl=DataLoader(ds,batch_size=a.batch_size,shuffle=True,num_workers=0)
    model=OpticalSARNet(a.num_classes).to(device); opt=torch.optim.AdamW(model.parameters(),lr=a.lr); loss_fn=nn.CrossEntropyLoss()
    for epoch in range(1,a.epochs+1):
        model.train(); total=0
        for o,s,m,_ in dl:
            o,s,m=o.to(device),s.to(device),m.to(device); opt.zero_grad(); loss=loss_fn(model(o,s),m); loss.backward(); opt.step(); total += loss.item()
        print(f'epoch={epoch} loss={total/max(1,len(dl)):.6f}')
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True)
    torch.save({'state_dict':model.state_dict(),'num_classes':a.num_classes,'architecture':'OpticalSARNet','manifest':str(Path(a.manifest).resolve())},out)
    print(out)
if __name__=='__main__': main()
