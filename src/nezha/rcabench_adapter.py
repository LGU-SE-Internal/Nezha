"""
Nezha Algorithm Adapter for rcabench_platform

Implements the rcabench_platform Algorithm interface for Nezha root cause analysis.
Aggregates pattern-level results to service-level rankings.
"""

from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from rcabench_platform.v2.algorithms.spec import (
    Algorithm,
    AlgorithmAnswer,
    AlgorithmArgs,
)
from rcabench_platform.v2.logging import logger

from .integration import run_nezha_pipeline


class NezhaAlgorithm(Algorithm):
    """Nezha algorithm implementation for rcabench platform"""

    def needs_cpu_count(self) -> Optional[int]:
        return 4  # Nezha can benefit from parallel processing

    def __call__(self, args: AlgorithmArgs) -> List[AlgorithmAnswer]:
        """Execute Nezha algorithm and return service-level rankings"""

        logger.info("Starting Nezha algorithm execution")

        try:
            # Extract parameters from args
            input_folder = Path(args.input_folder)

            # Run Nezha analysis
            results_any = run_nezha_pipeline(
                input_folder=input_folder,
                need_logs=True,
                return_id_manager=False,
            )

            # Handle potential tuple return
            if isinstance(results_any, tuple):
                results = results_any[0]
            else:
                results = results_any

            if not results or not results.get("ranked_patterns"):
                logger.warning("No results from Nezha analysis")
                return []

            # Aggregate pattern-level results to service-level rankings
            service_rankings = self._aggregate_to_service_level(results)

            # Create algorithm answers
            answers = []
            for i, (service_name, service_score) in enumerate(service_rankings[:10], 1):
                answer = AlgorithmAnswer(
                    level="service",
                    name=service_name,
                    rank=i,
                )
                answers.append(answer)

            logger.info(
                f"Nezha analysis completed, returning {len(answers)} service rankings"
            )
            return answers

        except Exception as e:
            error_msg = f"Nezha algorithm execution failed: {str(e)}"
            logger.error(error_msg)
            import traceback

            logger.error(traceback.format_exc())
            return []

    def _aggregate_to_service_level(self, results: Dict) -> List[tuple]:
        """
        Aggregate pattern-level results to service-level rankings.

        Args:
            results: Nezha analysis results containing ranked patterns

        Returns:
            List of (service_name, aggregated_score) tuples, sorted by score descending
        """
        ranked_patterns = results.get("ranked_patterns", [])

        if not ranked_patterns:
            return []

        # Aggregate scores by service (services are now direct service names)
        service_scores = defaultdict(list)
        service_pattern_counts = Counter()
        service_total_abnormal_support = defaultdict(int)

        for pattern_info in ranked_patterns:
            services = pattern_info.get("services", [])
            score = pattern_info.get("score", 0.0)
            abnormal_support = pattern_info.get("abnormal_support", 0)

            for service_name in services:
                # Collect scores for this service
                service_scores[service_name].append(score)
                service_pattern_counts[service_name] += 1
                service_total_abnormal_support[service_name] += abnormal_support

        # Calculate aggregated scores for each service
        service_rankings = []

        for service_name, scores in service_scores.items():
            if not scores:
                continue

            # Aggregation strategy: weighted combination of multiple factors
            # 1. Average suspiciousness score
            avg_score = sum(scores) / len(scores)

            # 2. Maximum suspiciousness score (worst case)
            max_score = max(scores)

            # 3. Number of suspicious patterns (frequency)
            pattern_count = service_pattern_counts[service_name]

            # 4. Total abnormal support (impact)
            total_abnormal = service_total_abnormal_support[service_name]

            # Weighted aggregation
            # Higher weight on max score and pattern frequency
            aggregated_score = (
                0.4 * max_score  # Worst case suspiciousness
                + 0.3 * avg_score  # Average suspiciousness
                + 0.2 * min(pattern_count / 5.0, 1.0)  # Pattern frequency (normalized)
                + 0.1 * min(total_abnormal / 10.0, 1.0)  # Impact (normalized)
            )

            service_rankings.append((service_name, aggregated_score))

        # Filter out loadgenerator service and sort by aggregated score (descending)
        service_rankings = [
            (service_name, score)
            for service_name, score in service_rankings
            if service_name != "loadgenerator"
        ]
        service_rankings.sort(key=lambda x: x[1], reverse=True)

        logger.info(
            f"Aggregated {len(ranked_patterns)} patterns into {len(service_rankings)} service rankings (excluding loadgenerator)"
        )

        # Log top services for debugging
        for i, (service_name, score) in enumerate(service_rankings[:5], 1):
            pattern_count = service_pattern_counts[service_name]
            abnormal_support = service_total_abnormal_support[service_name]
            logger.info(
                f"Rank {i}: {service_name} (score={score:.3f}, patterns={pattern_count}, support={abnormal_support})"
            )

        return service_rankings


def nezha_analysis(input_folder: Path, **kwargs) -> Dict:
    """
    Convenience function for running Nezha analysis.

    Args:
        input_folder: Path to input data folder
        **kwargs: Additional parameters for run_nezha_pipeline

    Returns:
        Analysis results dictionary
    """
    result = run_nezha_pipeline(input_folder, return_id_manager=False, **kwargs)
    if isinstance(result, tuple):
        return result[0]
    return result
