"""
Auto-encoder anomaly detector.

References:
    - "Variational auto-encoder based anomaly detection using reconstruction
     probability" J.An, S.Cho.

"""
from typing import List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.nn import functional as F

from sops_anomaly.detectors.base_detector import BaseDetector
from sops_anomaly.utils import window_data


class _AEModel(nn.Module):
    def __init__(
        self,
        input_size: int,
        latent_size: int,
        layers: Union[List[int], Tuple[int]],
    ) -> None:

        super().__init__()
        self.encoder: nn.Module = self._get_encoder(
            input_size, layers, latent_size)
        self.decoder: nn.Module = self._get_decoder(
            latent_size, list(reversed(layers)), input_size)

    @classmethod
    def _get_encoder(
        cls,
        input_size: int,
        layers: Union[List[int], Tuple[int]],
        output_size: int,
    ) -> nn.Module:
        nn_layers = cls._build_layers(input_size, layers, output_size)
        encoder = cls._build_network(nn_layers)
        return encoder

    @classmethod
    def _get_decoder(
        cls,
        input_size: int,
        layers: Union[List[int], Tuple[int]],
        output_size: int,
    ) -> nn.Module:
        nn_layers = cls._build_layers(input_size, layers, output_size)
        decoder = cls._build_network(nn_layers)
        return decoder

    def forward(self, data: torch.Tensor) -> torch.Tensor:
        encoded = self.encoder(data)
        decoded = self.decoder(encoded)
        return decoded

    @classmethod
    def _build_layers(cls, input_size, layers, output_size):
        if len(layers) > 0:
            input_layer = nn.Linear(input_size, layers[0])
            output_layer = nn.Linear(layers[-1], output_size)
        else:
            return [nn.Linear(input_size, output_size)]

        inner_layers = []
        if len(layers) > 1:
            inner_layers = [
                nn.Linear(layers[i - 1], layers[i])
                for i
                in range(1, len(layers))
            ]
        all_layers = [input_layer] + inner_layers + [output_layer]
        return all_layers

    @classmethod
    def _build_network(cls, layers: List[nn.Module]) -> nn.Sequential:
        network = []
        for layer in layers[:-1]:
            network.extend((
                layer,
                nn.ReLU(),
            ))
        network.append(layers[-1])
        return nn.Sequential(*network)


class AutoEncoder(BaseDetector):

    def __init__(
        self,
        window_size: int,
        latent_size: int = 100,
        layers: Union[List[int], Tuple[int]] = (500, 200),
        threshold: float = 0.8,
    ) -> None:
        self.model: Optional[nn.Module] = None
        self._layers: Union[List[int], Tuple[int]] = layers
        self._window_size: int = window_size
        self._input_size: int = 0
        self._latent_size: int = latent_size
        self._threshold: float = threshold
        self._max_error: float = 0.0

    def _transform_data(self, data: pd.DataFrame) -> pd.DataFrame:
        return window_data(data, self._window_size)

    @classmethod
    def _data_to_tensors(cls, data: pd.DataFrame) -> List[torch.Tensor]:
        tensors = [torch.Tensor(row) for _, row in data.iterrows()]
        return tensors

    def _compute_threshold(self, data: List[torch.Tensor]) -> float:
        scores = []
        self.model.eval()
        with torch.no_grad():
            for sample in data:
                rec = self.model.forward(sample)
                scores.append(F.mse_loss(rec, sample).item())
        scores = np.array(scores)
        return np.max(scores)

    def train(
        self,
        train_data: pd.DataFrame,
        epochs: int = 20,
        learning_rate: float = 1e-4,
        verbose: bool = False,
    ) -> None:
        if self._window_size > 1:
            train_data = self._transform_data(train_data)
        self._input_size = len(train_data.iloc[0])
        train_data = self._data_to_tensors(train_data)

        self.model = _AEModel(
            input_size=self._input_size,
            latent_size=self._latent_size,
            layers=self._layers,
        )
        self.model.train()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=learning_rate)

        for epoch in range(epochs):
            epoch_loss = 0
            for sample in train_data:
                optimizer.zero_grad()
                reconstructed = self.model.forward(sample)
                loss = F.mse_loss(reconstructed, sample)
                epoch_loss += loss.item()
                loss.backward()
                optimizer.step()
            if verbose:
                print(f"Epoch {epoch} loss: {epoch_loss/len(train_data)}")

        self._max_error = self._compute_threshold(train_data)

    def predict(self, data: pd.DataFrame) -> np.ndarray:
        if self._window_size > 1:
            input_data = self._transform_data(data)
            input_data = self._data_to_tensors(input_data)
        else:
            input_data = self._data_to_tensors(data)

        # Zero padding to match input length.
        scores = [0] * (self._window_size - 1)
        self.model.eval()
        with torch.no_grad():
            for sample in input_data:
                rec = self.model.forward(sample)
                scores.append(F.mse_loss(rec, sample).item())
        return np.array(scores)

    def detect(self, data: pd.DataFrame) -> np.ndarray:
        scores = self.predict(data)
        return (scores >= self._threshold * self._max_error).astype(np.int32)
