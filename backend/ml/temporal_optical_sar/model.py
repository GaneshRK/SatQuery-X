"""Native four-stream temporal Optical/SAR fusion.

Streams: Optical T1, SAR T1, Optical T2, SAR T2 + question.
The model keeps optical and SAR encoders separate and explicitly represents
both modality and time before Transformer fusion.
"""
from __future__ import annotations
import hashlib
import torch
from torch import nn


def hash_token(token: str, buckets: int = 4096) -> int:
    return int(hashlib.sha1(token.encode("utf-8")).hexdigest()[:8], 16) % buckets


def question_ids(text: str, buckets: int = 4096, max_tokens: int = 32) -> list[int]:
    ids = [hash_token(t, buckets) for t in str(text).lower().split()[:max_tokens] if t]
    return ids or [0]


class StreamEncoder(nn.Module):
    def __init__(self, in_channels: int, dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(in_channels, 32, 5, 2, 2), nn.GELU(),
            nn.Conv2d(32, 64, 3, 2, 1), nn.GELU(),
            nn.Conv2d(64, dim, 3, 2, 1), nn.GELU(),
        )
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class TemporalOpticalSARVQA(nn.Module):
    def __init__(self, num_answers: int, dim: int = 128, question_buckets: int = 4096):
        super().__init__()
        self.num_answers = num_answers
        self.dim = dim
        self.optical_encoder = StreamEncoder(3, dim)
        self.sar_encoder = StreamEncoder(1, dim)
        self.time_embedding = nn.Embedding(2, dim)
        self.modality_embedding = nn.Embedding(2, dim)  # 0 optical, 1 SAR
        self.question_embedding = nn.Embedding(question_buckets, dim)
        layer = nn.TransformerEncoderLayer(d_model=dim, nhead=8, dim_feedforward=dim * 4,
                                           batch_first=True, norm_first=True, dropout=0.1)
        self.fusion = nn.TransformerEncoder(layer, num_layers=2)
        self.head = nn.Sequential(nn.LayerNorm(dim), nn.Linear(dim, num_answers))

    def _tokens(self, feature, time_id: int, modality_id: int):
        b = feature.shape[0]
        return feature.flatten(2).transpose(1, 2) + self.time_embedding.weight[time_id] + self.modality_embedding.weight[modality_id]

    def encode_question(self, ids: torch.Tensor) -> torch.Tensor:
        emb = self.question_embedding(ids)
        mask = (ids != 0).float().unsqueeze(-1)
        return (emb * mask).sum(1) / mask.sum(1).clamp_min(1.0)

    def forward(self, optical_t1, sar_t1, optical_t2, sar_t2, question_ids_tensor):
        streams = [
            self._tokens(self.optical_encoder(optical_t1), 0, 0),
            self._tokens(self.sar_encoder(sar_t1), 0, 1),
            self._tokens(self.optical_encoder(optical_t2), 1, 0),
            self._tokens(self.sar_encoder(sar_t2), 1, 1),
        ]
        q = self.encode_question(question_ids_tensor).unsqueeze(1)
        fused = self.fusion(torch.cat(streams + [q], dim=1))
        return self.head(fused[:, -1, :])
