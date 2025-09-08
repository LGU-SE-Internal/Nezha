"""
Nezha Integration with rcabench_platform

This script provides integration between Nezha and rcabench_platform,
allowing Nezha to work with the new data format and event encoding system.
"""

import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from rcabench_platform.v2.logging import logger

from .algorithms import NezhaAlgorithm, run_nezha_analysis
from .data_structures import TraceData
from .preprocessor import NezhaPreprocessor


class NezhaIntegrator:
    """
    Integration layer between Nezha and rcabench_platform.

    Handles data loading, preprocessing, and algorithm execution
    in a unified interface compatible with rcabench_platform.
    """

    def __init__(self, input_folder: Path):
        """
        Initialize integrator.

        Args:
            input_folder: Path to rcabench_platform format data folder
        """
        self.input_folder = input_folder
        self.preprocessor = NezhaPreprocessor(input_folder)

        # Results storage
        self.trace_data_list: List[TraceData] = []
        self.normal_traces: List[TraceData] = []
        self.abnormal_traces: List[TraceData] = []

    def load_and_preprocess(self, need_logs: bool = True) -> None:
        """
        Load and preprocess data using rcabench_platform components.

        Args:
            need_logs: Whether to load and process log data
        """
        logger.info("Loading and preprocessing data...")

        # Use preprocessor to load and process data
        self.trace_data_list, metrics = self.preprocessor.load_and_process_data(
            need_logs=need_logs
        )

        logger.info(f"Preprocessed {len(self.trace_data_list)} traces")

    def separate_normal_abnormal_traces(
        self, inject_time: Optional[str] = None, normal_ratio: float = 0.5
    ) -> None:
        """
        Separate traces into normal and abnormal based on time or ratio.

        Args:
            inject_time: Optional injection time to separate traces
            normal_ratio: If no inject_time, use this ratio for separation
        """
        if inject_time:
            # TODO: Implement time-based separation when trace timestamps are available
            logger.warning("Time-based separation not yet implemented, using ratio")

        # For now, use simple ratio-based separation
        split_point = int(len(self.trace_data_list) * normal_ratio)

        # Sort traces by trace_id for consistent splitting
        sorted_traces = sorted(self.trace_data_list, key=lambda x: x.trace_id)

        self.normal_traces = sorted_traces[:split_point]
        self.abnormal_traces = sorted_traces[split_point:]

        logger.info(
            f"Separated into {len(self.normal_traces)} normal "
            f"and {len(self.abnormal_traces)} abnormal traces"
        )

    def run_analysis(
        self,
        min_support: int = 5,
        min_score: float = 0.67,
        top_k: int = 10,
        ground_truth: Optional[Set[Tuple[int, int]]] = None,
    ) -> Dict:
        """
        Run Nezha root cause analysis.

        Args:
            min_support: Minimum pattern support threshold
            min_score: Minimum suspiciousness score threshold
            top_k: Number of top patterns to return
            ground_truth: Optional ground truth for evaluation

        Returns:
            Analysis results dictionary
        """
        if not self.normal_traces or not self.abnormal_traces:
            raise ValueError("Must separate traces before running analysis")

        logger.info("Running Nezha root cause analysis...")

        # Run analysis
        result = run_nezha_analysis(
            normal_traces=self.normal_traces,
            abnormal_traces=self.abnormal_traces,
            ground_truth=ground_truth,
            min_support=min_support,
            min_score=min_score,
            top_k=top_k,
        )

        # Convert to dictionary format for easier consumption
        results_dict = {
            "ranked_patterns": [
                {
                    "pattern": pattern.pattern,
                    "score": pattern.score,
                    "abnormal_support": pattern.abnormal_support,
                    "normal_support": pattern.normal_support,
                    "depth": pattern.depth,
                    "services": list(pattern.services),
                    "rank": pattern.rank,
                }
                for pattern in result.ranked_patterns
            ],
            "total_abnormal_patterns": result.total_abnormal_patterns,
            "total_normal_patterns": result.total_normal_patterns,
            "processing_time_seconds": result.processing_time_seconds,
            "top_k_accuracy": result.top_k_accuracy or {},
        }

        return results_dict

    def get_pattern_explanation(self, pattern: Tuple[int, int]) -> Dict[str, str]:
        """
        Get human-readable explanation of a pattern.

        Args:
            pattern: Event pattern tuple

        Returns:
            Pattern explanation dictionary
        """
        if not self.preprocessor.event_manager:
            return {"error": "Event manager not initialized"}

        # Use algorithm to explain pattern
        algorithm = NezhaAlgorithm()

        return algorithm.explain_pattern(pattern, self.preprocessor.event_manager)

    def export_results(self, results: Dict, output_file: Path) -> None:
        """
        Export analysis results to file.

        Args:
            results: Results dictionary from run_analysis
            output_file: Path to output file
        """
        import json

        # Add metadata
        export_data = {
            "metadata": {
                "input_folder": str(self.input_folder),
                "total_traces": len(self.trace_data_list),
                "normal_traces": len(self.normal_traces),
                "abnormal_traces": len(self.abnormal_traces),
                "export_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            "results": results,
        }

        with open(output_file, "w") as f:
            json.dump(export_data, f, indent=2)

        logger.info(f"Results exported to {output_file}")


def run_nezha_pipeline(
    input_folder: Path,
    output_file: Optional[Path] = None,
    inject_time: Optional[str] = None,
    normal_ratio: float = 0.5,
    min_support: int = 5,
    min_score: float = 0.67,
    top_k: int = 10,
    need_logs: bool = True,
    ground_truth: Optional[Set[Tuple[int, int]]] = None,
    return_id_manager: bool = False,
) -> Dict | Tuple[Dict, Optional[object]]:
    """
    Run complete Nezha pipeline.

    Args:
        input_folder: Path to input data folder
        output_file: Optional path to save results
        inject_time: Optional injection time for separation
        normal_ratio: Ratio for trace separation if no inject_time
        min_support: Minimum pattern support threshold
        min_score: Minimum suspiciousness score threshold
        top_k: Number of top patterns to return
        need_logs: Whether to load log data
        ground_truth: Optional ground truth for evaluation
        return_id_manager: Whether to return (results, id_manager) tuple

    Returns:
        Analysis results dictionary, or (results, id_manager) tuple if return_id_manager=True
    """
    # Initialize integrator
    integrator = NezhaIntegrator(input_folder)

    # Step 1: Load and preprocess
    integrator.load_and_preprocess(need_logs=need_logs)

    # Step 2: Separate traces
    integrator.separate_normal_abnormal_traces(
        inject_time=inject_time, normal_ratio=normal_ratio
    )

    # Step 3: Run analysis
    results = integrator.run_analysis(
        min_support=min_support,
        min_score=min_score,
        top_k=top_k,
        ground_truth=ground_truth,
    )

    # Step 4: Export results if requested
    if output_file:
        integrator.export_results(results, output_file)

    if return_id_manager:
        return results, integrator.preprocessor.event_manager
    return results


# Convenience functions for specific datasets
def run_nezha_hipster(
    data_folder: Path = Path("./rca_data/2022-08-22"), **kwargs
) -> Dict:
    """Run Nezha on OnlineBoutique (hipster) dataset."""
    logger.info("Running Nezha on OnlineBoutique dataset...")
    result = run_nezha_pipeline(data_folder, return_id_manager=False, **kwargs)
    if isinstance(result, tuple):
        return result[0]
    return result


def run_nezha_trainticket(
    data_folder: Path = Path("./rca_data/2023-01-29"), **kwargs
) -> Dict:
    """Run Nezha on TrainTicket dataset."""
    logger.info("Running Nezha on TrainTicket dataset...")
    result = run_nezha_pipeline(data_folder, return_id_manager=False, **kwargs)
    if isinstance(result, tuple):
        return result[0]
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Nezha Integration Pipeline")
    parser.add_argument("input_folder", type=Path, help="Input data folder")
    parser.add_argument("--output", type=Path, help="Output results file")
    parser.add_argument("--inject-time", help="Fault injection time")
    parser.add_argument(
        "--normal-ratio", type=float, default=0.5, help="Normal trace ratio"
    )
    parser.add_argument(
        "--min-support", type=int, default=5, help="Minimum pattern support"
    )
    parser.add_argument(
        "--min-score", type=float, default=0.67, help="Minimum suspiciousness score"
    )
    parser.add_argument("--top-k", type=int, default=10, help="Number of top patterns")
    parser.add_argument("--no-logs", action="store_true", help="Skip log processing")

    args = parser.parse_args()

    results_any = run_nezha_pipeline(
        input_folder=args.input_folder,
        output_file=args.output,
        inject_time=args.inject_time,
        normal_ratio=args.normal_ratio,
        min_support=args.min_support,
        min_score=args.min_score,
        top_k=args.top_k,
        need_logs=not args.no_logs,
    )
    results = results_any[0] if isinstance(results_any, tuple) else results_any

    # Print summary
    print("\nNezha Analysis Results:")
    print(f"Found {len(results['ranked_patterns'])} suspicious patterns")
    print(f"Processing time: {results['processing_time_seconds']:.2f}s")

    if results.get("top_k_accuracy"):
        print("\nAccuracy Results:")
        for k, acc in results["top_k_accuracy"].items():
            print(f"  Top-{k}: {acc:.2f}%")
