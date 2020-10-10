"""
Generate a machine learning model to classify subjects as positive or
negative for ischemic heart disease. Full reproducibility is provided by
placing all configuration parameters, datasets, and random number
generator seeds in the repository and associating the generated model
with the commit hash.

Copyright 2020 Jerrad M. Genson

This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.
pp

Configuration
=============
All configuration parameters that may affect the behavior of the model
are located in the file 'config.json' located in the root directory of
the reposistory. The parameters in this file are described individually
below.

- training_dataset: the path to the training dataset starting from the
  root of the repository.

- validation_dataset: the path to the validation dataset starting from the
  root of the reposistory.

- random_seed: an integer to seed the random number generators with.

- scoring: the method to use for scoring candidate models during model
  generation. Possible values are 'accuracy', 'precision', 'sensitivity',
  'specificity', and 'informedness' (Youden's J statistic).

- algorithm: the machine learning algorithm to use for generating the
  model. Possible values are 'svm' (support vector machine),
  'knn' (k-nearest neighbors), 'rfc' (random forest classifier), and
  'sgd' (stochastic gradient descent).

- algorithm_parameters: a list of parameter dicts that is used during
  grid search to tune the hyperparameters of the model. A complete list
  of available parameters and their values can be found in the
  scikit-learn user manual located at:
  https://scikit-learn.org/stable/supervised_learning.html
  This parameter can be omitted if you wish to use the default values
  for the model's hyperparameters.


Command Line Arguments
======================
In addition to the parameters in the configuration file, some additional
arguments may be supplied via the command line. These are described below.
None of these parameters affect the behavior of the generated model.

usage: build_model.py [-h] [-o OUTPUT_PATH] [--cpu CPU]
                      [--log_level {critical,error,warning,info,debug}]

  -h, --help            show this help message and exit
  -o OUTPUT_PATH, --output_path OUTPUT_PATH
                        Path to output the heart disease model to.
  --cpu CPU             Number of processes to use for training models.
  --log_level {critical,error,warning,info,debug}
                        Log level to configure logging with.


Output Path
===========
By default, the output path for generated models is (starting from the
reposistory root): build/heart_disease_model.dat
A CSV file containing the generated model's predictions appended to the
validation dataset is saved alongside the model. This file is given the same
name as the model, with '.dat' replaced by '_validation.csv' (by default,
'heart_disease_model_validation.csv').

"""

import random
import argparse
import logging
import pickle
import time
import subprocess
import os
import re
import sys
import platform
import json
import datetime
from pathlib import Path
from collections import namedtuple

import numpy as np
import scipy as sp
from scipy.stats import median_abs_deviation
import pandas as pd
import joblib
import threadpoolctl
import sklearn
from sklearn import svm
from sklearn import ensemble
from sklearn import discriminant_analysis
from sklearn.pipeline import Pipeline

import scoring

# Path to the root of the git repository.
GIT_ROOT = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'])
GIT_ROOT = Path(GIT_ROOT.decode('utf-8').strip())

# URL for the repository on Github.
GITHUB_URL = 'https://github.com/jerradmgenson/cardiac'

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
    'sgd': MLAlgorithm('stochastic gradient descent',
                       sklearn.linear_model.SGDClassifier),
    'rrc': MLAlgorithm('ridge regression classifier',
                       sklearn.linear_model.RidgeClassifier),
    'lrc': MLAlgorithm('logistic regression classifier',
                       sklearn.linear_model.LogisticRegression),
    'lda': MLAlgorithm('linear discriminant analysis',
                       discriminant_analysis.LinearDiscriminantAnalysis),
    'qda': MLAlgorithm('quadratic discriminant analysis',
                       discriminant_analysis.QuadraticDiscriminantAnalysis),
    'dtc': MLAlgorithm('decision tree',
                       sklearn.tree.DecisionTreeClassifier),
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
}

# Stores values from the configuration file.
Config = namedtuple('Config',
                    ('training_dataset',
                     'validation_dataset',
                     'random_seed',
                     'scoring',
                     'algorithm',
                     'algorithm_parameters',
                     'preprocessing_methods',
                     'pca_whiten',
                     'pca_components'))

# Contains input data and target data for a single dataset.
Dataset = namedtuple('Dataset', 'inputs targets')

