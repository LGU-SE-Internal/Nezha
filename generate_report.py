"""
Generate detailed analysis report for Nezha results.

This script analyzes the results from run_analysis.py and provides
detailed insights about the root cause analysis.
"""

import json
import sys
from pathlib import Path

# Add src to path for development
current_dir = Path(__file__).parent
src_dir = current_dir / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))

try:
    from nezha.data_structures import ServiceMapping
    from rcabench_platform.v2.logging import logger
except ImportError as e:
    print(f"Error importing modules: {e}")
    sys.exit(1)


def load_results(results_file: Path) -> dict:
    """Load analysis results from JSON file"""
    with open(results_file, "r") as f:
        return json.load(f)


def create_service_mapping() -> ServiceMapping:
    """Create service mapping for interpretation"""
    services = [
        "loadgenerator",
        "ts-assurance-service",
        "ts-auth-service",
        "ts-basic-service",
        "ts-cancel-service",
        "ts-config-service",
        "ts-consign-price-service",
        "ts-consign-service",
        "ts-contacts-service",
        "ts-food-service",
        "ts-inside-payment-service",
        "ts-order-other-service",
        "ts-order-service",
        "ts-payment-service",
        "ts-preserve-service",
        "ts-price-service",
        "ts-route-plan-service",
        "ts-route-service",
        "ts-seat-service",
        "ts-security-service",
        "ts-station-food-service",
        "ts-station-service",
        "ts-train-food-service",
        "ts-train-service",
        "ts-travel-plan-service",
        "ts-travel-service",
        "ts-travel2-service",
        "ts-ui-dashboard",
        "ts-user-service",
        "ts-verification-code-service",
    ]
    return ServiceMapping.create(services)


def interpret_event_id(event_id: int) -> str:
    """Interpret event ID based on ranges"""
    if 1 <= event_id <= 5000:
        return f"SPAN_START({event_id})"
    elif 5001 <= event_id <= 10000:
        return f"SPAN_END({event_id})"
    elif event_id == 10001:
        return "STATUS_ERROR"
    elif event_id == 10002:
        return "PERF_DEGRADATION"
    elif event_id >= 20001:
        return f"LOG_TEMPLATE({event_id})"
    else:
        return f"UNKNOWN({event_id})"


def analyze_pattern(pattern: list, service_mapping: ServiceMapping) -> dict:
    """Analyze a single pattern and provide interpretation"""
    source_id, target_id = pattern

    analysis = {
        "pattern": pattern,
        "source_event": interpret_event_id(source_id),
        "target_event": interpret_event_id(target_id),
        "interpretation": "",
        "significance": "",
    }

    # Determine pattern type and significance
    if target_id == 10002:  # Performance degradation
        analysis["interpretation"] = "Pattern leading to performance degradation"
        analysis["significance"] = "HIGH - Directly indicates performance issues"
    elif source_id == 10002:  # Performance degradation as source
        analysis["interpretation"] = "Pattern following performance degradation"
        analysis["significance"] = "HIGH - Shows consequences of performance issues"
    elif target_id == 10001:  # Status error
        analysis["interpretation"] = "Pattern leading to status error"
        analysis["significance"] = "HIGH - Directly indicates error conditions"
    elif source_id == 10001:  # Status error as source
        analysis["interpretation"] = "Pattern following status error"
        analysis["significance"] = "HIGH - Shows consequences of errors"
    elif source_id >= 20001 and target_id >= 20001:  # Log to log
        analysis["interpretation"] = "Log sequence pattern"
        analysis["significance"] = "MEDIUM - May indicate problematic log sequences"
    elif source_id >= 20001 and 5001 <= target_id <= 10000:  # Log to span end
        analysis["interpretation"] = "Log event occurring near span completion"
        analysis["significance"] = "MEDIUM - May indicate logging during span closure"
    elif 1 <= source_id <= 5000 and target_id >= 20001:  # Span start to log
        analysis["interpretation"] = "Log event following span start"
        analysis["significance"] = "MEDIUM - May indicate problematic startup logging"
    else:
        analysis["interpretation"] = "General event transition"
        analysis["significance"] = "LOW - Normal event flow pattern"

    return analysis


