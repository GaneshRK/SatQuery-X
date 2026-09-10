import torch
from ml.native_multimodal.model import NativeTemporalMultimodalVQA, question_ids

def test_native_temporal_forward_uses_two_images_and_question():
    model = NativeTemporalMultimodalVQA(num_answers=4)
    out = model(torch.randn(2,3,256,256), torch.randn(2,3,256,256),
                torch.tensor([question_ids('what changed'), question_ids('where change')]))
    assert out.shape == (2,4)

def test_question_hashing_is_deterministic():
    assert question_ids('what changed') == question_ids('what changed')
