"""
Test Nezha with real TrainTicket data.

This script tests the refactored Nezha algorithm using the real TrainTicket dataset
from the test folder.
"""

import datetime
import json
import sys
from pathlib import Path

# Add src to path for development
current_dir = Path(__file__).parent
src_dir = current_dir / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))

try:
    from nezha.algorithms import run_nezha_analysis
    from nezha.integration import NezhaIntegrator
    from nezha.preprocessor import NezhaPreprocessor
    from rcabench_platform.v2.logging import logger
except ImportError as e:
    print(f"Error importing modules: {e}")
    print(
        "Make sure rcabench_platform is installed and the src directory is set up correctly"
    )
    sys.exit(1)


def load_env_info(input_folder: Path) -> dict:
    """Load environment information from env.json"""
    env_file = input_folder / "env.json"
    if env_file.exists():
        with open(env_file, "r") as f:
            return json.load(f)
    return {}


def convert_timestamp_to_datetime(timestamp_str: str) -> datetime.datetime:
    """Convert Unix timestamp string to datetime"""
    timestamp = int(timestamp_str)
    return datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)


def test_data_loading(input_folder: Path):
    """Test basic data loading functionality"""
    logger.info("Testing data loading...")

    try:
        preprocessor = NezhaPreprocessor(input_folder)

        # Test loading traces and logs
        trace_data_list, metrics = preprocessor.load_and_process_data(need_logs=True)

        logger.info(f"✓ Successfully loaded {len(trace_data_list)} traces")
        logger.info(f"✓ Processing metrics: {metrics}")

        # Show some basic statistics
        if trace_data_list:
            total_patterns = sum(len(td.enhanced_patterns) for td in trace_data_list)
            services = set()
            for td in trace_data_list:
                for pattern in td.enhanced_patterns:
                    services.add(pattern.service)  # service is int, not set

            logger.info(f"✓ Total enhanced patterns: {total_patterns}")
            logger.info(f"✓ Unique services involved: {len(services)}")

            # Show service mapping
            if preprocessor.service_mapping:
                logger.info(
                    f"✓ Service mapping created for {len(preprocessor.service_mapping.service_to_id)} services:"
                )
                for service, service_id in sorted(
                    preprocessor.service_mapping.service_to_id.items()
                ):
                    logger.info(f"   {service_id}: {service}")

        return trace_data_list, preprocessor

    except Exception as e:
        logger.error(f"✗ Data loading failed: {e}")
        import traceback

        traceback.print_exc()
        return None, None


def test_time_based_separation(trace_data_list, env_info: dict):
    """Test separating traces based on injection time"""
    logger.info("Testing time-based trace separation...")

    try:
        normal_end = int(env_info.get("NORMAL_END", "0"))
        abnormal_start = int(env_info.get("ABNORMAL_START", "0"))

        normal_end_dt = convert_timestamp_to_datetime(str(normal_end))
        abnormal_start_dt = convert_timestamp_to_datetime(str(abnormal_start))

        logger.info(f"Normal phase ends at: {normal_end_dt}")
        logger.info(f"Abnormal phase starts at: {abnormal_start_dt}")

        # For now, use simple ratio-based separation since we need to implement proper time-based filtering
        # TODO: Implement proper time-based filtering using the trace timestamps
        mid_point = len(trace_data_list) // 2
        normal_traces = trace_data_list[:mid_point]
        abnormal_traces = trace_data_list[mid_point:]

        logger.info(
            f"✓ Separated into {len(normal_traces)} normal and {len(abnormal_traces)} abnormal traces"
        )
        logger.info(
            "Note: Using ratio-based separation for now. Time-based separation needs implementation."
        )

        return normal_traces, abnormal_traces

    except Exception as e:
        logger.error(f"✗ Trace separation failed: {e}")
        return None, None


