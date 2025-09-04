"""
Test script for Nezha refactored version.

This script tests the basic functionality without requiring real data.
"""

import sys
from pathlib import Path

# Add src to path
current_dir = Path(__file__).parent
src_dir = current_dir / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))


def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")

    try:
        from nezha.data_structures import (
            EnhancedEventPattern,
            PatternSupport,
            ServiceMapping,
            TraceData,
        )

        print("✓ Data structures imported successfully")

        from nezha.preprocessor import NezhaPreprocessor

        print("✓ Preprocessor imported successfully")

        from nezha.algorithms import NezhaAlgorithm, run_nezha_analysis

        print("✓ Algorithms imported successfully")

        from nezha.integration import NezhaIntegrator, run_nezha_pipeline

        print("✓ Integration imported successfully")

        return True

    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False


def test_data_structures():
    """Test data structure creation and basic operations."""
    print("\nTesting data structures...")

    try:
        from nezha.data_structures import (
            EnhancedEventPattern,
            PatternSupport,
            ServiceMapping,
            TraceData,
        )

        # Test ServiceMapping
        service_mapping = ServiceMapping.create(["service1", "service2", "service3"])
        assert service_mapping.get_service_id("service1") == 0
        assert service_mapping.get_service_name(0) == "service1"
        print("✓ ServiceMapping works correctly")

        # Test EnhancedEventPattern
        pattern = EnhancedEventPattern(pattern=(1, 2), count=5, depth=1, service=0)
        assert pattern.pattern == (1, 2)
        assert pattern.count == 5
        print("✓ EnhancedEventPattern works correctly")

        # Test TraceData
        trace_data = TraceData(
            trace_id="test_trace",
            enhanced_patterns=[pattern],
            root_service="loadgenerator",
            total_spans=10,
            error_count=0,
            performance_score=1.5,
        )
        assert len(trace_data.enhanced_patterns) == 1
        print("✓ TraceData works correctly")

        # Test PatternSupport
        support = PatternSupport()
        support.add_pattern(pattern)
        sorted_patterns = support.get_sorted_patterns()
        assert len(sorted_patterns) == 1
        print("✓ PatternSupport works correctly")

        return True

    except Exception as e:
        print(f"✗ Data structures test failed: {e}")
        return False


def test_algorithms():
    """Test algorithm components."""
    print("\nTesting algorithms...")

    try:
        from nezha.algorithms import NezhaAlgorithm
        from nezha.data_structures import ServiceMapping

        # Create test data
        service_mapping = ServiceMapping.create(["service1", "service2"])
        algorithm = NezhaAlgorithm(service_mapping)

        # Test suspiciousness scoring
        score = algorithm.calculate_suspiciousness_score(10, 2, min_support=5)
        expected_score = 10 / (10 + 2)
        assert abs(score - expected_score) < 0.001
        print("✓ Suspiciousness scoring works correctly")

        return True

    except Exception as e:
        print(f"✗ Algorithm test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("Running Nezha refactored version tests...")
    print("=" * 50)

    tests = [test_imports, test_data_structures, test_algorithms]

    passed = 0
    total = len(tests)

    for test in tests:
        if test():
            passed += 1

    print("\n" + "=" * 50)
    print(f"Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("✓ All tests passed! Refactoring is working correctly.")
        return 0
    else:
        print("✗ Some tests failed. Please check the implementation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
