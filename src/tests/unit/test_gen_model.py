"""
Unit tests for gen_model.py

"""

import unittest
import random
from unittest.mock import patch, Mock

import sklearn
import numpy as np
import scipy as sp
import pandas as pd

import gen_model


class CreateValidationDatasetTest(unittest.TestCase):
    """
    Tests for gen_model.create_validation_dataset()

    """

    def test_create_validation_dataset(self):
        """
        Test create_validation_dataset() on typical inputs.

        """

        input_data = np.array([[1, 2, 3], [4, 5, 6]])
        target_data = np.array([2, 5])
        prediction_data = np.array([3, 6])
        columns = ['col1', 'col2', 'col3']
        target_dataset = pd.DataFrame([[1, 2, 3, 2, 3], [4, 5, 6, 5, 6]],
                                      columns=columns + ['target', 'prediction'])

        validation_dataset = gen_model.create_validation_dataset(input_data,
                                                                 target_data,
                                                                 prediction_data,
                                                                 columns)

        self.assertTrue(target_dataset.eq(validation_dataset).all().all())


class GetCommitHashTest(unittest.TestCase):
    """
    Tests for gen_model.get_commit_hash()

    """

    def test_git_call_success(self):
        """
        Test get_commit_hash() when calls to git are successful.

        """

        def create_run_command_mock():
            def run_command_mock(command):
                if command == 'git diff':
                    return ''

                elif command == 'git rev-parse --verify HEAD':
                    return '26223577219e04975a8ea93b95d0ab047a0ea536'

                assert False

            return run_command_mock

        run_command_patch = patch.object(gen_model,
                                         'run_command',
                                         new_callable=create_run_command_mock)

        with run_command_patch:
            commit_hash = gen_model.get_commit_hash()

        self.assertEqual(commit_hash, '26223577219e04975a8ea93b95d0ab047a0ea536')

    def test_empty_git_diff(self):
        """
        Test get_commit_hash() when git diff returns the empty string.

        """

        run_command_patch = patch.object(gen_model,
                                         'run_command',
                                         return_value='')

        with run_command_patch:
            commit_hash = gen_model.get_commit_hash()

        self.assertEqual(commit_hash, '')

    def test_file_not_found_error(self):
        """
        Test get_commit_hash() when git can not be found

        """

        def create_run_command_mock():
            def run_command_mock(command):
                raise FileNotFoundError()

            return run_command_mock

        run_command_patch = patch.object(gen_model,
                                         'run_command',
                                         new_callable=create_run_command_mock)

        with run_command_patch:
            commit_hash = gen_model.get_commit_hash()

        self.assertEqual(commit_hash, '')


class RunCommandTest(unittest.TestCase):
    """
    Tests for gen_model.run_command()

    """

    def test_run_command(self):
        """
        Test run_command() on a typical input.

        """

        check_output_patch = patch.object(gen_model.subprocess,
                                          'check_output',
                                          return_value=b'bbd155263aeaae63c12ad7498a0594fb2ff8d615\n')

        with check_output_patch as check_output_mock:
            command_output = gen_model.run_command('git rev-parse --verify HEAD')

        self.assertEqual(check_output_mock.call_count, 1)
        self.assertEqual(check_output_mock.call_args[0][0],
                         ['git', 'rev-parse', '--verify', 'HEAD'])

        self.assertEqual(command_output,
                         'bbd155263aeaae63c12ad7498a0594fb2ff8d615')


