import pytest

from app.desktop.studio_server.correlation_calculator import (
    CorrelationCalculator,
    CorrelationScore,
)


class TestCorrelationCalculator:
    def create_correlation_scores(self, measured, human):
        """Helper method to create correlation scores from raw data with normalization"""
        scores = []

        # Calculate normalized values
        min_m, max_m = min(measured), max(measured)
        min_h, max_h = min(human), max(human)

        for m, h in zip(measured, human):
            norm_m = (m - min_m) / (max_m - min_m) if max_m != min_m else 0
            norm_h = (h - min_h) / (max_h - min_h) if max_h != min_h else 0
            scores.append(
                CorrelationScore(
                    measured_score=m,
                    human_score=h,
                    normalized_measured_score=norm_m,
                    normalized_human_score=norm_h,
                )
            )
        return scores

    @pytest.fixture
    def perfect_correlation_data(self):
        """Dataset with perfect correlation (r=1.0)"""
        measured = list(range(10))
        human = list(range(10))
        return self.create_correlation_scores(measured, human)

    @pytest.fixture
    def high_correlation_data(self):
        """Dataset with high correlation (r≈0.9)"""
        measured = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        human = [1.1, 2.2, 2.9, 3.8, 5.2, 5.8, 7.1, 8.3, 8.7, 10.2]
        return self.create_correlation_scores(measured, human)

    @pytest.fixture
    def no_correlation_data(self):
        """Dataset with no correlation"""
        measured = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        human = [5.5, 6.2, 4.8, 7.3, 2.1, 8.9, 3.7, 5.4, 6.8, 4.2]
        return self.create_correlation_scores(measured, human)

    @pytest.fixture
    def inverse_correlation_data(self):
        """Dataset with inverse correlation (r≈-0.9)"""
        measured = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        human = [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
        return self.create_correlation_scores(measured, human)

    @pytest.fixture
    def single_data_point(self):
        """Dataset with only one data point"""
        return [
            CorrelationScore(
                measured_score=5,
                human_score=5,
                normalized_measured_score=0.5,
                normalized_human_score=0.5,
            )
        ]

    @pytest.fixture
    def two_data_points(self):
        """Dataset with only two data points"""
        measured = [1, 10]
        human = [2, 9]
        return self.create_correlation_scores(measured, human)

    def setup_calculator_with_data(self, data):
        """Helper method to create and populate a calculator with data"""
        calculator = CorrelationCalculator()
        for score in data:
            calculator.add_score(score)
        return calculator

    def test_add_score(self):
        """Test adding scores to the calculator"""
        calculator = CorrelationCalculator()
        score = CorrelationScore(
            measured_score=5,
            human_score=6,
            normalized_measured_score=0.5,
            normalized_human_score=0.6,
        )

        calculator.add_score(score)
        assert len(calculator.scores) == 1
        assert calculator.scores[0] == score

    def test_empty_calculator(self):
        """Test that calculating correlation with no scores raises an error"""
        calculator = CorrelationCalculator()

        with pytest.raises(ValueError, match="No scores to calculate correlation"):
            calculator.calculate_correlation()

    def test_perfect_correlation(self, perfect_correlation_data):
        """Test correlation calculations with perfectly correlated data"""
        calculator = CorrelationCalculator()
        for score in perfect_correlation_data:
            calculator.add_score(score)

        result = calculator.calculate_correlation()

        # Perfect correlation should have:
        # - MAE and MSE of 0 (no error)
        # - Correlation coefficients of 1.0
        assert result.mean_absolute_error == 0.0
        assert result.mean_normalized_absolute_error == 0.0
        assert result.mean_squared_error == 0.0
        assert result.mean_normalized_squared_error == 0.0
        assert result.spearman_correlation == pytest.approx(1.0)
        assert result.pearson_correlation == pytest.approx(1.0)
        assert result.kendalltau_correlation == pytest.approx(1.0)

    def test_high_correlation(self, high_correlation_data):
        """Test correlation calculations with highly correlated data"""
        calculator = CorrelationCalculator()
        for score in high_correlation_data:
            calculator.add_score(score)

        result = calculator.calculate_correlation()

        # High correlation should have:
        # - Low but non-zero error metrics
        # - Correlation coefficients close to 1.0
        assert 0 < result.mean_absolute_error < 1.0
        assert 0 < result.mean_normalized_absolute_error < 0.2
        assert 0 < result.mean_squared_error < 1.0
        assert 0 < result.mean_normalized_squared_error < 0.1
        assert result.spearman_correlation > 0.9
        assert result.pearson_correlation > 0.9
        assert result.kendalltau_correlation > 0.8

    def test_no_correlation(self, no_correlation_data):
        """Test correlation calculations with uncorrelated data"""
        calculator = CorrelationCalculator()
        for score in no_correlation_data:
            calculator.add_score(score)

        result = calculator.calculate_correlation()

        # No correlation should have:
        # - Higher error metrics
        # - Correlation coefficients close to 0
        assert result.mean_absolute_error > 1.0
        assert result.mean_normalized_absolute_error > 0.2
        assert result.mean_squared_error > 2.0
        assert result.mean_normalized_squared_error > 0.1
        assert -0.3 < result.spearman_correlation < 0.3
        assert -0.3 < result.pearson_correlation < 0.3
        assert -0.3 < result.kendalltau_correlation < 0.3

    def test_inverse_correlation(self, inverse_correlation_data):
        """Test correlation calculations with inversely correlated data"""
        calculator = CorrelationCalculator()
        for score in inverse_correlation_data:
            calculator.add_score(score)

        result = calculator.calculate_correlation()

        # Inverse correlation should have:
        # - Higher error metrics
        # - Correlation coefficients close to -1.0
        assert result.mean_absolute_error > 4.0
        assert result.mean_normalized_absolute_error > 0.5
        assert result.mean_squared_error > 20.0
        assert result.mean_normalized_squared_error > 0.3
        assert result.spearman_correlation < -0.9
        assert result.pearson_correlation < -0.9
        assert result.kendalltau_correlation < -0.9

    def test_single_data_point(self, single_data_point):
        """Test correlation calculations with a single data point"""
        calculator = CorrelationCalculator()
        for score in single_data_point:
            calculator.add_score(score)

        result = calculator.calculate_correlation()

        # Single data point should have:
        # - Zero error (since the point matches itself)
        # - Correlation coefficients of 0 (as defined in the implementation)
        assert result.mean_absolute_error == 0.0
        assert result.mean_normalized_absolute_error == 0.0
        assert result.mean_squared_error == 0.0
        assert result.mean_normalized_squared_error == 0.0
        assert result.spearman_correlation is None
        assert result.pearson_correlation is None
        assert result.kendalltau_correlation is None

    def test_two_data_points(self, two_data_points):
        """Test correlation calculations with two data points"""
        calculator = CorrelationCalculator()
        for score in two_data_points:
            calculator.add_score(score)

        result = calculator.calculate_correlation()

        # Two data points with positive correlation should have:
        # - Some error
        # - Positive correlation coefficients
        assert result.mean_absolute_error == 1.0
        assert result.mean_normalized_absolute_error == 0.0
        assert result.mean_squared_error == 1.0
        assert result.mean_normalized_squared_error == 0.0
        assert result.spearman_correlation == pytest.approx(1.0)
        assert result.pearson_correlation == pytest.approx(1.0)
        assert result.kendalltau_correlation == pytest.approx(1.0)

    def test_individual_calculation_methods(self, high_correlation_data):
        """Test that individual calculation methods match the combined result"""
        calculator = CorrelationCalculator()
        for score in high_correlation_data:
            calculator.add_score(score)

        # Calculate individual metrics
        mae = calculator.calculate_mean_absolute_error()
        # Our spell checker thinks n-m-a-e is a misspelling of name :)
        n_mae = calculator.calculate_mean_normalized_absolute_error()
        mse = calculator.calculate_mean_squared_error()
        nmse = calculator.calculate_mean_normalized_squared_error()
        spearman = calculator.calculate_spearman_correlation()
        pearson = calculator.calculate_pearson_correlation()
        kendall = calculator.calculate_kendalltau_correlation()

        # Calculate combined result
        result = calculator.calculate_correlation()

        # Verify they match
        assert result.mean_absolute_error == mae
        assert result.mean_normalized_absolute_error == n_mae
        assert result.mean_squared_error == mse
        assert result.mean_normalized_squared_error == nmse
        assert result.spearman_correlation == spearman
        assert result.pearson_correlation == pearson
        assert result.kendalltau_correlation == kendall

    def test_constant_arrays(self):
        """Test that constant arrays (no variation) return None for correlation coefficients"""
        # Create data where one array is constant
        constant_data = [
            CorrelationScore(
                measured_score=1.0,
                human_score=5.0,
                normalized_measured_score=0.0,
                normalized_human_score=1.0,
            ),
            CorrelationScore(
                measured_score=2.0,
                human_score=5.0,  # Constant human scores
                normalized_measured_score=0.5,
                normalized_human_score=1.0,
            ),
            CorrelationScore(
                measured_score=3.0,
                human_score=5.0,  # Constant human scores
                normalized_measured_score=1.0,
                normalized_human_score=1.0,
            ),
        ]

        calculator = CorrelationCalculator()
        for score in constant_data:
            calculator.add_score(score)

        result = calculator.calculate_correlation()

        # Error metrics should still be calculated
        assert result.mean_absolute_error > 0
        assert result.mean_normalized_absolute_error > 0
        assert result.mean_squared_error > 0
        assert result.mean_normalized_squared_error > 0

        # Correlation coefficients should be None due to constant array
        assert result.spearman_correlation is None
        assert result.pearson_correlation is None
        assert result.kendalltau_correlation is None

    def test_both_constant_arrays(self):
        """Test that both constant arrays return None for correlation coefficients"""
        # Create data where both arrays are constant
        both_constant_data = [
            CorrelationScore(
                measured_score=5.0,  # Constant measured scores
                human_score=5.0,  # Constant human scores
                normalized_measured_score=0.5,
                normalized_human_score=0.5,
            ),
            CorrelationScore(
                measured_score=5.0,  # Constant measured scores
                human_score=5.0,  # Constant human scores
                normalized_measured_score=0.5,
                normalized_human_score=0.5,
            ),
        ]

        calculator = CorrelationCalculator()
        for score in both_constant_data:
            calculator.add_score(score)

        result = calculator.calculate_correlation()

        # Error metrics should be 0 since all values are the same
        assert result.mean_absolute_error == 0.0
        assert result.mean_normalized_absolute_error == 0.0
        assert result.mean_squared_error == 0.0
        assert result.mean_normalized_squared_error == 0.0

        # Correlation coefficients should be None due to constant arrays
        assert result.spearman_correlation is None
        assert result.pearson_correlation is None
        assert result.kendalltau_correlation is None