# Stores training and validation datasets together in a single object.
Datasets = namedtuple('Datasets', 'training validation columns')


class ExitCode:
    """
    Enumerates possible exit codes.

    """

    SUCCESS = 0
    INVALID_CONFIG = 1


def main(argv):
    """
    Program's main function. Primary execution starts here.

    """

    start_time = time.time()
    command_line_arguments = parse_command_line(argv)
    logfile_path = command_line_arguments.target.with_name(
        command_line_arguments.target.stem + '.log')

    logger = configure_logging(command_line_arguments.log_level, logfile_path)
    print('Reading configuration file...')
    try:
        config = read_config_file(command_line_arguments.config)

    except InvalidConfigError as invalid_config_error:
        logger.error(invalid_config_error)
        return ExitCode.INVALID_CONFIG

    random.seed(config.random_seed)
    np.random.seed(config.random_seed)
    print('Loading datasets...')
    datasets = load_datasets(config.training_dataset,
                             config.validation_dataset)

    print(f'Training dataset:      {config.training_dataset}')
    print(f'Validation dataset:    {config.validation_dataset}')
    print(f'Random number seed:    {config.random_seed}')
    print(f'Scoring method:        {config.scoring}')
    print(f'Algorithm:             {config.algorithm.name}')
    print(f'Preprocessing methods: {config.preprocessing_methods}')
    print(f'Training samples:      {len(datasets.training.inputs)}')
    print(f'Validation samples:    {len(datasets.validation.inputs)}')
    score_function = scoring.create_scorer(config.scoring)
    print('Generating model...')
    model = train_model(config.algorithm.class_,
                        datasets.training.inputs,
                        datasets.training.targets,
                        score_function,
                        config.preprocessing_methods,
                        n_components=config.pca_components,
                        whiten=config.pca_whiten,
                        cpus=command_line_arguments.cpu,
                        parameter_grid=config.algorithm_parameters)

    print('Scoring model...')
    model_scores = scoring.score_model(model,
                                       datasets.validation.inputs,
                                       datasets.validation.targets)

    if command_line_arguments.cross_validate:
        median_scores, mad_scores = cross_validate(model,
                                                   datasets,
                                                   command_line_arguments.cross_validate)

        bind_model_metadata(model, model_scores,
                            cross_validation_scores=(median_scores,
                                                     mad_scores,
                                                     command_line_arguments.cross_validate))

    else:
        bind_model_metadata(model, model_scores)

    predictions = model.predict(datasets.validation.inputs)
    validation_dataset = create_validation_dataset(datasets.validation.inputs,
                                                   datasets.validation.targets,
                                                   predictions,
                                                   datasets.columns[:-1])

    print('\nSaving model to disk...')
    save_validation(validation_dataset, command_line_arguments.target)
    save_model(model, command_line_arguments.target)
    print(f'Saved model to {command_line_arguments.target}')
    runtime = f'Runtime: {time.time() - start_time:.2} seconds'
    logger.debug(runtime)

    return ExitCode.SUCCESS


def create_validation_dataset(input_data, target_data, prediction_data, columns):
    """
    Create a Pandas DataFrame that shows how input samples and expected target
    data corresponds to the actual outputs predicted by the model.

    Args
      input_data: A 2D numpy array of inputs to the model, where each
                  row of the array represents a sample and each column
                  represents a feature.
      target_data: A 1D numpy array of model targets. Each element is an
                   expected output for the corresponding sample in the
                   input_data array.
      predicted_data: A 1D numpy array of model targets. Each element is an
                      actual model output for the corresponding sample in the
                      input_data array.
      columns: A list of column names for the model input data.

    Returns
      An instance of pandas.DataFrame.

    """

    validation_dataset = pd.DataFrame(data=input_data, columns=columns)
    validation_dataset['target'] = target_data
    validation_dataset['prediction'] = prediction_data

    assert len(validation_dataset) == len(input_data)
    assert len(validation_dataset.columns) == len(columns) + 2

    return validation_dataset


def run_command(command):
    """
    Run the given command in a subprocess and return its output.

    Args
      command: The command to run as a string.

    Returns
      Standard output from the subprocess, decoded as a UTF-8 string.

    """

    return subprocess.check_output(re.split(r'\s+', command)).decode('utf-8').strip()


