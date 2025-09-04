#!/usr/bin/env python3
"""
Nezha Main Entry Point

Refactored version of Nezha that integrates with rcabench_platform.
"""

import argparse
import sys
from pathlib import Path

from rcabench_platform.v2.logging import logger

# Add src to path for development
current_dir = Path(__file__).parent
src_dir = current_dir / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))

try:
    from nezha.example import run_hipster_example, run_trainticket_example
    from nezha.integration import run_nezha_pipeline
except ImportError as e:
    logger.error(f"Failed to import Nezha modules: {e}")
    logger.error("Make sure rcabench_platform is installed and accessible")
    sys.exit(1)


def main():
    """Main entry point for Nezha."""
    parser = argparse.ArgumentParser(
        description="Nezha - Interpretable Fine-Grained Root Causes Analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run on custom data folder
  python main_nezha.py --input ./data/experiment1 --output results.json

  # Run on OnlineBoutique dataset
  python main_nezha.py --dataset hipster --min-score 0.8

  # Run on TrainTicket dataset with custom parameters
  python main_nezha.py --dataset ts --min-support 10 --top-k 5
        """,
    )

    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input",
        type=Path,
        help="Path to input data folder (rcabench_platform format)",
    )
    input_group.add_argument(
        "--dataset",
        choices=["hipster", "ts"],
        help="Use predefined dataset (hipster=OnlineBoutique, ts=TrainTicket)",
    )

    # Output options
    parser.add_argument(
        "--output", type=Path, help="Path to save results (JSON format)"
    )

    # Data processing options
    parser.add_argument(
        "--inject-time",
        help="Fault injection time for separating normal/abnormal traces",
    )
    parser.add_argument(
        "--normal-ratio",
        type=float,
        default=0.5,
        help="Ratio of traces to consider as normal (default: 0.5)",
    )
    parser.add_argument(
        "--no-logs", action="store_true", help="Skip log processing (use only traces)"
    )

    # Algorithm parameters
    parser.add_argument(
        "--min-support",
        type=int,
        default=5,
        help="Minimum pattern support threshold (default: 5)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.67,
        help="Minimum suspiciousness score threshold (default: 0.67)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of top patterns to return (default: 10)",
    )

    # Execution options
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        import logging

        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("Starting Nezha Root Cause Analysis...")
    logger.info(f"Arguments: {args}")

    try:
        if args.dataset:
            # Use predefined dataset
            if args.dataset == "hipster":
                logger.info("Running OnlineBoutique example...")
                result = run_hipster_example()
            elif args.dataset == "ts":
                logger.info("Running TrainTicket example...")
                result = run_trainticket_example()
            else:
                logger.error(f"Unknown dataset: {args.dataset}")
                return 1

        else:
            # Use custom input folder
            if not args.input.exists():
                logger.error(f"Input folder does not exist: {args.input}")
                return 1

            logger.info(f"Processing data from: {args.input}")
            result = run_nezha_pipeline(
                input_folder=args.input,
                output_file=args.output,
                inject_time=args.inject_time,
                normal_ratio=args.normal_ratio,
                min_support=args.min_support,
                min_score=args.min_score,
                top_k=args.top_k,
                need_logs=not args.no_logs,
            )

        # Print summary
        if result:
            print("\n" + "=" * 50)
            print("NEZHA ANALYSIS RESULTS")
            print("=" * 50)

            if isinstance(result, dict):
                print(
                    f"Suspicious patterns found: {len(result.get('ranked_patterns', []))}"
                )
                print(
                    f"Processing time: {result.get('processing_time_seconds', 0):.2f}s"
                )

                # Show top patterns
                patterns = result.get("ranked_patterns", [])[:5]
                if patterns:
                    print("\nTop suspicious patterns:")
                    for i, pattern in enumerate(patterns):
                        print(f"  {i + 1}. Pattern {pattern['pattern']}")
                        print(f"     Score: {pattern['score']:.3f}")
                        print(
                            f"     Abnormal: {pattern['abnormal_support']}, "
                            f"Normal: {pattern['normal_support']}"
                        )

                # Show accuracy if available
                accuracy = result.get("top_k_accuracy", {})
                if accuracy:
                    print("\nAccuracy results:")
                    for k, acc in sorted(accuracy.items()):
                        print(f"  Top-{k}: {acc:.2f}%")

            print("\nAnalysis completed successfully!")
            return 0
        else:
            logger.error("Analysis failed")
            return 1

    except KeyboardInterrupt:
        logger.info("Analysis interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Analysis failed with error: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
