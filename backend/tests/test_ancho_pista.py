import numpy as np

from app.services.ancho_pista import eje_rapido


def test_eje_reducido_conserva_pasos_de_un_pixel():
    mask = np.zeros((601, 2201), dtype=np.uint8)
    mask[250:351, :] = 1

    y, x = eje_rapido(mask, radio_max=50)

    assert np.ptp(x) > 2000
    assert np.all(mask[y, x])
    assert np.all(np.maximum(np.abs(np.diff(x)), np.abs(np.diff(y))) == 1)
