import numpy as np
from ml.evaluation.calibration import fit_temperature_binary, apply_binary_temperature

def test_temperature_is_positive_and_metrics_finite():
    logits=np.array([-3.,-1.,0.,1.,3.,2.,-2.,0.5])
    y=np.array([0,0,0,1,1,1,0,1])
    r=fit_temperature_binary(logits,y)
    assert r.temperature > 0
    assert np.isfinite([r.nll_before,r.nll_after,r.ece_before,r.ece_after,r.brier_before,r.brier_after]).all()
    assert np.isfinite(apply_binary_temperature(logits,r.temperature)).all()