class TrainModelTest(unittest.TestCase):
    """
    Tests for gen_model.train_model()

    """

    def setUp(self):
        random.seed(326717227)
        sp.random.seed(326717227)

    def test_svm_classifier(self):
        """
        Test train_model() with SVM classifier.

        """

        grid = [{'model__C': [1, 2, 3], 'model__kernel': ['linear', 'rbf']}]
        inputs = np.array([[0, 0], [0, 1], [1, 0], [1, 1],
                           [0, 0], [0, 1], [1, 0], [1, 1],
                           [0, 0], [0, 1], [1, 0], [1, 1]])

        targets = np.array([-1, 1, 1, -1, -1, 1, 1, -1, -1, 1, 1, -1])
        score = gen_model.create_scorer('informedness')
        model = gen_model.train_model(sklearn.svm.SVC,
                                      inputs,
                                      targets,
                                      score,
                                      ['standard scaling'],
                                      parameter_grid=grid,
                                      cpus=1)

        self.assertEqual(len(model.steps), 2)
        self.assertEqual(model.steps[0][0], 'standard scaling')
        self.assertEqual(model.steps[1][0], 'model')
        self.assertTrue((model.predict(inputs) == targets).all())

    def test_qda_classifier(self):
        """
        Test train_model() with QDA classifier.

        """

        inputs = np.array([[-4], [-3], [-2], [-1], [1], [2], [3], [4]])
        targets = np.array([-1, -1, -1, -1, 1, 1, 1, 1])
        score = gen_model.create_scorer('accuracy')
        model = gen_model.train_model(sklearn.discriminant_analysis.QuadraticDiscriminantAnalysis,
                                      inputs,
                                      targets,
                                      score,
                                      [],
                                      cpus=2)

        self.assertEqual(len(model.steps), 1)
        self.assertEqual(model.steps[0][0], 'model')
        self.assertTrue((model.predict(inputs) == targets).all())

    def test_sgd_classifier(self):
        """
        Test train_model() with SGD classifier.

        """

        inputs = np.array([[-4], [-3], [-2], [-1], [1], [2], [3], [4]])
        targets = np.array([-1, -1, -1, -1, 1, 1, 1, 1])
        score = gen_model.create_scorer('precision')
        model = gen_model.train_model(sklearn.linear_model.SGDClassifier,
                                      inputs,
                                      targets,
                                      score,
                                      ['pca', 'robust scaling'],
                                      cpus=4)

        self.assertEqual(len(model.steps), 3)
        self.assertEqual(model.steps[0][0], 'pca')
        self.assertEqual(model.steps[1][0], 'robust scaling')
        self.assertEqual(model.steps[2][0], 'model')
        self.assertTrue(model.predict(inputs).any())


class SplitInputsTests(unittest.TestCase):
    """
    Tests for gen_model.split_inputs

    """

    def test_split_inputs(self):
        """
        Test split_inputs() on a typical input.

        """

        data = pd.DataFrame([[0, 0, 0], [0, 1, 1], [1, 0, 1], [1, 1, 0]])
        inputs = gen_model.split_inputs(data)
        self.assertTrue((inputs == np.array([[0, 0], [0, 1], [1, 0], [1, 1]])).all())


class SplitTargetTests(unittest.TestCase):
    """
    Tests for gen_model.split_inputs

    """

    def test_split_target(self):
        """
        Test split_target() on a typical input.

        """

        data = pd.DataFrame([[0, 0, 0], [0, 1, 1], [1, 0, 1], [1, 1, 0]])
        inputs = gen_model.split_target(data)
        self.assertTrue((inputs == np.array([0, 1, 1, 0])).all())


class CreateScorerTests(unittest.TestCase):
    """
    Tests for gen_model.create_scorer

    """

    def test_informedness_metric(self):
        """
        Test create_scorer() with informedness scoring metric.

        """

        inputs = np.array([0, 0, 0, 0])
        targets = np.array([0, 1, 0, 1])
        model = Mock()
        model.predict = Mock(return_value=np.array([0, 1, 1, 0]))
        scorer = gen_model.create_scorer('informedness')
        score = scorer(model, inputs, targets)
        self.assertEqual(score, 0.0)

    def test_accuracy_metric(self):
        """
        Test create_scorer() with accuracy scoring metric.

        """

        inputs = np.array([0, 0, 0, 0])
        targets = np.array([0, 1, 0, 1])
        model = Mock()
        model.predict = Mock(return_value=np.array([0, 1, 1, 0]))
        scorer = gen_model.create_scorer('accuracy')
        score = scorer(model, inputs, targets)
        self.assertEqual(score, 0.5)

    def test_scorer_with_invalid_metric(self):
        """
        Test create_scorer() with a scoring metric that is invalid for
        the given type of classification.

        """

        inputs = np.array([1, 2, 3, 4])
        targets = np.array([1, 2, 3, 4])
        model = Mock()
        model.predict = Mock(return_value=np.array([1, 2, 3, 4]))
        scorer = gen_model.create_scorer('sensitivity')
        with self.assertRaises(ValueError):
            scorer(model, inputs, targets)


