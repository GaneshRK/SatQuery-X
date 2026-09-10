from ml.temporal_optical_sar.model import TemporalOpticalSARVQA
from apps.agent.modality_router import resolve_analysis_route
import torch

def test_four_stream_forward():
    model=TemporalOpticalSARVQA(num_answers=3, dim=32)
    # nhead must divide dim; replace with compatible model for test
    model=TemporalOpticalSARVQA(num_answers=3, dim=128)
    out=model(torch.randn(1,3,64,64),torch.randn(1,1,64,64),torch.randn(1,3,64,64),torch.randn(1,1,64,64),torch.ones(1,3,dtype=torch.long))
    assert out.shape == (1,3)

def test_router_identifies_four_stream_route():
    records=[
        {"modality":"optical","acquisition_date":"2025-01-01"},
        {"modality":"sar","acquisition_date":"2025-01-01"},
        {"modality":"optical","acquisition_date":"2025-02-01"},
        {"modality":"sar","acquisition_date":"2025-02-01"},
    ]
    r=resolve_analysis_route(records,"TEMPORAL_CROSS_MODAL")
    assert r["route"] == "BI_TEMPORAL_OPTICAL_SAR"
    assert r["specialist"] == "COMPOSED_TEMPORAL_MULTIMODAL"
