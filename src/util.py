"""
A collection of various utility functions that are not related to the core
model generation algorithms or another, more specific library. This includes
functions for reading/writing files, executing commands, parsing the command
line, and configuring logging.

Copyright 2020, 2021 Jerrad M. Genson

This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""


import re
import os
import json
import pickle
import logging
import argparse
import subprocess
from pathlib import Path
from collections import namedtuple

import numpy as np
import pandas as pd
import sklearn
from sklearn import svm
from sklearn import ensemble
from sklearn import discriminant_analysis
from sklearn import manifold
from sklearn import naive_bayes
from sklearn import cluster
from sklearn import neighbors

import scoring

# Path to the root of the git repository.
GIT_ROOT = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'])
GIT_ROOT = Path(GIT_ROOT.decode('utf-8').strip())

# Path to the commit hash file.
COMMIT_HASH_FILE = GIT_ROOT / 'build/commit_hash'

# Identifies a machine learning algorithm's name and sklearn class.
MLAlgorithm = namedtuple('MLAlgorithm', 'name class_')

# Machine learning algorithms that can be used to generate a model.
# Keys are three-letter algorithm abbreviations.
# Values are MLAlgorithm objects.
SUPPORTED_ALGORITHMS = {
    'svm': MLAlgorithm('support vector machine',
                       svm.SVC),
    'rfc': MLAlgorithm('random forest',
                       ensemble.RandomForestClassifier),
    'etc': MLAlgorithm('extra trees',
                       ensemble.ExtraTreesClassifier),
    'gbc': MLAlgorithm('gradient boosting',
                       ensemble.GradientBoostingClassifier),
    'sgd': MLAlgorithm('stochastic gradient descent',
                       sklearn.linear_model.SGDClassifier),
    'rrc': MLAlgorithm('ridge regression',
                       sklearn.linear_model.RidgeClassifier),
    'lrc': MLAlgorithm('logistic regression',
                       sklearn.linear_model.LogisticRegression),
    'nbc': MLAlgorithm('naive bayes classifier',
                       naive_bayes.GaussianNB),
    'lda': MLAlgorithm('linear discriminant analysis',
                       discriminant_analysis.LinearDiscriminantAnalysis),
    'qda': MLAlgorithm('quadratic discriminant analysis',
                       discriminant_analysis.QuadraticDiscriminantAnalysis),
    'dtc': MLAlgorithm('decision tree',
                       sklearn.tree.DecisionTreeClassifier),
    'knn': MLAlgorithm('k-nearest neighbors',
                       sklearn.neighbors.KNeighborsClassifier),
    'rnc': MLAlgorithm('radius neighbors',
                       sklearn.neighbors.RadiusNeighborsClassifier),
}

# Possible preprocessing methods that can be used to prepare data for
# a model.
PREPROCESSING_METHODS = {
    'standard scaling': sklearn.preprocessing.StandardScaler,
    'robust scaling': sklearn.preprocessing.RobustScaler,
    'quantile transformer': sklearn.preprocessing.QuantileTransformer,
    'power transformer': sklearn.preprocessing.PowerTransformer,
    'normalize': sklearn.preprocessing.Normalizer,
    'pca': sklearn.decomposition.PCA,
    'ica': sklearn.decomposition.FastICA,
    'isomap': manifold.Isomap,
    'lle': manifold.LocallyLinearEmbedding,
    'feature agglomeration': cluster.FeatureAgglomeration,
    'nca': neighbors.NeighborhoodComponentsAnalysis,
    'factor analysis': sklearn.decomposition.FactorAnalysis,
}

# Stores values from the configuration file.
Config = namedtuple('Config',
                    ('training_dataset',
                     'validation_dataset',
                     'random_seed',
                     'scoring',
                     'algorithm',
                     'preprocessing_method'))

# Contains input data and target data for a single dataset.
Dataset = namedtuple('Dataset', 'inputs targets')

# Stores training and validation datasets together in a single object.
Datasets = namedtuple('Datasets', 'training validation columns')


def run_command(command):
    """
    Run the given command in a subprocess and return its output.

    Args
      command: The command to run as a string.

    Returns
      Standard output from the subprocess, decoded as a UTF-8 string.

    """

    return subprocess.check_output(re.split(r'\s+', command)).decode('utf-8').strip()


def load_datasets(training_dataset, validation_dataset):
    """
    Load training and validation datasets from the filesystem and return
    them as a Datasets object.

    Args
      training_dataset: Path to the training dataset.
      validation_dataset: Path to the validation dataset.

    Returns
      An instance of Datasets.

    """

    training_dataset = pd.read_csv(str(training_dataset))
    validation_dataset = pd.read_csv(str(validation_dataset))

    assert set(training_dataset.columns) == set(validation_dataset.columns)

    return Datasets(training=Dataset(inputs=split_inputs(training_dataset),
                                     targets=split_target(training_dataset)),
                    validation=Dataset(inputs=split_inputs(validation_dataset),
                                       targets=split_target(validation_dataset)),
                    columns=training_dataset.columns)


def split_inputs(dataframe):
    """
    Split the input columns out of the given dataframe and return them
    as a two-dimensional numpy array. All columns except the last column
    in the dataframe are considered to be input columns.

    """

    inputs = dataframe.to_numpy()[:, 0:-1]
    assert len(inputs) == len(dataframe)
    assert len(inputs[0]) == len(dataframe.columns) - 1

    return inputs


def split_target(dataframe):
    """
    Split the target column out of the given dataframe and return it
    as a one-dimensional numpy array. Only the last column in the
    dataframe is considered to the target column.

    """

    targets = dataframe.to_numpy()[:, -1]
    assert len(targets) == len(dataframe)
    assert np.ndim(targets) == 1

    return targets


def save_validation(dataset, output_path):
    """
    Save a validation dataset alongside a model.

    Args
      dataset: Validation dataset as a pandas dataframe.
      output_path: Path that the model was saved to.

    Returns
      None

    """

    dataset_path = output_path.with_name(output_path.stem + '.csv')
    dataset.to_csv(dataset_path, index=None)


def get_commit_hash():
    """
    Get the git commit hash of the current commit.

    Returns
      The current commit hash as a string. If there are uncommitted
      changes, or if the current working directory is not in a git
      reposistory, return the empty string instead.

    """

    logger = logging.getLogger(__name__)
    try:
        with COMMIT_HASH_FILE.open() as commit_hash_fd:
            commit_hash = commit_hash_fd.read().strip()

        return commit_hash

    except FileNotFoundError as file_not_found_error:
        logger.debug(file_not_found_error)
        return ''


def parse_command_line(argv):
    """
    Parse the command line using argparse.

    Args
      argv: A list of command line arguments to parse.

    Returnsp
      A Namespace object returned by parse_args().

    """

    description = 'Generate a customizable classification model with a wide '
    description += 'variety of preprocessing and model configurations.'
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('target',
                        type=Path,
                        help='Output path to save the model to.')

    parser.add_argument('training',
                        type=Path,
                        help='Path to the training dataset.')

    parser.add_argument('validation',
                        type=Path,
                        help='Path to the validation dataset.')

    parser.add_argument('--cpu',
                        type=int,
                        default=os.cpu_count(),
                        help='Number of processes to use for training models.')

    parser.add_argument('--log-level',
                        choices=('critical', 'error', 'warning', 'info', 'debug'),
                        default='info',
                        help='Log level to configure logging with.')

    parser.add_argument('--cross-validate',
                        type=int,
                        default=0,
                        help='Cross-validate the model using the specified number of folds.')

    parser.add_argument('--outlier-scores',
                        action='store_true',
                        help='Score model on outliers in the testing data.')

    parser.add_argument('--model',
                        choices=SUPPORTED_ALGORITHMS,
                        default='qda',
                        help='Algorithm to use to generate the model.')

    parser.add_argument('--preprocessing',
                        choices=PREPROCESSING_METHODS,
                        default=[],
                        nargs='+',
                        help='Preprocessing methods to use in the generated model.')

    parser.add_argument('--scoring',
                        choices=scoring.scoring_methods(),
                        default='accuracy',
                        help='Scoring method to use for model hyperparameter tuning.')

    parser.add_argument('--random-state',
                        type=int,
                        default=0,
                        help='State to initialize random number generators with.')

    parser.add_argument('--parameter-grid',
                        type=json.loads,
                        help='Parameter grid to use with grid search (as a json string).')

    parser.add_argument('--print-hyperparameters',
                        action='store_true',
                        help='Print hyperparameter values of the final model.')

    return parser.parse_args(argv)


def configure_logging(log_level, logfile_path):
    """
    Configure the logger for the current module.

    """

    log_level_number = getattr(logging, log_level.upper())
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level_number)
    console_formatter = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(logfile_path)
    file_handler.setLevel(log_level_number)
    file_formatter = logging.Formatter('%(asctime)s %(name)s %(levelname)s: %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)


def save_model(model, output_path):
    """
    Save the given model to disk.

    Args
      model: An instance of a scikit-learn estimator.
      output_path: The path to save the model to as a Path object.

    Returns
      None

    """

    with output_path.open('wb') as output_file:
        pickle.dump(model, output_file)