def bind_model_metadata(model, scores, cross_validation_scores=None):
    """
    Generate metadata and bind it to the model. The following attributes
    will be assigned to `model`:

    - commit_hash
    - validated
    - repository
    - numpy_version
    - scipy_version
    - pandas_version
    - sklearn_version
    - joblib_version
    - threadpoolctl_version
    - operating_system
    - architecture
    - created
    - author

    Args
      model: An instance of a scikit-learn estimator.
      scores: A scores dict returned by `score_model`.
      cross_validation_scores: (Default=None) A 3-tuple of cross-validation scores
                               consisting of (median_scores, mad_scores, n_splits).

    Returns
      None

    """

    print('\nModel scores:')
    model_attributes = len(dir(model))
    score_count = 0
    for metric, score in scores.items():
        if score:
            score_count += 1
            setattr(model, metric, score)
            msg = '{metric:13} {score:.4}'.format(metric=metric + ':', score=score)
            print(msg)

    assert len(dir(model)) - model_attributes == score_count
    model_attributes = len(dir(model))

    if cross_validation_scores:
        median_scores = cross_validation_scores[0]
        mad_scores = cross_validation_scores[1]
        n_splits = cross_validation_scores[2]
        print(f'\n{n_splits}-fold cross-validation scores:')
        score_count = 0
        for metric, median_score, mad_score in zip(mad_scores, median_scores.values(), mad_scores.values()):
            if median_score:
                score_count += 2
                setattr(model, 'median_' + metric, median_score)
                setattr(model, 'mad_' + metric, mad_score)
                median_msg = '{metric:20} {score:.4}'.format(metric='median ' + metric + ':',
                                                             score=median_score)

                mad_msg = '{metric:20} {score:.4}'.format(metric='mad ' + metric + ':',
                                                          score=mad_score)

                print(median_msg)
                print(mad_msg)

        assert len(dir(model)) - model_attributes == score_count
        model_attributes = len(dir(model))

    model.commit_hash = get_commit_hash()
    model.validated = False
    model.repository = GITHUB_URL
    model.numpy_version = np.version.version
    model.scipy_version = sp.version.version
    model.pandas_version = pd.__version__
    model.sklearn_version = sklearn.__version__
    model.joblib_version = joblib.__version__
    model.threadpoolctl_version = threadpoolctl.__version__
    model.operating_system = platform.system() + ' ' + platform.version() + ' ' + platform.release()
    model.architecture = platform.processor()
    model.created = datetime.datetime.today().isoformat()
    try:
        username = run_command('git config user.name')
        email = run_command('git config user.email')

    except subprocess.CalledProcessError:
        username = ''
        email = ''

    model.author = '{} <{}>'.format(username, email)

    assert len(dir(model)) - model_attributes == 13


def train_model(model_class,
                input_data,
                target_data,
                score_function,
                preprocessing_methods,
                n_components=None,
                whiten=False,
                cpus=1,
                parameter_grid=None):

    """
    Train a machine learning model on the given data.

    Args
      model_class: A scikit-learn estimator class e.g. 'sklearn.svm.SVC'.
      input_data: A 2D numpy array of inputs to the model, where each
                  row of the array represents a sample and each column
                  represents a feature.
      target_data: A 1D numpy array of model targets. Each element is an
                   expected output for the corresponding sample in the
                   input_data array.
      score_function: A function that takes three parameters - an
                      estimator, an array of input data, and an array
                      of target data, and returns a score as a float,
                      where higher numbers are better.
      preprocessing_methods: A sequence of methods to use to preprocess the data
                             before feeding it to the model. Must be a subset of
                            'PREPROCESSING_METHODS'.
      n_components: (Default=None) The number of components to keep when using
                    principal component analysis. Ignored unless one of
                    'preprocessing_methods' is 'pca' or 'lda'.
      whiten: (Default=False) Whether to whiten the data when using principal
              component analysis. Ignored unless 'pca' in 'processing_methods'.
      cpus: (Default=1) Number of processes to use for training the model.
      parameter_grid: (Default=None) A sequence of dicts with possible
                      hyperparameter values. Used for tuning the
                      hyperparameters. When present, grid search will be
                      used to train the model.

    Returns
      A trained scikit-learn estimator object.

    """

    pipeline_steps = []
    for preprocessing_method in preprocessing_methods:
        if preprocessing_method == 'pca':
            preprocessor_class = PREPROCESSING_METHODS[preprocessing_method]
            preprocessor = preprocessor_class(n_components=n_components,
                                              whiten=whiten)

            pipeline_steps.append((preprocessing_method, preprocessor))

        else:
            preprocessor = PREPROCESSING_METHODS[preprocessing_method]()
            pipeline_steps.append((preprocessing_method, preprocessor))

    pipeline_steps.append(('model', model_class()))
    pipeline = Pipeline(steps=pipeline_steps)
    assert len(pipeline) == len(preprocessing_methods) + 1
    if parameter_grid:
        grid_estimator = sklearn.model_selection.GridSearchCV(pipeline,
                                                              parameter_grid,
                                                              scoring=score_function,
                                                              n_jobs=cpus)

        grid_estimator.fit(input_data, target_data)
        model = grid_estimator.best_estimator_

    else:
        model = pipeline
        model.fit(input_data, target_data)

    return model


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


