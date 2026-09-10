"""Runtime wrapper for the native four-stream temporal Optical/SAR VQA model."""
from __future__ import annotations
import io, os, time
from typing import Any
import numpy as np
from PIL import Image
from apps.agent.contracts import ModelInput, ModelOutput
from apps.models_ai.manager import model_manager

class TemporalOpticalSARModel:
    model_id = "TEMPORAL_OPTICAL_SAR"
    version = "1.0-native-four-stream"
    task = "temporal_optical_sar_vqa"

    def predict(self, inputs: ModelInput) -> ModelOutput:
        start=time.perf_counter(); checkpoint=os.getenv("TEMPORAL_OPTICAL_SAR_CHECKPOINT", "").strip()
        if not checkpoint:
            return ModelOutput(model_id=self.model_id, version=self.version, task=self.task, status="error", error="TEMPORAL_OPTICAL_SAR_CHECKPOINT is not configured; four-stream inference is unavailable.", latency_ms=int((time.perf_counter()-start)*1000))
        paths=getattr(inputs,"image_paths",[]) or []; blobs=getattr(inputs,"image_bytes",[]) or []
        meta=getattr(inputs,"context",{}) or {}; route=(meta.get("analysis_route") or {}) if isinstance(meta,dict) else {}
        oi=(route.get("indices") or {}).get("optical",[]) if isinstance(route,dict) else []
        si=(route.get("indices") or {}).get("sar",[]) if isinstance(route,dict) else []
        if len(oi)<2 or len(si)<2:
            return ModelOutput(model_id=self.model_id,version=self.version,task=self.task,status="error",error="Four-stream inference requires two optical and two SAR observations with explicit modality metadata.",latency_ms=int((time.perf_counter()-start)*1000))
        try:
            import torch
            from ml.temporal_optical_sar.model import TemporalOpticalSARVQA, question_ids
            device=model_manager.device
            ck=torch.load(checkpoint,map_location=device,weights_only=False)
            model=TemporalOpticalSARVQA(len(ck["answer_to_id"])).to(device); model.load_state_dict(ck["state_dict"]); model.eval()
            def inp(idx, channel):
                if blobs: raw=blobs[idx]
                else:
                    with open(paths[idx],"rb") as f: raw=f.read()
                if channel==1:
                    try:
                        import rasterio
                        if not blobs and paths[idx].lower().endswith((".tif",".tiff",".jp2")):
                            with rasterio.open(paths[idx]) as src: arr=src.read(1).astype("float32")
                            lo,hi=np.nanpercentile(arr,[2,98]); arr=np.clip((arr-lo)/max(hi-lo,1e-6),0,1); x=torch.from_numpy(arr)[None]
                            x=torch.nn.functional.interpolate(x[None],size=(256,256),mode="bilinear",align_corners=False)[0]
                        else: raise ValueError
                    except Exception:
                        im=Image.open(io.BytesIO(raw)).convert("L").resize((256,256)); x=torch.from_numpy(np.asarray(im,dtype=np.float32))[None]/255
                else:
                    im=Image.open(io.BytesIO(raw)).convert("RGB").resize((256,256)); x=torch.from_numpy(np.asarray(im,dtype=np.float32)).permute(2,0,1)/255
                return (x-.5)/.5
            ot1,ot2=oi[0],oi[1]; st1,st2=si[0],si[1]
            q=torch.tensor([question_ids(getattr(inputs,"question","") or "")],dtype=torch.long,device=device)
            tensors=[inp(ot1,3),inp(st1,1),inp(ot2,3),inp(st2,1)]
            tensors=[x[None].to(device) for x in tensors]
            with torch.inference_mode(): logits=model(*tensors,q); prob=torch.softmax(logits,1); score,pred=prob.max(1)
            answer=ck["id_to_answer"][int(pred)]; model_manager.mark_prediction(checkpoint,success=True)
            return ModelOutput(model_id=self.model_id,version=self.version,task=self.task,answer=answer,confidence=float(score),status="ok",latency_ms=int((time.perf_counter()-start)*1000),raw={"adaptation":"native_four_stream_temporal_optical_sar","base_model":"TemporalOpticalSARVQA","checkpoint":checkpoint,"stream_indices":{"optical_t1":ot1,"sar_t1":st1,"optical_t2":ot2,"sar_t2":st2},"confidence_type":"uncalibrated_softmax","closed_vocabulary":True})
        except Exception as exc:
            try: model_manager.mark_prediction(checkpoint,success=False,error=str(exc))
            except Exception: pass
            return ModelOutput(model_id=self.model_id,version=self.version,task=self.task,status="error",error=str(exc),latency_ms=int((time.perf_counter()-start)*1000))
