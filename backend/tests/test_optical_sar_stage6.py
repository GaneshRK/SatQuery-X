from pathlib import Path

def test_stage6_files_exist():
    root=Path(__file__).parents[1]
    for rel in ['ml/optical_sar_fusion/model.py','ml/optical_sar_fusion/dataset.py','ml/optical_sar_fusion/train.py','ml/optical_sar_fusion/evaluate.py','data/optical_sar/README.md']:
        assert (root/rel).exists()

def test_stage6_no_fake_metrics():
    text=(Path(__file__).parents[1]/'ml/optical_sar_fusion/evaluate.py').read_text()
    assert 'pixel_accuracy' in text and 'confusion_matrix' in text