class CalculateHmeanRecallTests(unittest.TestCase):
    """
    Tests for gen_model.calculate_hmean_recall

    """

    def test_100_percent_correct(self):
        """
        Test calculate_hmean_recall() with 100% correct recall.

        """

        report = dict(a=dict(recall=1.0),
                      b=dict(recall=1.0),
                      c=dict(recall=1.0),
                      d=dict(recall=1.0))

        classes = report.keys()
        hmean_recall = gen_model.calculate_hmean_recall(report, classes)
        self.assertEqual(hmean_recall, 1.0)

    def test_random_recalls1(self):
        """
        Test calculate_hmean_recall() with randomly-generated recall values.

        """

        report = dict(a=dict(recall=0.0161),
                      b=dict(recall=0.8070),
                      c=dict(recall=0.1344),
                      d=dict(recall=0.0156),
                      e=dict(recall=0.6629))

        classes = report.keys()
        hmean_recall = gen_model.calculate_hmean_recall(report, classes)
        self.assertAlmostEqual(hmean_recall, 0.0366562)

    def test_random_recalls2(self):
        """
        Test calculate_hmean_recall() with randomly-generated recall values.

        """

        report = dict(a=dict(recall=0.3014),
                      b=dict(recall=0.2736),
                      c=dict(recall=0.2339))

        classes = report.keys()
        hmean_recall = gen_model.calculate_hmean_recall(report, classes)
        self.assertAlmostEqual(hmean_recall, 0.2667105)


class CalculateHmeanPrecisionTests(unittest.TestCase):
    """
    Tests for gen_model.calculate_hmean_precision

    """

    def test_100_percent_correct(self):
        """
        Test calculate_hmean_precision() with 100% correct precision.

        """

        report = dict(a=dict(precision=1.0),
                      b=dict(precision=1.0),
                      c=dict(precision=1.0),
                      d=dict(precision=1.0))

        classes = report.keys()
        hmean_precision = gen_model.calculate_hmean_precision(report, classes)
        self.assertEqual(hmean_precision, 1.0)

    def test_random_precisions1(self):
        """
        Test calculate_hmean_precision() with randomly-generated precision values.

        """

        report = dict(a=dict(precision=0.0161),
                      b=dict(precision=0.8070),
                      c=dict(precision=0.1344),
                      d=dict(precision=0.0156),
                      e=dict(precision=0.6629))

        classes = report.keys()
        hmean_precision = gen_model.calculate_hmean_precision(report, classes)
        self.assertAlmostEqual(hmean_precision, 0.0366562)

    def test_random_precisions2(self):
        """
        Test calculate_hmean_precision() with randomly-generated precision values.

        """

        report = dict(a=dict(precision=0.3014),
                      b=dict(precision=0.2736),
                      c=dict(precision=0.2339))

        classes = report.keys()
        hmean_precision = gen_model.calculate_hmean_precision(report, classes)
        self.assertAlmostEqual(hmean_precision, 0.2667105)


