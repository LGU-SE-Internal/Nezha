"""
Test the enhanced frequency encoding.
"""

import sys
from pathlib import Path

# Add src to path
current_dir = Path(__file__).parent
src_dir = current_dir / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))


def test_frequency_encoding():
    """Test frequency encoding with real data."""
    print("Testing enhanced frequency encoding...")

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

        # Run the pipeline
        results = run_nezha_pipeline(
            input_folder=input_folder,
            normal_ratio=0.6,
            min_support=3,
            min_score=0.5,
            top_k=5,
            need_logs=True,
        )

        print("✅ Pipeline completed successfully!")
        print(f"📊 Found {len(results['ranked_patterns'])} suspicious patterns")

        # Print top patterns with their frequencies
        for i, pattern in enumerate(results["ranked_patterns"][:3]):
            print(f"\n🔍 Pattern {i + 1}:")
            print(f"   Event pair: {pattern['pattern']}")
            print(f"   Frequency count: {pattern['abnormal_support']}")
            print(f"   Score: {pattern['score']:.3f}")
            print(f"   Depth: {pattern['depth']:.1f}")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_frequency_encoding()
    sys.exit(0 if success else 1)
