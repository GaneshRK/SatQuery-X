from __future__ import annotations
import argparse, json, time
from pathlib import Path
import torch
from .dataset import OpticalSARDataset
from .model import OpticalSARNet

def main():
    p=argparse.ArgumentParser(); p.add_argument('--manifest',required=True); p.add_argument('--checkpoint',required=True); p.add_argument('--output',default='docs/optical_sar_evaluation.json'); p.add_argument('--num-classes',type=int,default=None); a=p.parse_args()
    ck=torch.load(a.checkpoint,map_location='cpu',weights_only=False); n=a.num_classes or int(ck['num_classes']); model=OpticalSARNet(n); model.load_state_dict(ck['state_dict']); model.eval()
    ds=OpticalSARDataset(a.manifest); cm=torch.zeros((n,n),dtype=torch.long); lat=[]
    with torch.no_grad():
      for o,s,m,r in ds:
        t=time.perf_counter(); pred=model(o[None],s[None]).argmax(1)[0]; lat.append((time.perf_counter()-t)*1000)
        cm += torch.bincount((m*n+pred).reshape(-1),minlength=n*n).reshape(n,n)
    tp=cm.diag().float(); fp=cm.sum(0).float()-tp; fn=cm.sum(1).float()-tp
    precision=(tp/(tp+fp).clamp_min(1)).mean().item(); recall=(tp/(tp+fn).clamp_min(1)).mean().item(); iou=(tp/(tp+fp+fn).clamp_min(1)).mean().item(); acc=tp.sum().item()/max(1,cm.sum().item())
    result={'status':'evaluated','dataset_size':len(ds),'classes':n,'pixel_accuracy':acc,'macro_precision':precision,'macro_recall':recall,'macro_iou':iou,'mean_latency_ms':sum(lat)/len(lat),'confusion_matrix':cm.tolist(),'checkpoint':str(Path(a.checkpoint))}
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,indent=2),encoding='utf-8'); print(json.dumps(result,indent=2))
if __name__=='__main__': main()
