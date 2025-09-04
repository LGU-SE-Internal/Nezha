"""
Example usage of Nezha algorithm with rcabench_platform integration.

This script demonstrates how to use the refactored Nezha algorithm
for root cause analysis on microservice traces.
"""

from pathlib import Path
from typing import Set, Tuple

from rcabench_platform.v2.logging import logger

from nezha.algorithms import run_nezha_analysis
from nezha.data_structures import TraceData
from nezha.preprocessor import NezhaPreprocessor


def load_ground_truth(ground_truth_file: Path) -> Set[Tuple[int, int]]:
    """
    Load ground truth patterns from file.

    This is a placeholder implementation - adapt based on your ground truth format.
    """
    # TODO: Implement based on your ground truth format
    # For now, return empty set
    return set()


def filter_traces_by_time(
    traces: list[TraceData], normal_end_time: str, abnormal_start_time: str
) -> tuple[list[TraceData], list[TraceData]]:
    """
    Filter traces into normal and abnormal based on time ranges.

    This is a simplified implementation - in practice you'd need to
    parse the time fields and compare with trace timestamps.
    """
    # TODO: Implement proper time-based filtering
    # For now, split traces in half for demonstration
    mid_point = len(traces) // 2
    normal_traces = traces[:mid_point]
    abnormal_traces = traces[mid_point:]

    return normal_traces, abnormal_traces


def run_nezha_experiment(
    input_folder: Path,
    ground_truth_file: Path = None,
    min_support: int = 5,
    min_score: float = 0.67,
    top_k: int = 10,
):
    """
    Run a complete Nezha experiment.

    Args:
        input_folder: Path to input data folder
        ground_truth_file: Optional path to ground truth file
        min_support: Minimum pattern support threshold
        min_score: Minimum suspiciousness score threshold
        top_k: Number of top patterns to return
    """
    logger.info("Starting Nezha experiment...")
    logger.info(f"Input folder: {input_folder}")

    # Step 1: Preprocessing
    logger.info("=== PREPROCESSING PHASE ===")
    preprocessor = NezhaPreprocessor(input_folder)

    # Load and process all data
    trace_data_list, processing_metrics = preprocessor.load_and_process_data(
        need_logs=True
    )

    if not trace_data_list:
        logger.error("No traces processed successfully")
        return

    # Step 2: Separate normal and abnormal traces
    logger.info("=== DATA SEPARATION PHASE ===")

    # TODO: Implement proper time-based separation based on your data structure
    # For now, use a simple split for demonstration
    normal_traces, abnormal_traces = filter_traces_by_time(
        trace_data_list, "normal_end", "abnormal_start"
    )

    logger.info(f"Normal traces: {len(normal_traces)}")
    logger.info(f"Abnormal traces: {len(abnormal_traces)}")

    if not normal_traces or not abnormal_traces:
        logger.error("Need both normal and abnormal traces for analysis")
        return

    # Step 3: Load ground truth (optional)
    ground_truth = None
    if ground_truth_file and ground_truth_file.exists():
        logger.info("Loading ground truth...")
        ground_truth = load_ground_truth(ground_truth_file)
        logger.info(f"Loaded {len(ground_truth)} ground truth patterns")

    # Step 4: Run algorithm
    logger.info("=== ALGORITHM PHASE ===")

    result = run_nezha_analysis(
        normal_traces=normal_traces,
        abnormal_traces=abnormal_traces,
        service_mapping=preprocessor.service_mapping,
        ground_truth=ground_truth,
        min_support=min_support,
        min_score=min_score,
        top_k=top_k,
    )

    # Step 5: Report results
    logger.info("=== RESULTS ===")
    logger.info(f"Total suspicious patterns found: {len(result.ranked_patterns)}")
    logger.info(f"Analysis time: {result.processing_time_seconds:.2f}s")

    # Display top patterns
    logger.info("Top suspicious patterns:")
    for i, pattern_score in enumerate(
        result.ranked_patterns[: min(5, len(result.ranked_patterns))]
    ):
        service_name = preprocessor.service_mapping.get_service_name(
            list(pattern_score.services)[0] if pattern_score.services else -1
        )
        logger.info(f"  {i + 1}. Pattern {pattern_score.pattern}")
        logger.info(f"     Score: {pattern_score.score:.3f}")
        logger.info(f"     Abnormal support: {pattern_score.abnormal_support}")
        logger.info(f"     Normal support: {pattern_score.normal_support}")
        logger.info(f"     Depth: {pattern_score.depth:.1f}")
        logger.info(f"     Service: {service_name}")
        logger.info("")

    # Display accuracy if ground truth available
    if result.top_k_accuracy:
        logger.info("Accuracy results:")
        for k, accuracy in result.top_k_accuracy.items():
            logger.info(f"  Top-{k}: {accuracy:.2f}%")

    logger.info("Nezha experiment completed!")

    return result


def run_hipster_example():
    """Run example with OnlineBoutique (hipster) data."""
    logger.info("Running OnlineBoutique example...")

    # Update these paths based on your data location
    input_folder = Path("./rca_data/2022-08-22")
    ground_truth_file = Path("./construct_data/root_cause_hipster.json")

    if not input_folder.exists():
        logger.error(f"Input folder not found: {input_folder}")
        return

    result = run_nezha_experiment(
        input_folder=input_folder,
        ground_truth_file=ground_truth_file if ground_truth_file.exists() else None,
        min_support=5,
        min_score=0.67,
        top_k=10,
    )

    return result


def run_trainticket_example():
    """Run example with TrainTicket data."""
    logger.info("Running TrainTicket example...")

    # Update these paths based on your data location
    input_folder = Path("./rca_data/2023-01-29")
    ground_truth_file = Path("./construct_data/root_cause_ts.json")

    if not input_folder.exists():
        logger.error(f"Input folder not found: {input_folder}")
        return

    result = run_nezha_experiment(
        input_folder=input_folder,
        ground_truth_file=ground_truth_file if ground_truth_file.exists() else None,
        min_support=5,
        min_score=0.67,
        top_k=10,
    )

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Nezha Root Cause Analysis")
    parser.add_argument(
        "--dataset",
        choices=["hipster", "ts"],
        default="hipster",
        help="Dataset to use (hipster=OnlineBoutique, ts=TrainTicket)",
    )
    parser.add_argument("--input-folder", type=Path, help="Path to input data folder")
    parser.add_argument("--ground-truth", type=Path, help="Path to ground truth file")
    parser.add_argument(
        "--min-support", type=int, default=5, help="Minimum pattern support"
    )
    parser.add_argument(
        "--min-score", type=float, default=0.67, help="Minimum suspiciousness score"
    )
    parser.add_argument(
        "--top-k", type=int, default=10, help="Number of top patterns to return"
    )

    args = parser.parse_args()

    if args.input_folder:
        # Custom input
        run_nezha_experiment(
            input_folder=args.input_folder,
            ground_truth_file=args.ground_truth,
            min_support=args.min_support,
            min_score=args.min_score,
            top_k=args.top_k,
        )
    elif args.dataset == "hipster":
        run_hipster_example()
    elif args.dataset == "ts":
        run_trainticket_example()
    else:
        logger.error("Please specify either --input-folder or --dataset")
