"""
Enhanced analysis with log template content interpretation.
"""

import json
import sys
from pathlib import Path

# Add src to path
current_dir = Path(__file__).parent
src_dir = current_dir / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))

import polars as pl


def analyze_log_templates(input_folder: Path, event_pairs: list):
    """Analyze log template content for given event pairs."""
    print("\n🔍 Analyzing log template content...")

    # Load logs to get template mapping
    try:
        normal_logs = pl.read_parquet(input_folder / "normal_logs.parquet")
        abnormal_logs = pl.read_parquet(input_folder / "abnormal_logs.parquet")
        all_logs = pl.concat([normal_logs, abnormal_logs])

        print(f"📋 Loaded {len(all_logs)} log records")

        # Create template mapping
        template_mapping = {}
        if (
            "attr.template_id" in all_logs.columns
            and "attr.log_template" in all_logs.columns
        ):
            templates = all_logs.select(
                ["attr.template_id", "attr.log_template"]
            ).unique()
            for row in templates.iter_rows(named=True):
                template_id = row["attr.template_id"]
                template_content = row["attr.log_template"]
                if template_id and template_content:
                    template_mapping[template_id] = template_content

        print(f"📝 Found {len(template_mapping)} unique log templates")

        return template_mapping

    except Exception as e:
        print(f"❌ Failed to load log templates: {e}")
        return {}


def get_event_description(event_id: int, template_mapping: dict, id_manager=None):
    """Get human-readable description of an event."""
    # If we have the id_manager, use it for exact mapping
    if id_manager:
        # Check log templates
        for original_id, encoded_id in id_manager.log_template_to_id.items():
            if encoded_id == event_id:
                if str(original_id) in template_mapping:
                    content = template_mapping[str(original_id)]
                    return f"LOG_TEMPLATE: {content[:100]}..."
                else:
                    return f"LOG_TEMPLATE (Original ID: {original_id}, Encoded: {event_id})"

        # Check span starts
        for span_name, encoded_id in id_manager.span_start_to_id.items():
            if encoded_id == event_id:
                return f"SPAN_START: {span_name}"

        # Check span ends
        for span_name, encoded_id in id_manager.span_end_to_id.items():
            if encoded_id == event_id:
                return f"SPAN_END: {span_name}"

    # Fallback to range-based detection
    SPAN_START_BEGIN = 1
    SPAN_START_END = 5000
    SPAN_END_BEGIN = 5001
    SPAN_END_END = 10000
    SPECIAL_EVENT_START = 10001
    LOG_TEMPLATE_START = 20001

    if SPAN_START_BEGIN <= event_id <= SPAN_START_END:
        return f"SPAN_START (ID: {event_id})"
    elif SPAN_END_BEGIN <= event_id <= SPAN_END_END:
        return f"SPAN_END (ID: {event_id})"
    elif SPECIAL_EVENT_START <= event_id < LOG_TEMPLATE_START:
        return f"SPECIAL_EVENT (ID: {event_id})"
    elif event_id >= LOG_TEMPLATE_START:
        return f"LOG_TEMPLATE (ID: {event_id})"
    else:
        return f"UNKNOWN (ID: {event_id})"


def enhanced_analysis():
    """Run enhanced analysis with log template interpretation."""
    print("🚀 Running enhanced Nezha analysis...")

    try:
        from nezha.integration import run_nezha_pipeline

        # Test with real data
        input_folder = Path(
            r"D:\workspace\Nezha\test\ts0-ts-preserve-service-request-replace-method-cw7ndj"
        )

        if not input_folder.exists():
            print(f"❌ Data folder not found: {input_folder}")
            return False

        print(f"📁 Using data folder: {input_folder}")

        # Load log templates first
        template_mapping = analyze_log_templates(input_folder, [])

        # Run the pipeline and get ID manager for accurate mapping
        results, id_manager = run_nezha_pipeline(
            input_folder=input_folder,
            normal_ratio=0.6,
            min_support=3,
            min_score=0.5,
            top_k=10,
            need_logs=True,
            return_id_manager=True,
        )

        print("\n" + "=" * 80)
        print("📊 ENHANCED ANALYSIS RESULTS")
        print("=" * 80)

        print(f"🎯 Found {len(results['ranked_patterns'])} suspicious patterns")
        print(f"⏱️ Processing time: {results['processing_time_seconds']:.2f}s")

        print("\n🔥 TOP SUSPICIOUS PATTERNS:")
        print("-" * 80)

        for i, pattern in enumerate(results["ranked_patterns"][:5]):
            source_id, target_id = pattern["pattern"]

            print(f"\n📍 PATTERN #{i + 1}")
            print(f"   🔗 Event Transition: {source_id} → {target_id}")
            print(f"   📊 Suspiciousness Score: {pattern['score']:.3f}")
            print(f"   📈 Abnormal Support: {pattern['abnormal_support']}")
            print(f"   📉 Normal Support: {pattern['normal_support']}")
            print(f"   📏 Average Depth: {pattern['depth']:.1f}")
            print(f"   🏢 Services: {pattern['services']}")

            # Decode event descriptions
            source_desc = get_event_description(source_id, template_mapping, id_manager)
            target_desc = get_event_description(target_id, template_mapping, id_manager)

            print(f"   🔵 Source Event: {source_desc}")
            print(f"   🔴 Target Event: {target_desc}")

            # Pattern interpretation
            if source_id >= 20001 and target_id >= 20001:
                print(
                    "   💭 Pattern Type: Log-to-Log transition (potential error cascade)"
                )
            elif source_id >= 20001 and 5001 <= target_id <= 10000:
                print(
                    "   💭 Pattern Type: Log-to-Span-End (log before span completion)"
                )
            elif 1 <= source_id <= 5000 and target_id >= 20001:
                print("   💭 Pattern Type: Span-Start-to-Log (log after span start)")
            elif 1 <= source_id <= 5000 and 5001 <= target_id <= 10000:
                print("   💭 Pattern Type: Span lifecycle (start to end)")
            else:
                print("   💭 Pattern Type: Complex transition")

        # Save detailed results
        output_file = Path("enhanced_analysis_results.json")
        with open(output_file, "w") as f:
            # Add template mapping to results for future reference
            enhanced_results = results.copy()
            enhanced_results["template_mapping"] = template_mapping
            enhanced_results["analysis_metadata"] = {
                "input_folder": str(input_folder),
                "total_templates": len(template_mapping),
                "analysis_type": "enhanced_with_templates",
            }
            json.dump(enhanced_results, f, indent=2, default=str)

        print(f"\n💾 Detailed results saved to: {output_file}")

        return True

    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = enhanced_analysis()
    sys.exit(0 if success else 1)
