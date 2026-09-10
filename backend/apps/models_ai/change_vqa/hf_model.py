"""Runtime for supervised bi-temporal Change VQA checkpoints."""
from __future__ import annotations
from io import BytesIO
import json
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw
import torch
from transformers import BlipForQuestionAnswering, BlipProcessor
from peft import PeftModel

class HuggingFaceChangeVQA:
    def __init__(self, model_id_or_path: str, device: str = "cpu"):
        self.model_id = model_id_or_path
        self.device = torch.device(device)
        self.processor = BlipProcessor.from_pretrained(model_id_or_path)
        path = Path(model_id_or_path)
        adapter_config = path / "adapter_config.json"
        if adapter_config.exists():
            cfg = json.loads(adapter_config.read_text(encoding="utf-8"))
            base = cfg.get("base_model_name_or_path")
            if not base:
                raise ValueError("Change VQA LoRA checkpoint has no base_model_name_or_path")
            base_model = BlipForQuestionAnswering.from_pretrained(base)
            self.model = PeftModel.from_pretrained(base_model, model_id_or_path)
        else:
            self.model = BlipForQuestionAnswering.from_pretrained(model_id_or_path)
        self.model.to(self.device); self.model.eval()

    @staticmethod
    def _image(value: Any) -> Image.Image:
        if isinstance(value, Image.Image): return value.convert("RGB")
        if isinstance(value, (bytes, bytearray)): return Image.open(BytesIO(value)).convert("RGB")
        return Image.open(Path(value)).convert("RGB")

    @staticmethod
    def _canvas(t1: Image.Image, t2: Image.Image, size: int = 384) -> Image.Image:
        t1, t2 = t1.copy(), t2.copy(); t1.thumbnail((size,size)); t2.thumbnail((size,size))
        h=max(t1.height,t2.height); c=Image.new("RGB",(size*2,h+28),"white")
        c.paste(t1,((size-t1.width)//2,28)); c.paste(t2,(size+(size-t2.width)//2,28))
        d=ImageDraw.Draw(c); d.text((10,7),"T1 / BEFORE",fill="black"); d.text((size+10,7),"T2 / AFTER",fill="black")
        return c

    def answer(self, t1: Any, t2: Any, question: str, max_new_tokens: int = 64) -> dict[str, Any]:
        image=self._canvas(self._image(t1),self._image(t2))
        prompt="Compare the before and after satellite observations. " + question.strip()
        inputs=self.processor(images=image,text=prompt,return_tensors="pt").to(self.device)
        with torch.inference_mode(): ids=self.model.generate(**inputs,max_new_tokens=max_new_tokens)
        answer=self.processor.decode(ids[0],skip_special_tokens=True).strip()
        return {"answer":answer,"confidence":None,"provenance":{"model_id":self.model_id,"method":"supervised bi-temporal BLIP VQA + LoRA if configured","temporal_canvas":"T1 before / T2 after"}}
