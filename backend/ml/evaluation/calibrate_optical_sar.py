"""Fit multiclass temperature scaling from saved validation logits/labels."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np


def metrics(logits, y, t, bins=15):
    z = logits / t
    z = z - z.max(axis=1, keepdims=True)
    p = np.exp(z); p /= p.sum(axis=1, keepdims=True)
    idx = np.arange(len(y))
    nll = float(-np.mean(np.log(np.clip(p[idx, y], 1e-7, 1.0))))
    brier = float(np.mean(np.sum((p - np.eye(p.shape[1])[y])**2, axis=1)))
    conf = p.max(1); pred = p.argmax(1); acc = (pred == y).astype(float)
    ece = 0.0
    edges = np.linspace(0,1,bins+1)
    for i in range(bins):
        m=(conf>=edges[i]) & (conf <= edges[i+1] if i==bins-1 else conf<edges[i+1])
        if m.any(): ece += float(m.mean()) * abs(float(conf[m].mean())-float(acc[m].mean()))
    return {"nll":nll,"brier":brier,"ece":ece}


def main():
    p=argparse.ArgumentParser(); p.add_argument("--logits-npy",required=True); p.add_argument("--labels-npy",required=True); p.add_argument("--output",required=True); a=p.parse_args()
    z=np.asarray(np.load(a.logits_npy),dtype=np.float64); y=np.asarray(np.load(a.labels_npy),dtype=np.int64).reshape(-1)
    if z.ndim != 2 or len(y)!=len(z): raise ValueError("Expected logits [N,C] and labels [N].")
    grid=np.exp(np.linspace(np.log(.05),np.log(20),161)); vals=[metrics(z,y,t)["nll"] for t in grid]; best=float(grid[int(np.argmin(vals))])
    before=metrics(z,y,1.0); after=metrics(z,y,best)
    payload={"task":"OPTICAL_SAR_FUSION","method":"temperature_scaling","temperature":best,"validation_metrics":{"before":before,"after":after},"calibration_data":"held_out_validation"}
    Path(a.output).write_text(json.dumps(payload,indent=2),encoding="utf-8"); print(json.dumps(payload,indent=2))
if __name__=="__main__": main()
