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
            results = run_nezha_pipeline(
                input_folder=input_folder,
                need_logs=True,
            )

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

        # Load service mapping to convert service IDs to names
        service_id_to_name = self._load_service_mapping(results)

        # Aggregate scores by service
        service_scores = defaultdict(list)
        service_pattern_counts = Counter()
        service_total_abnormal_support = defaultdict(int)

        for pattern_info in ranked_patterns:
            services = pattern_info.get("services", [])
            score = pattern_info.get("score", 0.0)
            abnormal_support = pattern_info.get("abnormal_support", 0)

            for service_id in services:
                service_name = service_id_to_name.get(
                    service_id, f"service_{service_id}"
                )

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

        # Sort by aggregated score (descending)
        service_rankings.sort(key=lambda x: x[1], reverse=True)

        logger.info(
            f"Aggregated {len(ranked_patterns)} patterns into {len(service_rankings)} service rankings"
        )

        # Log top services for debugging
        for i, (service_name, score) in enumerate(service_rankings[:5], 1):
            pattern_count = service_pattern_counts[service_name]
            abnormal_support = service_total_abnormal_support[service_name]
            logger.info(
                f"Rank {i}: {service_name} (score={score:.3f}, patterns={pattern_count}, support={abnormal_support})"
            )

        return service_rankings

    def _load_service_mapping(self, results: Dict) -> Dict[int, str]:
        """
        Load service ID to name mapping from results.

        Args:
            results: Nezha analysis results

        Returns:
            Dictionary mapping service IDs to service names
        """
        # Try to get service mapping from results
        service_mapping = results.get("service_mapping", {})

        if service_mapping and isinstance(service_mapping, dict):
            # If we have the mapping, create reverse mapping (id -> name)
            id_to_name = {}
            for name, service_id in service_mapping.items():
                id_to_name[service_id] = name
            return id_to_name

        # Fallback: create generic service names based on common TrainTicket services
        default_services = {
            1: "loadgenerator",
            2: "ts-admin-basic-info-service",
            3: "ts-basic-service",
            4: "ts-ticketinfo-service",
            5: "ts-order-service",
            6: "ts-order-other-service",
            7: "ts-config-service",
            8: "ts-station-service",
            9: "ts-train-service",
            10: "ts-travel-service",
            11: "ts-travel2-service",
            12: "ts-preserve-service",
            13: "ts-preserve-other-service",
            14: "ts-preserve-service",
            15: "ts-security-service",
            16: "ts-preserve-service",
            17: "ts-contacts-service",
            18: "ts-price-service",
            19: "ts-notification-service",
            20: "ts-inside-payment-service",
            21: "ts-execute-service",
            22: "ts-payment-service",
            23: "ts-rebook-service",
            24: "ts-cancel-service",
            25: "ts-assurance-service",
            26: "ts-travel2-service",
            27: "ts-seat-service",
            28: "ts-food-service",
            29: "ts-consign-service",
            30: "ts-user-service",
        }

        return default_services


def nezha_analysis(input_folder: Path, **kwargs) -> Dict:
    """
    Convenience function for running Nezha analysis.

    Args:
        input_folder: Path to input data folder
        **kwargs: Additional parameters for run_nezha_pipeline

    Returns:
        Analysis results dictionary
    """
    return run_nezha_pipeline(input_folder, **kwargs)
