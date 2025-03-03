import math
from dataclasses import dataclass
from typing import List

from scipy import stats


@dataclass
class CorrelationScore:
    measured_score: float
    human_score: float
    normalized_measured_score: float
    normalized_human_score: float


@dataclass
class CorrelationResult:
    mean_absolute_error: float
    mean_normalized_absolute_error: float
    mean_squared_error: float
    mean_normalized_squared_error: float
    spearman_correlation: float | None
    pearson_correlation: float | None
    kendalltau_correlation: float | None


class CorrelationCalculator:
    def __init__(self):
        self.scores: List[CorrelationScore] = []

    def add_score(self, score: CorrelationScore):
        self.scores.append(score)

    def calculate_correlation(self) -> CorrelationResult:
        if len(self.scores) == 0:
            raise ValueError("No scores to calculate correlation")

        return CorrelationResult(
            mean_absolute_error=self.calculate_mean_absolute_error(),
            mean_normalized_absolute_error=self.calculate_mean_normalized_absolute_error(),
            mean_squared_error=self.calculate_mean_squared_error(),
            mean_normalized_squared_error=self.calculate_mean_normalized_squared_error(),
            spearman_correlation=self.calculate_spearman_correlation(),
            pearson_correlation=self.calculate_pearson_correlation(),
            kendalltau_correlation=self.calculate_kendalltau_correlation(),
        )

    def calculate_mean_absolute_error(self) -> float:
        total_absolute_error = sum(
            abs(score.measured_score - score.human_score) for score in self.scores
        )
        return total_absolute_error / len(self.scores)

    def calculate_mean_normalized_absolute_error(self) -> float:
        total_normalized_absolute_error = sum(
            abs(score.normalized_measured_score - score.normalized_human_score)
            for score in self.scores
        )
        return total_normalized_absolute_error / len(self.scores)

    def calculate_mean_squared_error(self) -> float:
        total_squared_error = sum(
            (score.measured_score - score.human_score) ** 2 for score in self.scores
        )
        return total_squared_error / len(self.scores)

    def calculate_mean_normalized_squared_error(self) -> float:
        total_normalized_squared_error = sum(
            (score.normalized_measured_score - score.normalized_human_score) ** 2
            for score in self.scores
        )
        return total_normalized_squared_error / len(self.scores)

    def calculate_spearman_correlation(self) -> float | None:
        if len(self.scores) < 2:
            # If there is only one pair, no correlation
            return None
        x = [score.measured_score for score in self.scores]
        y = [score.human_score for score in self.scores]
        result = stats.spearmanr(x, y)
        # library doesn't support proper types
        correlation = result.__getattribute__("correlation")
        if math.isnan(correlation) or not isinstance(correlation, float):
            # Very small samples may have a NaN result (unknown correlation)
            return None
        return correlation

    def calculate_pearson_correlation(self) -> float | None:
        if len(self.scores) < 2:
            # If there is only one pair,  no correlation
            return None
        x = [score.measured_score for score in self.scores]
        y = [score.human_score for score in self.scores]
        result = stats.pearsonr(x, y)
        if math.isnan(result.correlation):
            # Very small samples may have a NaN result (unknown correlation)
            return None
        return result.correlation

    def calculate_kendalltau_correlation(self) -> float | None:
        if len(self.scores) < 2:
            # If there is only one pair, no correlation
            return None
        x = [score.measured_score for score in self.scores]
        y = [score.human_score for score in self.scores]
        result = stats.kendalltau(x, y)
        if math.isnan(result.correlation):
            # Very small samples may have a NaN result (unknown correlation)
            return None
        return result.correlation
