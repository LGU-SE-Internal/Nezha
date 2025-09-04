"""
Run Nezha analysis on the real TrainTicket data.

This script provides an easy way to run the refactored Nezha algorithm
on the real data provided by the user.
"""

import sys
from pathlib import Path

# Add src to path for development
current_dir = Path(__file__).parent
src_dir = current_dir / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))

try:
    from nezha.integration import run_nezha_pipeline
    from rcabench_platform.v2.logging import logger
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure rcabench_platform is installed")
    sys.exit(1)


def main():
    """Main function to run Nezha on real data"""

    # Set the data path
    data_path = Path(
        "D:/workspace/Nezha/test/ts0-ts-preserve-service-request-replace-method-cw7ndj"
    )
    output_path = Path("D:/workspace/Nezha/results_real_data.json")

    if not data_path.exists():
        logger.error(f"Data path does not exist: {data_path}")
        logger.error("Please ensure the test data is available")
        return 1

    logger.info("🚀 Running Nezha Analysis on Real TrainTicket Data")
    logger.info("=" * 60)
    logger.info(f"Data folder: {data_path}")
    logger.info(f"Output file: {output_path}")

    try:
        # Run the complete pipeline
        results = run_nezha_pipeline(
            input_folder=data_path,
            output_file=output_path,
            inject_time=None,  # Could implement time-based separation
            normal_ratio=0.5,  # Use 50/50 split for now
            min_support=3,  # Lower threshold for more patterns
            min_score=0.6,  # Lower threshold for more patterns
            top_k=20,  # Get more patterns
            need_logs=True,  # Include log analysis
        )

        # Print detailed results
        logger.info("")
        logger.info("📊 ANALYSIS RESULTS")
        logger.info("=" * 40)
        logger.info(f"✓ Found {len(results['ranked_patterns'])} suspicious patterns")
        logger.info(f"✓ Total abnormal patterns: {results['total_abnormal_patterns']}")
        logger.info(f"✓ Total normal patterns: {results['total_normal_patterns']}")
        logger.info(f"✓ Processing time: {results['processing_time_seconds']:.2f}s")

        # Show top patterns with details
        logger.info("")
        logger.info("🔍 TOP SUSPICIOUS PATTERNS")
        logger.info("=" * 40)

        for i, pattern in enumerate(results["ranked_patterns"][:10]):
            logger.info(f"Rank {i + 1}: Pattern {pattern['pattern']}")
            logger.info(f"  Score: {pattern['score']:.3f}")
            logger.info(f"  Abnormal support: {pattern['abnormal_support']}")
            logger.info(f"  Normal support: {pattern['normal_support']}")
            logger.info(f"  Depth: {pattern['depth']:.1f}")
            logger.info(f"  Services: {pattern['services']}")
            logger.info("")

        # Show insights based on the data
        logger.info("🧠 INSIGHTS")
        logger.info("=" * 40)

        # Analyze service involvement
        service_pattern_count = {}
        for pattern in results["ranked_patterns"]:
            for service in pattern["services"]:
                service_pattern_count[service] = (
                    service_pattern_count.get(service, 0) + 1
                )

        if service_pattern_count:
            logger.info("Services most involved in suspicious patterns:")
            for service, count in sorted(
                service_pattern_count.items(), key=lambda x: x[1], reverse=True
            )[:5]:
                logger.info(f"  Service {service}: {count} patterns")

        # Analyze score distribution
        high_score_patterns = [
            p for p in results["ranked_patterns"] if p["score"] >= 0.9
        ]
        medium_score_patterns = [
            p for p in results["ranked_patterns"] if 0.7 <= p["score"] < 0.9
        ]

        logger.info("Score distribution:")
        logger.info(f"  High confidence (≥0.9): {len(high_score_patterns)} patterns")
        logger.info(
            f"  Medium confidence (0.7-0.9): {len(medium_score_patterns)} patterns"
        )

        # Check if ts-preserve-service is involved (based on the data path name)
        preserve_patterns = [
            p
            for p in results["ranked_patterns"]
            if any("preserve" in str(s) for s in p["services"])
        ]
        if preserve_patterns:
            logger.info(
                f"ts-preserve-service related patterns: {len(preserve_patterns)}"
            )
            logger.info(
                "This aligns with the experiment name suggesting preserve service issues"
            )

        logger.info("")
        logger.info("✅ Analysis completed successfully!")
        logger.info(f"📁 Detailed results saved to: {output_path}")

        return 0

    except Exception as e:
        logger.error(f"❌ Analysis failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
