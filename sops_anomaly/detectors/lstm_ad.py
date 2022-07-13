"""
LSTM Anomaly Detector based on reconstruction error density.

"""
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import torch
from torch import nn
import torch.nn.functional as F

from sops_anomaly.detectors.base_detector import BaseDetector
from sops_anomaly.detectors.error_distribution import ErrorDistribution


class LSTM_AD(BaseDetector):

    def __init__(
        self,
        l_predictions: int = 10,
        hidden_size: int = 400,
        threshold: float = 0.9,
    ) -> None:
        """

        :param l_predictions:
        :param hidden_size:
        """
        super(LSTM_AD, self).__init__()
        self.model: Optional[nn.LSTM] = None
        self.linear: Optional[nn.Module] = None
        self._threshold: float = threshold
        self._hidden_size: int = hidden_size
        # Model output dimensions (l, d)
        self._l_preds: int = l_predictions
        self._d_size: int = 0
        # Multivariate gaussian scipy.stats.multivariate_gaussian
        self._error_dist = None

    def _initialize_model(
            self, n_layers: int = 2, dropout: float = 0.5) -> None:
        self.model = nn.LSTM(
            input_size=self._d_size,
            hidden_size=self._hidden_size,
            proj_size=self._l_preds * self._d_size,
            num_layers=n_layers,
            dropout=dropout,
            bidirectional=False,
        )
        self._error_dist = ErrorDistribution(self._d_size, self._l_preds)

    def _reshape_outputs(self, output: torch.Tensor) -> torch.Tensor:
        """Model returns self._l_preds predicted values for each of self._d_size
        dimensions.

        :param output:
        :return:
        """
        d1, d2, _ = output.shape
        return output.reshape(d1, d2, self._d_size, self._l_preds)

    @classmethod
    def _to_tensor(cls, array: np.ndarray) -> torch.Tensor:
        return torch.from_numpy(array.astype(np.float32))

    def _transform_train_data_target(
            self, data: pd.DataFrame) -> Tuple[torch.Tensor, torch.Tensor]:
        """Transforms given data into train and target sets. The sequential
        nature of the model requires targets to include windowed slices of
        data from consequent time steps.

        Ex. if
              data = [1,2,3,4,5,6,7], self._l_preds = 3
            then
              train = [1,2,3,4]
              targets = [[2,3,4],[3,4,5],[4,5,6],[5,6,7]]

        :param data:
        :return:
        """
        values = np.expand_dims(data, axis=0)
        train_data = values[:, :-self._l_preds, :]
        train_targets = []
        for i in range(self._l_preds-1):
            train_targets += [values[:, 1+i:-self._l_preds+i+1, :]]
        train_targets += [values[:, self._l_preds:, :]]
        train_targets = np.stack(train_targets, axis=3)

        train_data, train_targets = (
            self._to_tensor(train_data),
            self._to_tensor(train_targets),
        )
        return train_data, train_targets

    def _transform_eval_data_target(
            self, data: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """Transforms given data into evaluation data input and targets.
        The evaluation is realised as computing reconstruction errors
        for a given point x(t) over all its reconstructions. Because of that
        evaluation can be only performed for points x(t), where t comes from:
        self._l_preds < t <= len(data)-self._l_preds

        :param data:
        :return:
        """
        values = np.expand_dims(data, axis=0)
        eval_data = values[:, :-self._l_preds, :]
        eval_target = values[:, self._l_preds:-self._l_preds+1, :]

        return eval_data, eval_target

    def train(
        self,
        train_data: pd.DataFrame,
        epochs: int = 50,
        learning_rate: float = 1e-4,
        verbose: bool = False,
    ) -> None:
        """

        :param train_data:
        :param epochs:
        :param learning_rate:
        :param verbose:
        :return:
        """
        # Shape: (time_steps, d)
        data = train_data
        # Shape: (batch_size, time_steps-l, d), (batch_size, time_steps-l, d, l)
        train_data, train_targets = self._transform_train_data_target(data)
        self._d_size = train_data[0].shape[-1]
        self._initialize_model()
        # TODO: do test-eval split to estimate distribution on eval set
        self._train_model(train_data, train_targets, epochs, learning_rate,
                          verbose)
        self._fit_error_distribution(data)

    def _fit_error_distribution(self, data: pd.DataFrame):
        # Shape: (time_steps-l, d), (time_steps-2*l, d)
        eval_data, eval_targets = self._transform_eval_data_target(data)
        self.model.eval()
        # Shape: (batch_size, time_steps, d, l)
        outputs = self._get_model_outputs(self._to_tensor(eval_data))
        self._error_dist.fit(outputs.detach().numpy(), eval_targets)

    def _train_model(
        self, train_data: torch.Tensor, train_targets: torch.Tensor,
        epochs: int, learning_rate: float, verbose: bool,
    ) -> None:

        optimizer = torch.optim.Adam(self.model.parameters(), lr=learning_rate)
        self._run_train_loop(
            epochs, optimizer, train_data, train_targets, verbose)

    def _run_train_loop(
        self, epochs: int, optimizer: torch.optim.Optimizer,
        train_data: torch.Tensor, train_targets: torch.Tensor, verbose: bool,
    ) -> None:
        self.model.train()
        for epoch in range(epochs):
            optimizer.zero_grad()
            outputs = self._get_model_outputs(train_data)
            loss = F.mse_loss(outputs, train_targets)
            loss.backward()
            optimizer.step()
            if verbose:
                print(f"Epoch {epoch} loss: {loss.item()}")

    def predict(self, data: pd.DataFrame) -> np.ndarray:
        self.model.eval()
        inputs, targets = self._transform_eval_data_target(data)
        outputs = self._get_model_outputs(self._to_tensor(inputs))
        errors = self._get_errors(outputs, targets)
        scores = self._get_scores(data, errors)

        return scores

    def _get_scores(self, data: pd.DataFrame, errors: np.ndarray) -> np.ndarray:
        p = self._error_dist(errors)
        scores = np.zeros((len(data),))
        scores[self._l_preds:-self._l_preds + 1] = p
        return scores

    def _get_errors(
            self, outputs: torch.Tensor, targets: np.ndarray) -> np.ndarray:
        errors = self._error_dist.get_errors(outputs.detach().numpy(), targets)
        errors = errors.reshape((errors.shape[0], self._l_preds * self._d_size))
        return errors

    def _get_model_outputs(self, inputs: torch.Tensor) -> torch.Tensor:
        if self.model.training:
            outputs, _ = self.model(inputs)
        else:
            with torch.no_grad():
                outputs, _ = self.model(inputs)
        return self._reshape_outputs(outputs)

    def detect(self, data: pd.DataFrame) -> np.ndarray:
        scores = self.predict(data)
        return (scores < self._threshold).astype(np.int32)
