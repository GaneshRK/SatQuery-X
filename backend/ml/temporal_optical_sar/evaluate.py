from __future__ import annotations
import argparse,json,time
from pathlib import Path
import torch
from torch.utils.data import DataLoader
from .dataset import TemporalOpticalSARDataset, collate
from .model import TemporalOpticalSARVQA

def main():
    p=argparse.ArgumentParser(); p.add_argument('--manifest',required=True); p.add_argument('--checkpoint',required=True); p.add_argument('--output',required=True); p.add_argument('--device',default='auto'); a=p.parse_args()
    device='cuda' if a.device=='auto' and torch.cuda.is_available() else ('cpu' if a.device=='auto' else a.device)
    ck=torch.load(a.checkpoint,map_location=device,weights_only=False); ds=TemporalOpticalSARDataset(a.manifest,ck['answer_to_id']); model=TemporalOpticalSARVQA(len(ck['answer_to_id'])).to(device); model.load_state_dict(ck['state_dict']); model.eval(); rows=[]; correct=0
    with torch.inference_mode():
        for b in DataLoader(ds,batch_size=1,collate_fn=collate):
            t=time.perf_counter(); logits=model(*(b[k].to(device) for k in ('optical_t1','sar_t1','optical_t2','sar_t2','question_ids'))); ms=(time.perf_counter()-t)*1000; prob=torch.softmax(logits,1); score,pred=prob.max(1); pred=int(pred); truth=int(b['answer_id'][0]); correct += pred==truth; rows.append({'prediction':ck['id_to_answer'][pred],'truth':ck['id_to_answer'].get(truth),'confidence':float(score),'latency_ms':ms})
    report={'status':'evaluated','accuracy':correct/max(len(rows),1),'mean_confidence':sum(r['confidence'] for r in rows)/max(len(rows),1),'mean_latency_ms':sum(r['latency_ms'] for r in rows)/max(len(rows),1),'samples':len(rows),'predictions':rows,'model_type':ck.get('model_type'),'confidence_type':'uncalibrated_softmax'}
    Path(a.output).parent.mkdir(parents=True,exist_ok=True); Path(a.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
if __name__=='__main__': main()