class CalculateInformednessTests(unittest.TestCase):
    """
    Tests for gen_model.calculate_informedness

    """

    def test_100_percent_correct_binary_classification(self):
        """
        Test calculate_informedness() with 100% correct binary classification.

        """

        report = dict(a=dict(recall=1.0),
                      b=dict(recall=1.0))

        classes = report.keys()
        informedness = gen_model.calculate_informedness(report, classes)
        self.assertEqual(informedness, 1.0)

    def test_50_percent_correct_binary_classification(self):
        """
        Test calculate_informedness() with 50% correct binary classification.

        """

        report = dict(a=dict(recall=0.5),
                      b=dict(recall=0.5))

        classes = report.keys()
        informedness = gen_model.calculate_informedness(report, classes)
        self.assertEqual(informedness, 0)

    def test_random_binary_classifications(self):
        """
        Test calculate_informedness() with random binary classifications.

        """

        report = dict(a=dict(recall=0.7572),
                      b=dict(recall=0.4744))

        classes = report.keys()
        informedness = gen_model.calculate_informedness(report, classes)
        self.assertAlmostEqual(informedness, 0.2316)

    def test_100_percent_correct_ternary_classification(self):
        """
        Test calculate_informedness() with 100% correct ternary classification.

        """

        report = dict(a=dict(recall=1.0),
                      b=dict(recall=1.0),
                      c=dict(recall=1.0))

        classes = report.keys()
        informedness = gen_model.calculate_informedness(report, classes)
        self.assertEqual(informedness, 1.0)

    def test_50_percent_correct_ternary_classification(self):
        """
        Test calculate_informedness() with 50% correct ternary classification.

        """

        report = dict(a=dict(recall=0.5),
                      b=dict(recall=0.5),
                      c=dict(recall=0.5))

        classes = report.keys()
        informedness = gen_model.calculate_informedness(report, classes)
        self.assertEqual(informedness, 0)

    def test_random_ternary_classifications(self):
        """
        Test calculate_informedness() with random ternary classifications.

        """

        report = dict(a=dict(recall=0.1859),
                      b=dict(recall=0.8663),
                      c=dict(recall=0.2619))

        classes = report.keys()
        informedness = gen_model.calculate_informedness(report, classes)
        self.assertAlmostEqual(informedness, -0.1239333)

    def test_100_percent_correct_quaternary_classification(self):
        """
        Test calculate_informedness() with 100% correct quaternary classification.

        """

        report = dict(a=dict(recall=1.0),
                      b=dict(recall=1.0),
                      c=dict(recall=1.0),
                      d=dict(recall=1.0))

        classes = report.keys()
        informedness = gen_model.calculate_informedness(report, classes)
        self.assertEqual(informedness, 1.0)

    def test_50_percent_correct_quaternary_classification(self):
        """
        Test calculate_informedness() with 50% correct quaternary classification.

        """

        report = dict(a=dict(recall=0.5),
                      b=dict(recall=0.5),
                      c=dict(recall=0.5),
                      d=dict(recall=0.5))

        classes = report.keys()
        informedness = gen_model.calculate_informedness(report, classes)
        self.assertEqual(informedness, 0)

    def test_random_quaternary_classifications(self):
        """
        Test calculate_informedness() with random quaternary classifications.

        """

        report = dict(a=dict(recall=0.9741),
                      b=dict(recall=0.8153),
                      c=dict(recall=0.3981),
                      d=dict(recall=0.4263))

        classes = report.keys()
        informedness = gen_model.calculate_informedness(report, classes)
        self.assertAlmostEqual(informedness, 0.3069)

    def test_100_percent_correct_quinary_classification(self):
        """
        Test calculate_informedness() with 100% correct quinary classification.

        """

        report = dict(a=dict(recall=1.0),
                      b=dict(recall=1.0),
                      c=dict(recall=1.0),
                      d=dict(recall=1.0),
                      e=dict(recall=1.0))

        classes = report.keys()
        informedness = gen_model.calculate_informedness(report, classes)
        self.assertEqual(informedness, 1.0)

    def test_50_percent_correct_quinary_classification(self):
        """
        Test calculate_informedness() with 50% correct quinary classification.

        """

        report = dict(a=dict(recall=0.5),
                      b=dict(recall=0.5),
                      c=dict(recall=0.5),
                      d=dict(recall=0.5),
                      e=dict(recall=0.5))

        classes = report.keys()
        informedness = gen_model.calculate_informedness(report, classes)
        self.assertEqual(informedness, 0)

    def test_random_quinary_classifications(self):
        """
        Test calculate_informedness() with random quinary classifications.

        """

        report = dict(a=dict(recall=0.4476),
                      b=dict(recall=0.4212),
                      c=dict(recall=0.3679),
                      d=dict(recall=0.2574),
                      e=dict(recall=0.5060))

        classes = report.keys()
        informedness = gen_model.calculate_informedness(report, classes)
        self.assertAlmostEqual(informedness, -0.19996)