def read_config_file(path):
    """
    Read a json configuration file into memory.

    Args
      path: Path to the configuration file (as a Path object).

    Returns
      A Config object.

    """

    logger = logging.getLogger(__name__)
    with path.open() as config_fp:
        try:
            config_json = json.load(config_fp)

        except json.decoder.JSONDecodeError as json_decode_error:
            logger.debug(json_decode_error)
            raise InvalidConfigError(f'{path} does not contain valid json.')

    assert is_valid_config(config_json)
    config_json['training_dataset'] = os.path.join(str(GIT_ROOT),
                                                   config_json['training_dataset'])

    config_json['validation_dataset'] = os.path.join(str(GIT_ROOT),
                                                     config_json['validation_dataset'])

    config_json['algorithm'] = SUPPORTED_ALGORITHMS[config_json['algorithm']]
    if 'algorithm_parameters' not in config_json:
        config_json['algorithm_parameters'] = []

    # Prepend algorithm parameters with `model__` so they can be fed to
    # scikit-learn Pipeline without raising a ValueError.
    modified_algorithm_parameters = []
    for parameter_set in config_json['algorithm_parameters']:
        modified_parameter_set = {'model__' + key: value for key, value in parameter_set.items()}
        modified_algorithm_parameters.append(modified_parameter_set)

    config_json['algorithm_parameters'] = modified_algorithm_parameters

    return Config(**config_json)


