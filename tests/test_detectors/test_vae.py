import numpy as np
import pandas as pd
import pytest

from ad_toolkit.detectors import VariationalAutoEncoder

datasets = (
    pd.DataFrame(np.random.random((10, 1))),
    pd.DataFrame(np.random.random((10, 10))),
    pd.DataFrame(np.random.random((10, 200))),
    pd.DataFrame(np.random.random((200, 5))),
)


@pytest.mark.parametrize("data", datasets)
@pytest.mark.parametrize("use_gpu", (False, True))
def test_train_vae(data, use_gpu):
    vae = VariationalAutoEncoder(window_size=3, latent_size=10, use_gpu=use_gpu)
    vae.train(data, epochs=2)


@pytest.mark.parametrize("layers", (
    (), (100, ), (500, 200), (500, 300, 200, 100),
))
def test_build_custom_network_auto_encoder(layers):
    vae = VariationalAutoEncoder(window_size=2, latent_size=50, layers=layers)
    vae.train(pd.DataFrame([1, 2, 3, 4, 5, 6, 7]), epochs=1)
    expected_enc_sizes = (vae._input_size, *layers, vae._latent_size)
    expected_dec_sizes = tuple(reversed(expected_enc_sizes))
    encoder_layers = [vae.model.encoder[i]
                      for i
                      in range(0, len(vae.model.encoder), 2)]
    decoder_layers = [vae.model.decoder[i]
                      for i
                      in range(0, len(vae.model.decoder), 2)]
    for i, layer in enumerate(encoder_layers):
        assert layer.in_features == expected_enc_sizes[i]
        assert layer.out_features == expected_enc_sizes[i+1]

    for i, layer in enumerate(decoder_layers):
        assert layer.in_features == expected_dec_sizes[i]
        assert layer.out_features == expected_dec_sizes[i+1]


@pytest.mark.parametrize("data", datasets)
@pytest.mark.parametrize("window_size", (1, 3, 5))
@pytest.mark.parametrize("latent_size", (10, 50, 100))
@pytest.mark.parametrize("use_gpu", (False, True))
def test_train_predict_vae(data, window_size, latent_size, use_gpu):
    vae = VariationalAutoEncoder(window_size=window_size, use_gpu=use_gpu,
                                 latent_size=latent_size)
    vae.train(data, epochs=2)

    p = vae.predict(data)
    assert len(p) == len(data)


@pytest.mark.parametrize("data", datasets)
@pytest.mark.parametrize("window_size", (1, 3, 5))
def test_train_predict_raw_errors_vae(data, window_size):
    vae = VariationalAutoEncoder(window_size=window_size)
    vae.train(data, epochs=2)

    p = vae.predict(data, raw_errors=True)
    assert p.shape == data.shape