class ScoreModelTests(unittest.TestCase):
    """
    Tests for gen_model.score_model

    """

    def test_100_percent_binary_classification(self):
        """
        Test score_model() with 100% correct binary classification.

        """

        input_data = np.array([0, 0, 0, 0])
        target_data = np.array([0, 1, 1, 0])
        model = Mock()
        model.predict = Mock(return_value=target_data)
        scores, _ = gen_model.score_model(model, input_data, target_data)
        self.assertEqual(model.predict.call_count, 1)
        self.assertTrue((model.predict.call_args[0][0] == input_data).all())
        self.assertEqual(scores.accuracy, 1.0)
        self.assertEqual(scores.precision, 1.0)
        self.assertEqual(scores.hmean_precision, 1.0)
        self.assertEqual(scores.hmean_recall, 1.0)
        self.assertEqual(scores.sensitivity, 1.0)
        self.assertEqual(scores.specificity, 1.0)
        self.assertEqual(scores.informedness, 1.0)

    def test_50_percent_binary_classification(self):
        """
        Test score_model() with 50% correct binary classification.

        """

        input_data = np.array([])
        target_data = np.array([0, 1, 0, 1])
        model = Mock()
        model.predict = Mock(return_value=np.array([0, 1, 1, 0]))
        scores, _ = gen_model.score_model(model, input_data, target_data)
        self.assertAlmostEqual(scores.accuracy, 0.5)
        self.assertAlmostEqual(scores.precision, 0.5)
        self.assertAlmostEqual(scores.hmean_precision, 0.5)
        self.assertAlmostEqual(scores.hmean_recall, 0.5)
        self.assertAlmostEqual(scores.sensitivity, 0.5)
        self.assertAlmostEqual(scores.specificity, 0.5)
        self.assertAlmostEqual(scores.informedness, 0)

    def test_random_binary_classifications(self):
        """
        Test score_model() with random binary classifications.

        """

        input_data = np.array([])
        target_data = np.array([0, 1, 0, 1])
        model = Mock()
        model.predict = Mock(return_value=np.array([0, 0, 1, 0]))
        scores, _ = gen_model.score_model(model, input_data, target_data)
        self.assertAlmostEqual(scores.accuracy, 0.25)
        self.assertEqual(scores.precision, 0)
        self.assertAlmostEqual(scores.hmean_precision, 0)
        self.assertAlmostEqual(scores.hmean_recall, 0)
        self.assertAlmostEqual(scores.sensitivity, 0)
        self.assertAlmostEqual(scores.specificity, 0.5)
        self.assertAlmostEqual(scores.informedness, -0.5)

    def test_100_percent_ternary_classification(self):
        """
        Test score_model() with 100% correct ternary classification.

        """

        input_data = np.array([])
        target_data = np.array([0, 1, 2, 0, 1, 2])
        model = Mock()
        model.predict = Mock(return_value=target_data)
        scores, _ = gen_model.score_model(model, input_data, target_data)
        self.assertEqual(scores.accuracy, 1.0)
        self.assertEqual(scores.hmean_precision, 1.0)
        self.assertEqual(scores.hmean_recall, 1.0)
        self.assertEqual(scores.informedness, 1.0)

    def test_50_percent_ternary_classification(self):
        """
        Test score_model() with 50% correct ternary classification.

        """

        input_data = np.array([])
        target_data = np.array([0, 1, 2, 0, 1, 2])
        model = Mock()
        model.predict = Mock(return_value=np.array([0, 1, 2, 2, 0, 1]))
        scores, _ = gen_model.score_model(model, input_data, target_data)
        self.assertAlmostEqual(scores.accuracy, 0.5)
        self.assertAlmostEqual(scores.hmean_precision, 0.5)
        self.assertAlmostEqual(scores.hmean_recall, 0.5)
        self.assertAlmostEqual(scores.informedness, 0)

    def test_random_ternary_classifications(self):
        """
        Test score_model() with random ternary classifications.

        """

        input_data = np.array([])
        target_data = np.array([0, 1, 2, 0, 1, 2])
        model = Mock()
        model.predict = Mock(return_value=np.array([1, 1, 1, 2, 2, 0]))
        scores, _ = gen_model.score_model(model, input_data, target_data)
        self.assertAlmostEqual(scores.accuracy, 0.1666667)
        self.assertAlmostEqual(scores.hmean_precision, 0)
        self.assertAlmostEqual(scores.hmean_recall, 0)
        self.assertAlmostEqual(scores.informedness, -0.6666667)


class BindModelMetadataTests(unittest.TestCase):
    """
    Tests for gen_model.bind_model_metadata

    """

    def test_bind_model_metadata(self):
        """
        Test bind_model_metadata() on typical inputs.

        """

        scores = gen_model.ModelScores(1., 2., 3., 4., 5., 6., 7.)
        attributes = ('commit_hash', 'validated', 'reposistory', 'numpy_version',
                      'scipy_version', 'pandas_version', 'sklearn_version',
                      'joblib_version', 'threadpoolctl_version', 'operating_system',
                      'architecture', 'created', 'author')

        attributes += tuple(scores._asdict().keys())
        model = Mock()
        gen_model.bind_model_metadata(model, scores)
        for attribute in attributes:
            self.assertTrue(hasattr(model, attribute))


if __name__ == '__main__':
    unittest.main()