def is_valid_config(config):
    """
    Check that loaded json config file contains only valid parameters.

    Args
      config: A dict corresponding to a json config file.

    Returns
      True if `config` is valid.

    Raises
      InvalidConfigError if `config` is invalid.

    """

    logger = logging.getLogger(__name__)
    config_parameters = ('training_dataset',
                         'validation_dataset',
                         'random_seed',
                         'scoring',
                         'preprocessing_methods',
                         'pca_components',
                         'pca_whiten',
                         'algorithm',
                         'algorithm_parameters')

    if not isinstance(config, dict):
        raise InvalidConfigError('config must be a dict.')

    if set(config) != set(config_parameters) and set(config) != set(config_parameters[:-1]):
        raise InvalidConfigError('Config file contains invalid parameters.')

    try:
        GIT_ROOT / Path(config['training_dataset'])

    except TypeError as type_error:
        logger.debug(type_error)
        raise InvalidConfigError('`training_dataset` must be a path.')

    try:
        GIT_ROOT / Path(config['validation_dataset'])

    except TypeError as type_error:
        logger.debug(type_error)
        raise InvalidConfigError('`validation_dataset` must be a path.')

    try:
        if int(config['random_seed']) > 2**32 - 1 or int(config['random_seed']) < 0:
            raise InvalidConfigError('`random_seed` must be between 0 and 2**32 - 1.')

    except ValueError as value_error:
        logger.debug(value_error)
        raise InvalidConfigError('`random_seed` not an integer.')

    if config['scoring'] not in scoring.SCORING_METHODS:
        raise InvalidConfigError(f'`scoring` must be one of `{scoring.SCORING_METHODS}`.')

    try:
        if not set(config['preprocessing_methods']) <= set(PREPROCESSING_METHODS):
            err = f'`preprocessing_methods` must be in {set(PREPROCESSING_METHODS)}.'
            raise InvalidConfigError(err)

    except TypeError as type_error:
        logger.debug(type_error)
        raise InvalidConfigError('`preprocessing_methods` must be a list.')

    try:
        if int(config['pca_components']) <= 0:
            raise InvalidConfigError('`pca_components` must be greater than 0.')

    except TypeError as type_error:
        logger.debug(type_error)
        raise InvalidConfigError('`pca_components` must be an integer.')

    if not isinstance(config['pca_whiten'], bool):
        raise InvalidConfigError('`pca_whiten` must be a boolean.')

    if config['algorithm'] not in SUPPORTED_ALGORITHMS:
        raise InvalidConfigError(f'`algorithm` must be one of {list(SUPPORTED_ALGORITHMS)}.')

    if 'algorithm_parameters' in config:
        try:
            parameter_grid = sklearn.model_selection.ParameterGrid(config['algorithm_parameters'])

        except TypeError as type_error:
            logger.debug(type_error)
            raise InvalidConfigError('`algorithm_parameters` must be a dict or a list.')

        try:
            [SUPPORTED_ALGORITHMS[config['algorithm']].class_(**x) for x in parameter_grid]

        except TypeError as type_error:
            logger.debug(type_error)
            invalid_parameter = re.search(r"keyword argument '(\w+)'", str(type_error)).group(1)
            err = f'`{invalid_parameter}` is not a valid parameter for `{config["algorithm"]}`.'
            raise InvalidConfigError(err)

    return True


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
        if run_command('git diff'):
            return ''

        return run_command('git rev-parse --verify HEAD')

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

    description = 'Generate a probabalistic classification model.'
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('target',
                        type=Path,
                        help='Output path to save the model to.')

    parser.add_argument('config',
                        type=Path,
                        help='Path to the gen_model configuration file.')

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

    return parser.parse_args(argv)


def configure_logging(log_level, logfile_path):
    """
    Configure the logger for the current module.

    Returns
      A Logger object for the current module.

    """

    log_level_number = getattr(logging, log_level.upper())
    logger = logging.getLogger(__name__)
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

    return logger


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


def cross_validate(model, datasets, n_splits):
    """
    Cross-validate a model by splitting the dataset into training/validation
    sets numerous times and calculating summary statistics for the model scores.

    Args:
      model: An trained instance of a scikit-learn estimator.
      datasets: An instance of Datasets.
      n_splits: Number of splits (or folds) to use in cross-validation.

    Returns:
     A 2-tuple of Scores objects, where the first element is the median of all
     the models' scores, and the second element is the median absolute deviation
     of all the models' scores.

    """

    inputs = np.concatenate((datasets.training.inputs,
                             datasets.validation.inputs))

    assert len(inputs) == len(datasets.training.inputs) + len(datasets.validation.inputs)
    targets = np.concatenate((datasets.training.targets,
                              datasets.validation.targets))

    assert len(targets) == len(datasets.training.targets) + len(datasets.validation.targets)
    kfold = sklearn.model_selection.KFold(n_splits=n_splits)
    scores_lists = dict()
    for training_index, testing_index in kfold.split(inputs):
        training_inputs = inputs[training_index]
        training_targets = targets[training_index]
        testing_inputs = inputs[testing_index]
        testing_targets = targets[testing_index]

        new_model = sklearn.clone(model)
        new_model.fit(training_inputs, training_targets)
        scores = scoring.score_model(new_model, testing_inputs, testing_targets)
        for metric, score in scores.items():
            if score is None or np.isnan(score):
                continue

            if metric in scores_lists:
                scores_lists[metric].append(score)

            else:
                scores_lists[metric] = [score]

    median_scores = dict()
    mad_scores = dict()
    for metric, score_list in scores_lists.items():
        assert len(score_list) <= n_splits
        median_scores[metric] = np.median(score_list)
        mad_scores[metric] = median_abs_deviation(score_list)

    return median_scores, mad_scores


class InvalidConfigError(Exception):
    """
    Raised when the config file is not valid.

    """


if __name__ == '__main__':  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
