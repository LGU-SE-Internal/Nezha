"""
Evaluation methods for assessing pattern mining and ranking performance.
This module provides generic evaluation metrics independent of specific datasets.
"""

import json
from typing import List, Dict, Tuple, Optional, Any, Callable
from pathlib import Path
from loguru import logger

from ..common.types import RankedPattern, GroundTruth, FaultInjection, EvaluationMetrics


class Evaluator:
    """Generic evaluation methods for pattern analysis."""

    def __init__(self):
        """Initialize evaluator."""
        pass

    def evaluate_ranking_performance(
        self,
        ranked_patterns: List[RankedPattern],
        ground_truth: List[GroundTruth],
        match_function: Optional[Callable] = None,
        top_k_values: Optional[List[int]] = None,
    ) -> EvaluationMetrics:
        """
        Evaluate ranking performance using Hit@K and MAR metrics.

        Args:
            ranked_patterns: List of ranked patterns
            ground_truth: List of ground truth fault injections
            match_function: Custom function to match patterns with ground truth
            top_k_values: List of K values for Hit@K evaluation

        Returns:
            EvaluationMetrics containing evaluation results
        """
        if top_k_values is None:
            top_k_values = [1, 3, 5]

        if match_function is None:
            match_function = self._default_pattern_match

        logger.info(
            f"Evaluating {len(ranked_patterns)} patterns against {len(ground_truth)} ground truths"
        )

        hit_counts = {k: 0 for k in top_k_values}
        total_rank = 0
        successful_matches = 0

        for gt in ground_truth:
            rank = self._find_pattern_rank(ranked_patterns, gt, match_function)

            if rank > 0:  # Found a match
                successful_matches += 1
                total_rank += rank

                # Update Hit@K counts
                for k in top_k_values:
                    if rank <= k:
                        hit_counts[k] += 1

        # Calculate metrics
        total_faults = len(ground_truth)
        hit_at_k = {}
        for k in top_k_values:
            hit_at_k[f"hit_at_{k}"] = (
                hit_counts[k] / total_faults if total_faults > 0 else 0.0
            )

        mar = (
            total_rank / successful_matches if successful_matches > 0 else float("inf")
        )

        # Create metrics object (assuming we have a namespace)
        metrics = EvaluationMetrics(
            hit_at_1=hit_at_k.get("hit_at_1", 0.0),
            hit_at_3=hit_at_k.get("hit_at_3", 0.0),
            hit_at_5=hit_at_k.get("hit_at_5", 0.0),
            mean_average_rank=mar,
            total_faults=total_faults,
            namespace="unknown",  # Should be set by caller
        )

        logger.info(
            f"Evaluation complete: Hit@1={metrics.hit_at_1:.3f}, "
            f"Hit@3={metrics.hit_at_3:.3f}, Hit@5={metrics.hit_at_5:.3f}, "
            f"MAR={metrics.mean_average_rank:.3f}"
        )

        return metrics

    def evaluate_service_level_performance(
        self,
        ranked_patterns: List[RankedPattern],
        ground_truth: List[GroundTruth],
        pod_match_function: Optional[Callable] = None,
    ) -> EvaluationMetrics:
        """
        Evaluate performance at service/pod level.

        Args:
            ranked_patterns: List of ranked patterns
            ground_truth: List of ground truth data
            pod_match_function: Function to match patterns by pod

        Returns:
            EvaluationMetrics for service-level evaluation
        """
        if pod_match_function is None:
            pod_match_function = self._default_pod_match

        return self.evaluate_ranking_performance(
            ranked_patterns, ground_truth, pod_match_function
        )

    def evaluate_with_score_thresholds(
        self,
        ranked_patterns: List[RankedPattern],
        ground_truth: List[GroundTruth],
        score_thresholds: List[float],
        match_function: Optional[Callable] = None,
    ) -> Dict[float, EvaluationMetrics]:
        """
        Evaluate performance across different score thresholds.

        Args:
            ranked_patterns: List of ranked patterns
            ground_truth: List of ground truth data
            score_thresholds: List of score thresholds to evaluate
            match_function: Function to match patterns with ground truth

        Returns:
            Dictionary mapping thresholds to evaluation metrics
        """
        results = {}

        for threshold in score_thresholds:
            # Filter patterns by score threshold
            filtered_patterns = [p for p in ranked_patterns if p.score >= threshold]

            logger.info(
                f"Evaluating with score threshold {threshold}: "
                f"{len(filtered_patterns)} patterns"
            )

            metrics = self.evaluate_ranking_performance(
                filtered_patterns, ground_truth, match_function
            )
            results[threshold] = metrics

        return results

    def _find_pattern_rank(
        self,
        ranked_patterns: List[RankedPattern],
        ground_truth: GroundTruth,
        match_function: Callable,
    ) -> int:
        """
        Find the rank of the first matching pattern for given ground truth.

        Args:
            ranked_patterns: List of ranked patterns
            ground_truth: Ground truth to match against
            match_function: Function to determine if pattern matches ground truth

        Returns:
            Rank of first matching pattern (1-indexed), or 0 if no match
        """
        for rank, pattern in enumerate(ranked_patterns, 1):
            if match_function(pattern, ground_truth):
                return rank

        return 0  # No match found

    def _default_pattern_match(
        self, pattern: RankedPattern, ground_truth: GroundTruth
    ) -> bool:
        """
        Default pattern matching function.

        Args:
            pattern: Ranked pattern to check
            ground_truth: Ground truth to match against

        Returns:
            True if pattern matches ground truth
        """
        # Match by pattern key if available
        if hasattr(ground_truth, "root_cause_pattern"):
            return pattern.pattern.pattern_key == ground_truth.root_cause_pattern

        # Match by pod if available
        if hasattr(ground_truth, "fault_injection"):
            injection = ground_truth.fault_injection
            return pattern.pod == injection.inject_pod

        return False

    def _default_pod_match(
        self, pattern: RankedPattern, ground_truth: GroundTruth
    ) -> bool:
        """
        Default pod-level matching function.

        Args:
            pattern: Ranked pattern to check
            ground_truth: Ground truth to match against

        Returns:
            True if pattern pod matches ground truth pod
        """
        if hasattr(ground_truth, "fault_injection"):
            injection = ground_truth.fault_injection
            return pattern.pod == injection.inject_pod

        return False

    def calculate_precision_recall(
        self, predicted_patterns: List[str], true_patterns: List[str]
    ) -> Tuple[float, float, float]:
        """
        Calculate precision, recall, and F1-score for pattern sets.

        Args:
            predicted_patterns: List of predicted pattern keys
            true_patterns: List of true pattern keys

        Returns:
            Tuple of (precision, recall, f1_score)
        """
        predicted_set = set(predicted_patterns)
        true_set = set(true_patterns)

        if len(predicted_set) == 0:
            precision = 0.0
        else:
            precision = len(predicted_set & true_set) / len(predicted_set)

        if len(true_set) == 0:
            recall = 0.0
        else:
            recall = len(predicted_set & true_set) / len(true_set)

        if precision + recall == 0:
            f1_score = 0.0
        else:
            f1_score = 2 * (precision * recall) / (precision + recall)

        return precision, recall, f1_score

    def load_ground_truth_from_file(
        self, file_path: str, parser_function: Optional[Callable] = None
    ) -> List[GroundTruth]:
        """
        Load ground truth data from file.

        Args:
            file_path: Path to ground truth file
            parser_function: Custom function to parse file content

        Returns:
            List of GroundTruth objects
        """
        if parser_function is None:
            parser_function = self._default_ground_truth_parser

        try:
            with open(file_path, "r") as f:
                data = json.load(f)

            ground_truth_list = parser_function(data)
            logger.info(
                f"Loaded {len(ground_truth_list)} ground truth entries from {file_path}"
            )
            return ground_truth_list

        except Exception as e:
            logger.error(f"Error loading ground truth from {file_path}: {e}")
            return []

    def _default_ground_truth_parser(self, data: Any) -> List[GroundTruth]:
        """
        Default parser for ground truth JSON data.

        Args:
            data: JSON data from file

        Returns:
            List of GroundTruth objects
        """
        ground_truth_list = []

        try:
            # Handle nested structure: hour -> fault list
            if isinstance(data, dict):
                for hour, faults in data.items():
                    if isinstance(faults, list):
                        for fault in faults:
                            gt = self._parse_fault_to_ground_truth(fault)
                            if gt:
                                ground_truth_list.append(gt)

            # Handle flat list structure
            elif isinstance(data, list):
                for fault in data:
                    gt = self._parse_fault_to_ground_truth(fault)
                    if gt:
                        ground_truth_list.append(gt)

        except Exception as e:
            logger.error(f"Error parsing ground truth data: {e}")

        return ground_truth_list

    def _parse_fault_to_ground_truth(self, fault_data: Dict) -> Optional[GroundTruth]:
        """Parse individual fault data to GroundTruth object."""
        try:
            injection = FaultInjection(
                inject_time=fault_data.get("inject_time", ""),
                inject_pod=fault_data.get("inject_pod", ""),
                inject_service=fault_data.get("inject_service", ""),
                inject_type=fault_data.get("inject_type", ""),
                severity=fault_data.get("severity", 1.0),
                duration=fault_data.get("duration"),
            )

            ground_truth = GroundTruth(
                fault_injection=injection,
                root_cause_pattern=fault_data.get("root_cause", ""),
                affected_services=fault_data.get("affected_services", []),
            )

            return ground_truth

        except Exception as e:
            logger.warning(f"Error parsing fault data: {e}")
            return None

    def export_evaluation_results(
        self,
        metrics: EvaluationMetrics,
        output_file: str,
        additional_data: Optional[Dict] = None,
    ) -> None:
        """
        Export evaluation results to file.

        Args:
            metrics: Evaluation metrics to export
            output_file: Output file path
            additional_data: Additional data to include in export
        """
        try:
            results = {
                "hit_at_1": metrics.hit_at_1,
                "hit_at_3": metrics.hit_at_3,
                "hit_at_5": metrics.hit_at_5,
                "mean_average_rank": metrics.mean_average_rank,
                "total_faults": metrics.total_faults,
                "namespace": metrics.namespace,
            }

            if additional_data:
                results.update(additional_data)

            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w") as f:
                json.dump(results, f, indent=2)

            logger.info(f"Exported evaluation results to {output_file}")

        except Exception as e:
            logger.error(f"Error exporting results to {output_file}: {e}")
