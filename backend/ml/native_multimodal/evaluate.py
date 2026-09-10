from __future__ import annotations
import argparse, json, time
from pathlib import Path
import torch
from torch.utils.data import DataLoader
from ml.native_multimodal.dataset import NativeTemporalVQADataset, collate
from ml.native_multimodal.model import NativeTemporalMultimodalVQA

def main():
    p=argparse.ArgumentParser(); p.add_argument('--manifest',required=True); p.add_argument('--checkpoint',required=True); p.add_argument('--output',required=True); p.add_argument('--device',default='auto'); a=p.parse_args()
    device='cuda' if a.device=='auto' and torch.cuda.is_available() else ('cpu' if a.device=='auto' else a.device)
    ck=torch.load(a.checkpoint,map_location=device,weights_only=False); ds=NativeTemporalVQADataset(a.manifest,ck['answer_to_id']); model=NativeTemporalMultimodalVQA(len(ck['answer_to_id'])).to(device); model.load_state_dict(ck['state_dict']); model.eval()
    correct=0; total=0; conf=[]; rows=[]
    with torch.inference_mode():
        for b in DataLoader(ds,batch_size=1,collate_fn=collate):
            t=time.perf_counter(); logits=model(b['t1'].to(device),b['t2'].to(device),b['question_ids'].to(device)); latency=(time.perf_counter()-t)*1000
            prob=torch.softmax(logits,1); score,pred=prob.max(1); pred=int(pred); truth=int(b['answer_id'][0]); correct+=pred==truth; total+=1; conf.append(float(score)); rows.append({'prediction':ck['id_to_answer'][pred],'truth':ck['id_to_answer'].get(truth),'confidence':float(score),'latency_ms':latency})
    report={'status':'evaluated','accuracy':correct/max(total,1),'mean_confidence':sum(conf)/max(len(conf),1),'mean_latency_ms':sum(r['latency_ms'] for r in rows)/max(len(rows),1),'samples':total,'predictions':rows,'model_type':ck.get('model_type')}
    Path(a.output).parent.mkdir(parents=True,exist_ok=True); Path(a.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
if __name__=='__main__': main()
