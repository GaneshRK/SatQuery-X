"""Trainable Siamese remote-sensing change detector.

This is SatQuery's own compact supervised baseline. It is intentionally named
SiameseChangeNet rather than ChangeFormer: a ChangeFormer checkpoint is a
separate architecture and must not be mislabeled as this model.
"""
from __future__ import annotations

import torch
from torch import nn
import torch.nn.functional as F


class ConvBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.block(x)


class SiameseEncoder(nn.Module):
    def __init__(self, in_channels: int = 3) -> None:
        super().__init__()
        self.e1 = ConvBlock(in_channels, 32)
        self.e2 = ConvBlock(32, 64)
        self.e3 = ConvBlock(64, 128)

    def forward(self, x: torch.Tensor):
        x1 = self.e1(x)
        x2 = self.e2(F.max_pool2d(x1, 2))
        x3 = self.e3(F.max_pool2d(x2, 2))
        return x1, x2, x3


class SiameseChangeNet(nn.Module):
    """Binary bi-temporal change segmentation network.

    Both dates share the same encoder weights. Absolute feature differences
    are decoded into a one-channel change logit map.
    """

    def __init__(self, in_channels: int = 3) -> None:
        super().__init__()
        self.encoder = SiameseEncoder(in_channels)
        self.decode3 = ConvBlock(128, 64)
        self.decode2 = ConvBlock(64 + 64, 32)
        self.decode1 = ConvBlock(32 + 32, 16)
        self.head = nn.Conv2d(16, 1, kernel_size=1)

    def forward(self, t1: torch.Tensor, t2: torch.Tensor) -> torch.Tensor:
        a1, a2, a3 = self.encoder(t1)
        b1, b2, b3 = self.encoder(t2)

        x = self.decode3(torch.abs(a3 - b3))
        x = F.interpolate(x, size=a2.shape[-2:], mode="bilinear", align_corners=False)
        x = self.decode2(torch.cat([x, torch.abs(a2 - b2)], dim=1))
        x = F.interpolate(x, size=a1.shape[-2:], mode="bilinear", align_corners=False)
        x = self.decode1(torch.cat([x, torch.abs(a1 - b1)], dim=1))
        return self.head(x)
