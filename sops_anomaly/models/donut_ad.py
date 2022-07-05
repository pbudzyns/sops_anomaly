"""
Variational auto-encoder with MCMC.

"""
from typing import List

from donut import Donut as _Donut, DonutTrainer, DonutPredictor
from donut.preprocessing import complete_timestamp, standardize_kpi
import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
from tfsnippet.modules import Sequential

from sops_anomaly.models.base_model import BaseDetector
from sops_anomaly.utils import window_data


TF_SESSION = tf.Session()


class Donut(BaseDetector):

    def __init__(self, window_size: int = 1):
        self._window_size = window_size
        self._models: List[_Donut] = []
        self._sessions: List[tf.Session] = []
        self._predictors: List[DonutPredictor] = []
        self._model_counter = 0

    def train(self, train_data: pd.DataFrame, epochs: int = 0):
        train_data = window_data(train_data, self._window_size)
        timestamp = np.array(train_data.index)
        for _, column in train_data.items():
            values = np.array(column)
            labels = np.zeros_like(values, dtype=np.int32)
            timestamp, missing, (values, labels) = complete_timestamp(timestamp,
                                                                      (values,
                                                                       labels))
            train_values, mean, std = standardize_kpi(
                values, excludes=np.logical_or(labels, missing))

            model, model_vs = self._build_model()
            trainer = DonutTrainer(model=model, model_vs=model_vs)
            predictor = DonutPredictor(model)
            session = tf.Session()

            with session.as_default():
                trainer.fit(train_values, labels, missing, mean, std)

            self._models.append(model)
            self._predictors.append(predictor)
            self._sessions.append(session)

    def _build_model(self):
        with tf.variable_scope(f'model{self._model_counter}') as model_vs:
            model = _Donut(
                h_for_p_x=Sequential([
                    layers.Dense(100,
                                   kernel_regularizer=keras.regularizers.l2(0.001),
                                   activation=tf.nn.relu),
                    layers.Dense(100,
                                   kernel_regularizer=keras.regularizers.l2(0.001),
                                   activation=tf.nn.relu),
                ]),
                h_for_q_z=Sequential([
                    layers.Dense(100,
                                   kernel_regularizer=keras.regularizers.l2(0.001),
                                   activation=tf.nn.relu),
                    layers.Dense(100,
                                   kernel_regularizer=keras.regularizers.l2(0.001),
                                   activation=tf.nn.relu),
                ]),
                x_dims=120,
                z_dims=5,
            )
        self._model_counter += 1
        return model, model_vs

    # def _train(self, train_values, train_labels, train_missing, mean, std):
    #
    #
    #     trainer = DonutTrainer(model=model, model_vs=model_vs)
    #     self.predictor = DonutPredictor(model)
    #
    #     with TF_SESSION.as_default():
    #         trainer.fit(train_values, train_labels, train_missing, mean, std)
            # test_score = predictor.get_score(test_values, test_missing)

    def predict(self, data: pd.DataFrame) -> np.ndarray:
        data = window_data(data, self._window_size)
        timestamp = np.array(data.index)
        results = []
        for i, (_, column) in enumerate(data.items()):
            values = np.array(column)
            labels = np.zeros_like(values, dtype=np.int32)
            timestamp, missing, (values, labels) = complete_timestamp(timestamp,
                                                                      (values,
                                                                       labels))
            session = self._sessions[i]
            with session.as_default():
                scores = self._predictors[i].get_score(values, missing)
            results.append(scores)

        # results = np.array(results)
        return np.mean(results, axis=0)

    def detect(self, data: pd.DataFrame) -> np.ndarray:
        # TODO: implement detection, check in the paper how is it done
        pass


if __name__ == '__main__':
    #


    # timestamp, values = dataset.data
    # labels = np.zeros_like(values, dtype=np.int32)
    #
    # timestamp, missing, (values, labels) = complete_timestamp(timestamp, (values, labels))
    #
    # train_values, mean, std = standardize_kpi(
    #     values, excludes=np.logical_or(labels, missing))
    #
    # model = Donut()
    # model.train(train_values, labels, missing, mean, std)
    # score = model.predict(values, missing)
    # print(score)

    from sops_anomaly.datasets import MNIST
    import datetime

    # mnist = MNIST()
    # x = mnist.get_train_samples(n_samples=1000)
    # index = []
    # now = datetime.datetime.now()
    # for i in range(len(x)):
    #     index.append(now + datetime.timedelta(minutes=i*1))
    # x.index = index

    from sops_anomaly.datasets.nab_samples import NabDataset

    dataset = NabDataset().data
    dataset['value2'] = dataset['value']
    model = Donut()
    model.train(dataset)

    p = model.predict(dataset)
    print(p)
