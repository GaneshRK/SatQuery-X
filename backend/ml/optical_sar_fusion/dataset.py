from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset

class OpticalSARDataset(Dataset):
    """Manifest: {optical, sar, mask}; mask values 0..num_classes-1."""
    def __init__(self, manifest: str, size: int = 256):
        self.root = Path(manifest).parent
        self.records = json.loads(Path(manifest).read_text(encoding='utf-8'))
        if not isinstance(self.records, list) or not self.records:
            raise ValueError('Optical-SAR manifest must be a non-empty JSON list.')
        for i,r in enumerate(self.records):
            for k in ('optical','sar','mask'):
                if k not in r: raise ValueError(f'Record {i} missing {k}.')
        self.size=size
    def _path(self,p):
        p=Path(p); return p if p.is_absolute() else self.root/p
    def __len__(self): return len(self.records)
    def __getitem__(self,i):
        r=self.records[i]
        o=np.asarray(Image.open(self._path(r['optical'])).convert('RGB').resize((self.size,self.size), Image.Resampling.BILINEAR),dtype=np.float32)/255
        s=np.asarray(Image.open(self._path(r['sar'])).convert('L').resize((self.size,self.size), Image.Resampling.BILINEAR),dtype=np.float32)/255
        m=np.asarray(Image.open(self._path(r['mask'])).convert('L').resize((self.size,self.size), Image.Resampling.NEAREST),dtype=np.int64)
        return torch.from_numpy(o).permute(2,0,1), torch.from_numpy(s[None]), torch.from_numpy(m), r
