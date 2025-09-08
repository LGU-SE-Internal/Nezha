"""
Nezha Algorithm - Root cause analysis using enhanced event patterns.

Implements the core Nezha algorithm for comparing normal and abnormal patterns.
"""

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from rcabench_platform.v2.logging import logger

from .data_structures import PatternSupport, TraceData


@dataclass
class PatternScore:
    """
    Scoring information for a pattern.

    Attributes:
        pattern: The event pattern tuple
        abnormal_support: Support in abnormal traces
        normal_support: Support in normal traces
        score: Calculated suspiciousness score
        depth: Average depth of the pattern
        services: Set of services involved
        rank: Ranking position
    """

    pattern: Tuple[int, int]
    abnormal_support: int
    normal_support: int
    score: float
    depth: float
    services: Set[str]
    rank: int = 0


@dataclass
class RCAResult:
    """
    Root cause analysis result.

    Attributes:
        ranked_patterns: List of patterns ranked by suspiciousness
        total_abnormal_patterns: Total patterns in abnormal traces
        total_normal_patterns: Total patterns in normal traces
        processing_time_seconds: Time taken for analysis
        top_k_accuracy: Accuracy metrics for different k values
    """

    ranked_patterns: List[PatternScore]
    total_abnormal_patterns: int
    total_normal_patterns: int
    processing_time_seconds: float
    top_k_accuracy: Optional[Dict[int, float]] = None


