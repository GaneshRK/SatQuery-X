from __future__ import annotations
import torch
from torch import nn

class ConvEncoder(nn.Module):
    def __init__(self, in_channels: int, base: int = 32):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(in_channels, base, 3, padding=1), nn.BatchNorm2d(base), nn.ReLU(),
            nn.Conv2d(base, base, 3, padding=1), nn.BatchNorm2d(base), nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(base, base*2, 3, padding=1), nn.BatchNorm2d(base*2), nn.ReLU(),
            nn.Conv2d(base*2, base*2, 3, padding=1), nn.BatchNorm2d(base*2), nn.ReLU(),
        )
    def forward(self, x): return self.net(x)

class OpticalSARNet(nn.Module):
    """Supervised dual-encoder optical/SAR pixel classifier.

    Inputs are normalized optical RGB (3 ch) and SAR (1 ch). The branches
    share no weights because the modalities have different physics. Their
    learned features are fused and decoded into per-pixel classes.
    """
    def __init__(self, num_classes: int = 4):
        super().__init__()
        self.optical = ConvEncoder(3)
        self.sar = ConvEncoder(1)
        self.fusion = nn.Sequential(
            nn.Conv2d(128, 128, 3, padding=1), nn.BatchNorm2d(128), nn.ReLU(),
            nn.Conv2d(128, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(),
        )
        self.head = nn.Conv2d(64, num_classes, 1)
        self.num_classes = num_classes
    def forward(self, optical, sar):
        fo, fs = self.optical(optical), self.sar(sar)
        x = self.fusion(torch.cat([fo, fs], dim=1))
        logits = self.head(x)
        return nn.functional.interpolate(logits, size=optical.shape[-2:], mode='bilinear', align_corners=False)
