"""
Pattern ranking methods for scoring and ranking patterns based on anomaly detection.
This module provides generic ranking algorithms independent of specific data sources.
"""

from typing import List, Dict, Set, Optional, Callable
from loguru import logger

from ..common.types import Pattern, RankedPattern, EventGraph, AlarmEvent, PatternDict


class PatternRanker:
    """Generic pattern ranking algorithms."""

    def __init__(
        self,
        min_score: float = 0.67,
        min_support: int = 5,
        score_metric: str = "anomaly_ratio",
    ):
        """
        Initialize pattern ranker.

        Args:
            min_score: Minimum score threshold for patterns
            min_support: Minimum support threshold for patterns
            score_metric: Scoring metric to use ("anomaly_ratio", "lift", "confidence")
        """
        self.min_score = min_score
        self.min_support = min_support
        self.score_metric = score_metric

    def rank_patterns(
        self,
        normal_patterns: PatternDict,
        abnormal_patterns: PatternDict,
        event_graphs: List[EventGraph],
        alarms: List[AlarmEvent],
        template_resolver: Optional[Callable[[int], str]] = None,
        depth_calculator: Optional[Callable[[List[EventGraph], str], tuple]] = None,
        alarm_associator: Optional[
            Callable[[str, str, List[AlarmEvent]], tuple]
        ] = None,
    ) -> List[RankedPattern]:
        """
        Rank patterns by comparing normal and abnormal frequencies.

        Args:
            normal_patterns: Pattern support in normal periods
            abnormal_patterns: Pattern support in abnormal periods
            event_graphs: Event graphs for depth calculation
            alarms: List of alarms for association
            template_resolver: Function to resolve event_id -> template
            depth_calculator: Function to calculate pattern depth and pod
            alarm_associator: Function to associate patterns with alarms

        Returns:
            List of ranked patterns
        """
        logger.info("Ranking patterns based on anomaly scores")

        # Calculate scores for all abnormal patterns
        pattern_scores = self._calculate_pattern_scores(
            normal_patterns, abnormal_patterns
        )

        # Filter by score and support thresholds
        filtered_scores = self._filter_patterns(pattern_scores, abnormal_patterns)

        # Remove redundant child patterns
        pruned_scores = self._prune_child_patterns(filtered_scores, template_resolver)

        # Create ranked pattern objects
        ranked_patterns = []

        for pattern_key, score in pruned_scores.items():
            # Calculate depth and pod if calculator provided
            depth, pod = 0, "unknown"
            if depth_calculator:
                depth, pod = depth_calculator(event_graphs, pattern_key)

            # Check alarm association if associator provided
            alarm_flag, alarm_info = False, None
            if alarm_associator:
                alarm_flag, alarm_info = alarm_associator(pattern_key, pod, alarms)

            # Get templates if resolver provided
            source_template, target_template = "", ""
            if template_resolver:
                try:
                    source_id, target_id = self._parse_pattern_key(pattern_key)
                    source_template = template_resolver(source_id)
                    target_template = template_resolver(target_id)
                except Exception as e:
                    logger.warning(
                        f"Failed to resolve templates for {pattern_key}: {e}"
                    )

            # Create pattern object
            pattern = Pattern.from_key(
                pattern_key, abnormal_patterns.get(pattern_key, 0)
            )

            ranked_pattern = RankedPattern(
                pattern=pattern,
                score=score,
                depth=depth,
                pod=pod,
                alarm_flag=alarm_flag,
                alarm_info=alarm_info,
                source_template=source_template,
                target_template=target_template,
            )

            ranked_patterns.append(ranked_pattern)

        # Sort by score (descending), then by depth (descending)
        ranked_patterns.sort(key=lambda x: (x.score, x.depth), reverse=True)

        logger.info(f"Ranked {len(ranked_patterns)} patterns")
        return ranked_patterns

    def _calculate_pattern_scores(
        self, normal_patterns: PatternDict, abnormal_patterns: PatternDict
    ) -> Dict[str, float]:
        """Calculate anomaly scores for patterns."""
        scores = {}

        for pattern_key, abnormal_support in abnormal_patterns.items():
            if abnormal_support < self.min_support:
                continue

            normal_support = normal_patterns.get(pattern_key, 0)

            if self.score_metric == "anomaly_ratio":
                # Ratio of abnormal to total occurrences
                total_support = abnormal_support + normal_support
                score = abnormal_support / total_support if total_support > 0 else 1.0

            elif self.score_metric == "lift":
                # Lift: P(abnormal|pattern) / P(abnormal)
                total_abnormal = sum(abnormal_patterns.values())
                total_normal = sum(normal_patterns.values())
                total_occurrences = total_abnormal + total_normal

                if total_occurrences > 0:
                    p_abnormal = total_abnormal / total_occurrences
                    p_abnormal_given_pattern = abnormal_support / (
                        abnormal_support + normal_support
                    )
                    score = (
                        p_abnormal_given_pattern / p_abnormal if p_abnormal > 0 else 1.0
                    )
                else:
                    score = 1.0

            elif self.score_metric == "confidence":
                # Confidence: abnormal_support / total_pattern_support
                total_pattern_support = abnormal_support + normal_support
                score = (
                    abnormal_support / total_pattern_support
                    if total_pattern_support > 0
                    else 0.0
                )

            else:
                raise ValueError(f"Unknown score metric: {self.score_metric}")

            scores[pattern_key] = score

        return scores

    def _filter_patterns(
        self, pattern_scores: Dict[str, float], abnormal_patterns: PatternDict
    ) -> Dict[str, float]:
        """Filter patterns by score and support thresholds."""
        filtered = {}

        for pattern_key, score in pattern_scores.items():
            support = abnormal_patterns.get(pattern_key, 0)

            if score >= self.min_score and support >= self.min_support:
                filtered[pattern_key] = score
            else:
                logger.debug(
                    f"Filtering pattern {pattern_key}: score={score:.3f}, support={support}"
                )

        logger.info(
            f"Filtered {len(pattern_scores)} patterns to {len(filtered)} "
            f"with min_score={self.min_score}, min_support={self.min_support}"
        )
        return filtered

    def _prune_child_patterns(
        self,
        pattern_scores: Dict[str, float],
        template_resolver: Optional[Callable[[int], str]] = None,
    ) -> Dict[str, float]:
        """Remove child patterns that have parent patterns with higher scores."""
        if not template_resolver:
            return pattern_scores

        pruned = pattern_scores.copy()
        to_remove: Set[str] = set()

        for pattern_key in pattern_scores.keys():
            source_id, target_id = self._parse_pattern_key(pattern_key)

            # Skip if this is a metric pattern (can't be determined without templates)
            try:
                target_template = template_resolver(target_id)
                if self._is_metric_pattern(target_template):
                    continue
            except Exception:
                continue

            # Check if this pattern has a parent with higher score
            for other_key in pattern_scores.keys():
                if other_key == pattern_key:
                    continue

                other_source, other_target = self._parse_pattern_key(other_key)

                # Check if current pattern is child of other pattern
                if (
                    source_id == other_target
                    and pattern_scores[pattern_key] <= pattern_scores[other_key]
                ):
                    logger.debug(
                        f"Removing child pattern {pattern_key} (score: {pattern_scores[pattern_key]:.3f}) "
                        f"due to parent {other_key} (score: {pattern_scores[other_key]:.3f})"
                    )
                    to_remove.add(pattern_key)
                    break

        # Remove identified child patterns
        for pattern_key in to_remove:
            pruned.pop(pattern_key, None)

        logger.info(f"Pruned {len(to_remove)} child patterns")
        return pruned

    def _parse_pattern_key(self, pattern_key: str) -> tuple:
        """Parse pattern key into source and target IDs."""
        try:
            parts = pattern_key.split("_")
            if len(parts) >= 2:
                return int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            logger.warning(f"Invalid pattern key format: {pattern_key}")

        return 0, 0

    def _is_metric_pattern(self, template: str) -> bool:
        """Check if template represents a metric pattern."""
        metric_keywords = ["Cpu", "Memory", "Network", "metric", "alarm"]
        template_lower = template.lower()
        return any(keyword.lower() in template_lower for keyword in metric_keywords)

    def rank_by_custom_score(
        self,
        patterns: List[Pattern],
        score_function: Callable[[Pattern], float],
        reverse: bool = True,
    ) -> List[Pattern]:
        """
        Rank patterns using a custom scoring function.

        Args:
            patterns: List of patterns to rank
            score_function: Function that takes a pattern and returns a score
            reverse: Whether to sort in descending order

        Returns:
            Sorted list of patterns
        """
        logger.info(f"Ranking {len(patterns)} patterns with custom score function")

        # Calculate scores and sort
        scored_patterns = [(pattern, score_function(pattern)) for pattern in patterns]
        scored_patterns.sort(key=lambda x: x[1], reverse=reverse)

        # Return sorted patterns
        return [pattern for pattern, _ in scored_patterns]

    def calculate_confidence_scores(
        self, patterns: PatternDict, total_transactions: int
    ) -> Dict[str, float]:
        """
        Calculate confidence scores for patterns.

        Args:
            patterns: Pattern support dictionary
            total_transactions: Total number of transactions/graphs

        Returns:
            Dictionary mapping pattern keys to confidence scores
        """
        confidence_scores = {}

        for pattern_key, support in patterns.items():
            confidence = support / total_transactions if total_transactions > 0 else 0.0
            confidence_scores[pattern_key] = confidence

        return confidence_scores