class NezhaAlgorithm:
    """
    Core Nezha algorithm for root cause analysis.

    Compares event patterns between normal and abnormal traces to identify
    suspicious patterns that could indicate root causes.
    """

    def __init__(self):
        """
        Initialize algorithm.
        """
        pass

    def calculate_pattern_support(
        self, trace_data_list: List[TraceData]
    ) -> PatternSupport:
        """
        Calculate pattern support from trace data.

        Args:
            trace_data_list: List of processed trace data

        Returns:
            PatternSupport object with aggregated patterns
        """
        support = PatternSupport()

        for trace_data in trace_data_list:
            for pattern in trace_data.enhanced_patterns:
                support.add_pattern(pattern)

        return support

    def calculate_suspiciousness_score(
        self, abnormal_support: int, normal_support: int, min_support: int = 5
    ) -> float:
        """
        Calculate suspiciousness score for a pattern.

        Uses the formula: abnormal_support / (abnormal_support + normal_support)
        Patterns with low normal support and high abnormal support get higher scores.

        Args:
            abnormal_support: Number of occurrences in abnormal traces
            normal_support: Number of occurrences in normal traces
            min_support: Minimum support required for consideration

        Returns:
            Suspiciousness score between 0 and 1
        """
        if abnormal_support < min_support:
            return 0.0

        total_support = abnormal_support + normal_support
        if total_support == 0:
            return 0.0

        return abnormal_support / total_support

    def rank_patterns(
        self,
        normal_support: PatternSupport,
        abnormal_support: PatternSupport,
        min_support: int = 5,
        min_score: float = 0.67,
    ) -> List[PatternScore]:
        """
        Rank patterns by suspiciousness score.

        Args:
            normal_support: Pattern support from normal traces
            abnormal_support: Pattern support from abnormal traces
            min_support: Minimum support threshold
            min_score: Minimum suspiciousness score threshold

        Returns:
            List of ranked pattern scores
        """
        scored_patterns = []

        # Get all patterns that appear in abnormal traces
        abnormal_patterns = set(abnormal_support.pattern_counts.keys())

        for pattern in abnormal_patterns:
            abnormal_count = abnormal_support.pattern_counts.get(pattern, 0)
            normal_count = normal_support.pattern_counts.get(pattern, 0)

            # Calculate suspiciousness score
            score = self.calculate_suspiciousness_score(
                abnormal_count, normal_count, min_support
            )

            # Filter by minimum score and support
            if score >= min_score and abnormal_count >= min_support:
                # Get pattern metadata
                abnormal_info = abnormal_support.get_pattern_info(pattern)
                avg_depth = abnormal_info["avg_depth"]
                services = set(abnormal_info["services"])

                pattern_score = PatternScore(
                    pattern=pattern,
                    abnormal_support=abnormal_count,
                    normal_support=normal_count,
                    score=score,
                    depth=avg_depth,
                    services=services,
                )
                scored_patterns.append(pattern_score)

        # Sort by score (descending) and then by abnormal support (descending)
        scored_patterns.sort(key=lambda x: (x.score, x.abnormal_support), reverse=True)

        # Assign ranks
        for i, pattern_score in enumerate(scored_patterns):
            pattern_score.rank = i + 1

        return scored_patterns

    def analyze_root_causes(
        self,
        normal_traces: List[TraceData],
        abnormal_traces: List[TraceData],
        min_support: int = 5,
        min_score: float = 0.67,
        top_k: int = 10,
    ) -> RCAResult:
        """
        Perform root cause analysis.

        Args:
            normal_traces: List of normal trace data
            abnormal_traces: List of abnormal trace data
            min_support: Minimum pattern support threshold
            min_score: Minimum suspiciousness score threshold
            top_k: Number of top patterns to return

        Returns:
            RCA result with ranked suspicious patterns
        """
        start_time = time.time()

        logger.info("Starting root cause analysis...")
        logger.info(f"Normal traces: {len(normal_traces)}")
        logger.info(f"Abnormal traces: {len(abnormal_traces)}")

        # Calculate pattern support for normal and abnormal traces
        logger.info("Calculating pattern support...")
        normal_support = self.calculate_pattern_support(normal_traces)
        abnormal_support = self.calculate_pattern_support(abnormal_traces)

        logger.info(f"Normal patterns: {len(normal_support.pattern_counts)}")
        logger.info(f"Abnormal patterns: {len(abnormal_support.pattern_counts)}")

        # Rank patterns by suspiciousness
        logger.info("Ranking patterns by suspiciousness...")
        ranked_patterns = self.rank_patterns(
            normal_support, abnormal_support, min_support, min_score
        )

        # Limit to top-k
        top_ranked_patterns = ranked_patterns[:top_k]

        processing_time = time.time() - start_time

        logger.info(f"Found {len(ranked_patterns)} suspicious patterns")
        logger.info(f"Top-{top_k} patterns selected")
        logger.info(f"Analysis completed in {processing_time:.2f}s")

        # Log top patterns
        for i, pattern_score in enumerate(top_ranked_patterns[:5]):
            logger.info(
                f"Rank {i + 1}: Pattern {pattern_score.pattern} "
                f"Score={pattern_score.score:.3f} "
                f"Abnormal={pattern_score.abnormal_support} "
                f"Normal={pattern_score.normal_support}"
            )

        return RCAResult(
            ranked_patterns=top_ranked_patterns,
            total_abnormal_patterns=len(abnormal_support.pattern_counts),
            total_normal_patterns=len(normal_support.pattern_counts),
            processing_time_seconds=processing_time,
        )

    def evaluate_accuracy(
        self,
        rca_result: RCAResult,
        ground_truth: Set[Tuple[int, int]],
        k_values: List[int] = [1, 3, 5, 10],
    ) -> Dict[int, float]:
        """
        Evaluate accuracy of root cause analysis.

        Args:
            rca_result: Result from root cause analysis
            ground_truth: Set of ground truth patterns
            k_values: List of k values for top-k accuracy

        Returns:
            Dictionary mapping k to accuracy percentage
        """
        if not ground_truth:
            logger.warning("No ground truth provided for evaluation")
            return {k: 0.0 for k in k_values}

        accuracy_results = {}

        for k in k_values:
            if k > len(rca_result.ranked_patterns):
                accuracy_results[k] = accuracy_results.get(k - 1, 0.0)
                continue

            # Get top-k patterns
            top_k_patterns = set(
                pattern.pattern for pattern in rca_result.ranked_patterns[:k]
            )

            # Calculate accuracy as percentage of ground truth found
            correct_predictions = len(top_k_patterns & ground_truth)
            accuracy = (correct_predictions / len(ground_truth)) * 100.0
            accuracy_results[k] = accuracy

        # Log accuracy results
        for k, accuracy in accuracy_results.items():
            logger.info(f"Top-{k} accuracy: {accuracy:.2f}%")

        return accuracy_results

    def explain_pattern(
        self, pattern: Tuple[int, int], event_manager
    ) -> Dict[str, str]:
        """
        Provide human-readable explanation of a pattern.

        Args:
            pattern: Event pattern tuple (source_id, target_id)
            event_manager: Event ID manager for decoding

        Returns:
            Dictionary with pattern explanation
        """
        source_id, target_id = pattern

        # Decode event IDs to human-readable descriptions
        # This is a simplified version - in practice you'd need the full event manager
        explanation = {
            "pattern": f"{source_id} -> {target_id}",
            "description": f"Event transition from {source_id} to {target_id}",
            "type": "unknown",
        }

        # Add more sophisticated decoding based on event ID ranges
        if 1 <= source_id <= 5000:
            explanation["source_type"] = "span_start"
        elif 5001 <= source_id <= 10000:
            explanation["source_type"] = "span_end"
        elif source_id >= 20001:
            explanation["source_type"] = "log_template"
        else:
            explanation["source_type"] = "special_event"

        if 1 <= target_id <= 5000:
            explanation["target_type"] = "span_start"
        elif 5001 <= target_id <= 10000:
            explanation["target_type"] = "span_end"
        elif target_id >= 20001:
            explanation["target_type"] = "log_template"
        else:
            explanation["target_type"] = "special_event"

        return explanation


def run_nezha_analysis(
    normal_traces: List[TraceData],
    abnormal_traces: List[TraceData],
    ground_truth: Optional[Set[Tuple[int, int]]] = None,
    min_support: int = 5,
    min_score: float = 0.67,
    top_k: int = 10,
) -> RCAResult:
    """
    Convenience function to run complete Nezha analysis.

    Args:
        normal_traces: List of normal trace data
        abnormal_traces: List of abnormal trace data
        ground_truth: Optional ground truth for evaluation
        min_support: Minimum pattern support threshold
        min_score: Minimum suspiciousness score threshold
        top_k: Number of top patterns to return

    Returns:
        RCA result with ranked suspicious patterns
    """
    # Initialize algorithm
    algorithm = NezhaAlgorithm()

    # Perform analysis
    result = algorithm.analyze_root_causes(
        normal_traces, abnormal_traces, min_support, min_score, top_k
    )

    # Evaluate accuracy if ground truth provided
    if ground_truth:
        accuracy = algorithm.evaluate_accuracy(result, ground_truth)
        result.top_k_accuracy = accuracy

    return result
