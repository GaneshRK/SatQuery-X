"""Native two-image temporal + question fusion model.

Unlike the legacy Change-VQA path, this model never concatenates T1/T2 into
one image. Each timestamp is encoded independently, timestamp embeddings are
added, and the resulting visual tokens are fused with a question token.
The answer head is a supervised closed-vocabulary classifier.
"""
from __future__ import annotations
import hashlib
import torch
from torch import nn
import torch.nn.functional as F


def hash_token(token: str, buckets: int = 4096) -> int:
    return int(hashlib.sha1(token.encode("utf-8")).hexdigest()[:8], 16) % buckets


def question_ids(text: str, buckets: int = 4096, max_tokens: int = 32) -> list[int]:
    toks = [t for t in text.lower().split() if t]
    ids = [hash_token(t, buckets) for t in toks[:max_tokens]]
    return ids or [0]


class ImageEncoder(nn.Module):
    def __init__(self, dim: int = 128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(3, 32, 5, stride=2, padding=2), nn.GELU(),
            nn.Conv2d(32, 64, 3, stride=2, padding=1), nn.GELU(),
            nn.Conv2d(64, dim, 3, stride=2, padding=1), nn.GELU(),
        )
    def forward(self, x):
        return self.net(x)


class NativeTemporalMultimodalVQA(nn.Module):
    def __init__(self, num_answers: int, dim: int = 128, question_buckets: int = 4096):
        super().__init__()
        self.num_answers = num_answers
        self.dim = dim
        self.image_encoder = ImageEncoder(dim)
        self.time_embedding = nn.Embedding(2, dim)
        self.question_embedding = nn.Embedding(question_buckets, dim)
        layer = nn.TransformerEncoderLayer(d_model=dim, nhead=8, dim_feedforward=dim * 4,
                                           batch_first=True, norm_first=True, dropout=0.1)
        self.fusion = nn.TransformerEncoder(layer, num_layers=2)
        self.head = nn.Sequential(nn.LayerNorm(dim), nn.Linear(dim, num_answers))

    def encode_questions(self, ids: torch.Tensor) -> torch.Tensor:
        emb = self.question_embedding(ids)
        mask = (ids != 0).float().unsqueeze(-1)
        return (emb * mask).sum(1) / mask.sum(1).clamp_min(1.0)

    def forward(self, t1: torch.Tensor, t2: torch.Tensor, question_ids_tensor: torch.Tensor):
        f1 = self.image_encoder(t1)
        f2 = self.image_encoder(t2)
        b, d, h, w = f1.shape
        v1 = f1.flatten(2).transpose(1, 2) + self.time_embedding.weight[0]
        v2 = f2.flatten(2).transpose(1, 2) + self.time_embedding.weight[1]
        q = self.encode_questions(question_ids_tensor).unsqueeze(1)
        fused = self.fusion(torch.cat([v1, v2, q], dim=1))
        pooled = fused[:, -1, :]
        return self.head(pooled)