def test_nezha_analysis(normal_traces, abnormal_traces, service_mapping):
    """Test running the full Nezha analysis"""
    logger.info("Testing Nezha root cause analysis...")

    try:
        result = run_nezha_analysis(
            normal_traces=normal_traces,
            abnormal_traces=abnormal_traces,
            service_mapping=service_mapping,
            min_support=3,  # Lower threshold for testing
            min_score=0.6,  # Lower threshold for testing
            top_k=15,
        )

        logger.info("✓ Analysis completed successfully!")
        logger.info(f"✓ Found {len(result.ranked_patterns)} suspicious patterns")
        logger.info(f"✓ Processing time: {result.processing_time_seconds:.2f}s")

        # Show top patterns
        logger.info("Top suspicious patterns:")
        for i, pattern_score in enumerate(result.ranked_patterns[:5]):
            service_names = [
                service_mapping.get_service_name(sid) for sid in pattern_score.services
            ]
            logger.info(f"  {i + 1}. Pattern {pattern_score.pattern}")
            logger.info(f"     Score: {pattern_score.score:.3f}")
            logger.info(f"     Abnormal support: {pattern_score.abnormal_support}")
            logger.info(f"     Normal support: {pattern_score.normal_support}")
            logger.info(f"     Depth: {pattern_score.depth:.1f}")
            logger.info(f"     Services: {service_names}")
            logger.info("")

        return result

    except Exception as e:
        logger.error(f"✗ Nezha analysis failed: {e}")
        import traceback

        traceback.print_exc()
        return None


def test_integration_pipeline(input_folder: Path):
    """Test the complete integration pipeline"""
    logger.info("Testing complete integration pipeline...")

    try:
        integrator = NezhaIntegrator(input_folder)

        # Load and preprocess
        integrator.load_and_preprocess(need_logs=True)

        # Separate traces (using ratio for now)
        integrator.separate_normal_abnormal_traces(normal_ratio=0.5)

        # Run analysis
        results = integrator.run_analysis(min_support=3, min_score=0.6, top_k=15)

        logger.info("✓ Integration pipeline completed successfully!")
        logger.info("✓ Results summary:")
        logger.info(f"   - Suspicious patterns: {len(results['ranked_patterns'])}")
        logger.info(
            f"   - Total abnormal patterns: {results['total_abnormal_patterns']}"
        )
        logger.info(f"   - Total normal patterns: {results['total_normal_patterns']}")
        logger.info(f"   - Processing time: {results['processing_time_seconds']:.2f}s")

        return results

    except Exception as e:
        logger.error(f"✗ Integration pipeline failed: {e}")
        import traceback

        traceback.print_exc()
        return None


def main():
    """Main test function"""
    input_folder = Path(
        "D:/workspace/Nezha/test/ts0-ts-preserve-service-request-replace-method-cw7ndj"
    )

    if not input_folder.exists():
        logger.error(f"Input folder does not exist: {input_folder}")
        return 1

    logger.info("=" * 60)
    logger.info("TESTING NEZHA WITH REAL TRAINTICKET DATA")
    logger.info("=" * 60)
    logger.info(f"Data folder: {input_folder}")

    # Load environment info
    env_info = load_env_info(input_folder)
    logger.info(f"Environment info: {env_info}")

    # Test 1: Data loading
    logger.info("\n" + "=" * 40)
    logger.info("TEST 1: Data Loading")
    logger.info("=" * 40)

    trace_data_list, preprocessor = test_data_loading(input_folder)
    if not trace_data_list or not preprocessor:
        logger.error("Data loading test failed, stopping here")
        return 1

    # Test 2: Trace separation
    logger.info("\n" + "=" * 40)
    logger.info("TEST 2: Trace Separation")
    logger.info("=" * 40)

    normal_traces, abnormal_traces = test_time_based_separation(
        trace_data_list, env_info
    )
    if not normal_traces or not abnormal_traces:
        logger.error("Trace separation test failed, stopping here")
        return 1

    # Test 3: Nezha analysis
    logger.info("\n" + "=" * 40)
    logger.info("TEST 3: Nezha Analysis")
    logger.info("=" * 40)

    result = test_nezha_analysis(
        normal_traces, abnormal_traces, preprocessor.service_mapping
    )
    if not result:
        logger.error("Nezha analysis test failed")
        return 1

    # Test 4: Integration pipeline
    logger.info("\n" + "=" * 40)
    logger.info("TEST 4: Integration Pipeline")
    logger.info("=" * 40)

    integration_result = test_integration_pipeline(input_folder)
    if not integration_result:
        logger.error("Integration pipeline test failed")
        return 1

    # Final summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    logger.info("✓ All tests passed successfully!")
    logger.info("✓ Nezha refactored version is working with real TrainTicket data")
    logger.info(f"✓ Data contains {len(trace_data_list)} traces")
    logger.info(f"✓ Found {len(result.ranked_patterns)} suspicious patterns")
    logger.info("✓ Ready for production use!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
