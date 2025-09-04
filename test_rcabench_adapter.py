#!/usr/bin/env python3
"""
Test script for Nezha rcabench_platform adapter

Tests the NezhaAlgorithm class to ensure it correctly implements
the rcabench_platform Algorithm interface.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

# Add src to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from nezha.rcabench_adapter import NezhaAlgorithm


@dataclass
class MockAlgorithmArgs:
    """Mock AlgorithmArgs for testing"""

    input_folder: str
    normal_ratio: float = 0.6
    min_support: int = 3
    min_score: float = 0.5
    top_k: int = 20


def test_nezha_adapter():
    """Test the Nezha rcabench adapter"""
    print("🧪 测试Nezha rcabench适配器...")

    # Initialize algorithm
    nezha_algo = NezhaAlgorithm()

    # Check CPU requirements
    cpu_count = nezha_algo.needs_cpu_count()
    print(f"📊 推荐CPU核心数: {cpu_count}")

    # Set up test data path
    test_data_path = Path(
        r"D:\workspace\Nezha\test\ts0-ts-preserve-service-request-replace-method-cw7ndj"
    )

    if not test_data_path.exists():
        print(f"❌ 测试数据路径不存在: {test_data_path}")
        return False

    # Create mock arguments
    args = MockAlgorithmArgs(
        input_folder=str(test_data_path),
        normal_ratio=0.6,
        min_support=3,
        min_score=0.5,
        top_k=20,
    )

    print(f"📁 使用测试数据: {test_data_path}")
    print(f"⚙️  参数: normal_ratio={args.normal_ratio}, min_support={args.min_support}")

    try:
        # Execute algorithm
        print("\n🚀 执行Nezha算法...")
        answers = nezha_algo(args)

        if not answers:
            print("❌ 算法未返回结果")
            return False

        print(f"\n✅ 算法执行成功，返回 {len(answers)} 个服务排名")
        print("\n🏆 服务排名结果:")
        print("-" * 60)

        for answer in answers:
            print(f"排名 {answer.rank:2d}: {answer.name}")
            if hasattr(answer, "score") and answer.score is not None:
                print(f"         评分: {answer.score:.3f}")

        # Validate results
        print("\n🔍 结果验证:")
        print(f"   ✓ 返回答案数量: {len(answers)}")
        print(
            f"   ✓ 所有答案级别为 'service': {all(a.level == 'service' for a in answers)}"
        )
        print(
            f"   ✓ 排名连续性: {[a.rank for a in answers] == list(range(1, len(answers) + 1))}"
        )

        # Show top 5 services with details
        print("\n🎯 前5名根因服务:")
        for i, answer in enumerate(answers[:5], 1):
            score_info = (
                f" (评分: {answer.score:.3f})"
                if hasattr(answer, "score") and answer.score
                else ""
            )
            print(f"   {i}. {answer.name}{score_info}")

        return True

    except Exception as e:
        print(f"❌ 算法执行失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def benchmark_performance():
    """Benchmark algorithm performance"""
    print("\n⚡ 性能基准测试...")

    import time

    nezha_algo = NezhaAlgorithm()
    test_data_path = Path(
        r"D:\workspace\Nezha\test\ts0-ts-preserve-service-request-replace-method-cw7ndj"
    )

    if not test_data_path.exists():
        print("❌ 测试数据不存在，跳过性能测试")
        return

    args = MockAlgorithmArgs(input_folder=str(test_data_path))

    # Warm up run
    print("🔥 预热运行...")
    _ = nezha_algo(args)

    # Benchmark runs
    times = []
    for i in range(3):
        print(f"📊 基准测试运行 {i + 1}/3...")
        start_time = time.time()
        answers = nezha_algo(args)
        end_time = time.time()

        execution_time = end_time - start_time
        times.append(execution_time)
        print(f"   执行时间: {execution_time:.2f}秒, 结果数: {len(answers)}")

    avg_time = sum(times) / len(times)
    print("\n📈 性能统计:")
    print(f"   平均执行时间: {avg_time:.2f}秒")
    print(f"   最快执行时间: {min(times):.2f}秒")
    print(f"   最慢执行时间: {max(times):.2f}秒")


def main():
    """主函数"""
    print("🎯 Nezha rcabench适配器测试")
    print("=" * 50)

    # Test basic functionality
    success = test_nezha_adapter()

    if success:
        # Run performance benchmark
        benchmark_performance()
        print("\n🎉 所有测试通过！")
        return True
    else:
        print("\n💥 测试失败！")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