def generate_report(results_file: Path):
    """Generate detailed analysis report"""

    if not results_file.exists():
        logger.error(f"Results file not found: {results_file}")
        return

    # Load results
    results = load_results(results_file)
    service_mapping = create_service_mapping()

    logger.info("📋 DETAILED NEZHA ANALYSIS REPORT")
    logger.info("=" * 60)

    # Metadata
    metadata = results["metadata"]
    logger.info("📊 EXPERIMENT METADATA")
    logger.info("-" * 30)
    logger.info(f"Data folder: {metadata['input_folder']}")
    logger.info(f"Total traces: {metadata['total_traces']}")
    logger.info(f"Normal traces: {metadata['normal_traces']}")
    logger.info(f"Abnormal traces: {metadata['abnormal_traces']}")
    logger.info(f"Analysis time: {metadata['export_time']}")
    logger.info("")

    # Analysis results summary
    analysis_results = results["results"]
    patterns = analysis_results["ranked_patterns"]

    logger.info("📈 ANALYSIS SUMMARY")
    logger.info("-" * 30)
    logger.info(f"Suspicious patterns found: {len(patterns)}")
    logger.info(
        f"Total abnormal patterns: {analysis_results['total_abnormal_patterns']}"
    )
    logger.info(f"Total normal patterns: {analysis_results['total_normal_patterns']}")
    logger.info(f"Processing time: {analysis_results['processing_time_seconds']:.2f}s")
    logger.info("")

    # Pattern analysis
    logger.info("🔍 DETAILED PATTERN ANALYSIS")
    logger.info("-" * 30)

    high_priority_patterns = []
    medium_priority_patterns = []

    for i, pattern_data in enumerate(patterns[:15]):  # Analyze top 15
        pattern = pattern_data["pattern"]
        analysis = analyze_pattern(pattern, service_mapping)

        # Get service names
        service_names = []
        for service_id in pattern_data["services"]:
            if service_id == -1:
                service_names.append("UNKNOWN")
            else:
                service_names.append(service_mapping.get_service_name(service_id))

        logger.info(f"Pattern {i + 1}: {pattern}")
        logger.info(
            f"  Event Flow: {analysis['source_event']} → {analysis['target_event']}"
        )
        logger.info(f"  Interpretation: {analysis['interpretation']}")
        logger.info(f"  Significance: {analysis['significance']}")
        logger.info(f"  Score: {pattern_data['score']:.3f}")
        logger.info(
            f"  Support: {pattern_data['abnormal_support']} abnormal, {pattern_data['normal_support']} normal"
        )
        logger.info(f"  Depth: {pattern_data['depth']:.1f}")
        logger.info(f"  Services: {service_names}")
        logger.info("")

        if analysis["significance"] == "HIGH":
            high_priority_patterns.append((pattern_data, analysis))
        elif analysis["significance"] == "MEDIUM":
            medium_priority_patterns.append((pattern_data, analysis))

    # Service analysis
    logger.info("🏢 SERVICE IMPACT ANALYSIS")
    logger.info("-" * 30)

    service_impact = {}
    for pattern_data in patterns:
        for service_id in pattern_data["services"]:
            if service_id not in service_impact:
                service_impact[service_id] = {
                    "pattern_count": 0,
                    "total_score": 0.0,
                    "max_score": 0.0,
                    "patterns": [],
                }
            service_impact[service_id]["pattern_count"] += 1
            service_impact[service_id]["total_score"] += pattern_data["score"]
            service_impact[service_id]["max_score"] = max(
                service_impact[service_id]["max_score"], pattern_data["score"]
            )
            service_impact[service_id]["patterns"].append(pattern_data["pattern"])

    # Sort services by impact
    sorted_services = sorted(
        service_impact.items(),
        key=lambda x: (x[1]["pattern_count"], x[1]["total_score"]),
        reverse=True,
    )

    for service_id, impact in sorted_services[:10]:  # Top 10 services
        if service_id == -1:
            service_name = "UNKNOWN/MULTIPLE"
        else:
            service_name = service_mapping.get_service_name(service_id)

        avg_score = impact["total_score"] / impact["pattern_count"]
        logger.info(f"{service_name}:")
        logger.info(f"  Suspicious patterns: {impact['pattern_count']}")
        logger.info(f"  Average score: {avg_score:.3f}")
        logger.info(f"  Max score: {impact['max_score']:.3f}")
        logger.info("")

    # Key insights
    logger.info("💡 KEY INSIGHTS")
    logger.info("-" * 30)

    # Check for preserve service issues
    preserve_service_id = service_mapping.get_service_id("ts-preserve-service")
    if preserve_service_id in service_impact:
        logger.info(
            "🔴 CRITICAL: ts-preserve-service is involved in suspicious patterns!"
        )
        logger.info(
            "   This aligns with the experiment name suggesting preserve service issues."
        )
        logger.info("")

    # Performance degradation analysis
    perf_patterns = [p for p in patterns if 10002 in p["pattern"]]
    if perf_patterns:
        logger.info(
            f"⚠️  Performance degradation detected in {len(perf_patterns)} patterns"
        )
        logger.info(
            "   This suggests system performance issues during the abnormal phase."
        )
        logger.info("")

    # Error patterns analysis
    error_patterns = [p for p in patterns if 10001 in p["pattern"]]
    if error_patterns:
        logger.info(f"❌ Error conditions detected in {len(error_patterns)} patterns")
        logger.info("   This suggests error propagation during the abnormal phase.")
        logger.info("")

    # High confidence patterns
    if high_priority_patterns:
        logger.info(
            f"🎯 {len(high_priority_patterns)} high-priority patterns identified"
        )
        logger.info(
            "   These patterns directly indicate critical issues and should be investigated first."
        )
        logger.info("")

    logger.info("📝 RECOMMENDATIONS")
    logger.info("-" * 30)
    logger.info("1. Focus on high-priority patterns (marked as HIGH significance)")
    logger.info("2. Investigate ts-preserve-service issues if highlighted")
    logger.info("3. Check performance degradation patterns for bottlenecks")
    logger.info("4. Analyze error propagation chains")
    logger.info("5. Compare pattern depths to understand call chain impacts")
    logger.info("")

    logger.info("✅ Report generation completed!")


def main():
    """Main function"""
    results_file = Path("D:/workspace/Nezha/results_real_data.json")

    if not results_file.exists():
        logger.error(
            "Results file not found. Please run 'python run_analysis.py' first."
        )
        return 1

    generate_report(results_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
