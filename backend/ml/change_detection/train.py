"""Supervised training for SatQuery SiameseChangeNet."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader

from ml.change_detection.dataset import ChangeDetectionManifestDataset
from ml.change_detection.model import SiameseChangeNet


def dice_loss(logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    prob = torch.sigmoid(logits)
    intersection = (prob * target).sum(dim=(1, 2, 3))
    denom = prob.sum(dim=(1, 2, 3)) + target.sum(dim=(1, 2, 3))
    return (1.0 - (2.0 * intersection + 1.0) / (denom + 1.0)).mean()


def run_epoch(model, loader, optimizer, device):
    training = optimizer is not None
    model.train(training)
    total = 0.0
    count = 0
    bce = nn.BCEWithLogitsLoss()
    for batch in loader:
        t1, t2, mask = batch["t1"].to(device), batch["t2"].to(device), batch["mask"].to(device)
        logits = model(t1, t2)
        loss = bce(logits, mask) + dice_loss(logits, mask)
        if training:
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
        total += float(loss.item()) * t1.shape[0]
        count += t1.shape[0]
    return total / max(count, 1)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--train-manifest", required=True)
    p.add_argument("--val-manifest")
    p.add_argument("--output", default="ml/checkpoints/satquery_siamese_cd_v1.pt")
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--batch-size", type=int, default=4)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--size", type=int, default=256)
    p.add_argument("--device", default="auto")
    args = p.parse_args()

    device = "cuda" if args.device == "auto" and torch.cuda.is_available() else ("cpu" if args.device == "auto" else args.device)
    train_ds = ChangeDetectionManifestDataset(args.train_manifest, args.size)
    val_ds = ChangeDetectionManifestDataset(args.val_manifest, args.size) if args.val_manifest else None
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, num_workers=0) if val_ds else None

    model = SiameseChangeNet().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    best = float("inf")
    history = []

    for epoch in range(1, args.epochs + 1):
        train_loss = run_epoch(model, train_loader, optimizer, device)
        val_loss = run_epoch(model, val_loader, None, device) if val_loader else None
        row = {"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss}
        history.append(row)
        print(row)
        score = val_loss if val_loss is not None else train_loss
        if score < best:
            best = score
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            torch.save({
                "model_state_dict": model.state_dict(),
                "model_type": "SiameseChangeNet",
                "in_channels": 3,
                "input_size": args.size,
                "best_loss": best,
                "train_manifest": str(Path(args.train_manifest).resolve()),
                "val_manifest": str(Path(args.val_manifest).resolve()) if args.val_manifest else None,
                "history": history,
            }, out)

    print(json.dumps({"checkpoint": str(Path(args.output).resolve()), "best_loss": best}, indent=2))


if __name__ == "__main__":
    main()
