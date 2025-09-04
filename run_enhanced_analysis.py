#!/usr/bin/env python3
"""
Enhanced Nezha Analysis Script

运行完整的增强版Nezha根因分析，包括：
1. 日志模板内容解析
2. 事件转换模式分析
3. 可疑模式排序和解释
4. 根因假设生成
"""

import json
import time
from pathlib import Path
from typing import Dict, List

import polars as pl


def load_log_templates(input_folder: Path) -> Dict[str, str]:
    """加载日志模板映射"""
    try:
        print("🔍 分析日志模板内容...")

        # 加载所有日志数据
        log_files = []
        for pattern in ["normal_logs.parquet", "abnormal_logs.parquet"]:
            log_file = input_folder / pattern
            if log_file.exists():
                log_files.append(log_file)

        if not log_files:
            print("❌ 未找到日志文件")
            return {}

        # 合并所有日志
        all_logs = []
        for log_file in log_files:
            logs = pl.read_parquet(log_file)
            all_logs.append(logs)

        combined_logs = pl.concat(all_logs)
        print(f"📋 加载了 {len(combined_logs)} 条日志记录")

        # 提取模板映射
        template_mapping = {}
        if (
            "attr.template_id" in combined_logs.columns
            and "attr.log_template" in combined_logs.columns
        ):
            # 获取唯一的模板ID和内容映射
            unique_templates = (
                combined_logs.select(["attr.template_id", "attr.log_template"])
                .unique()
                .filter(
                    pl.col("attr.template_id").is_not_null()
                    & pl.col("attr.log_template").is_not_null()
                )
            )

            for row in unique_templates.iter_rows(named=True):
                template_id = str(row["attr.template_id"])
                template_content = str(row["attr.log_template"])
                template_mapping[template_id] = template_content

        print(f"📝 找到 {len(template_mapping)} 个唯一日志模板")
        return template_mapping

    except Exception as e:
        print(f"❌ 加载日志模板失败: {e}")
        return {}


def get_event_description(
    event_id: int, template_mapping: Dict[str, str], id_manager=None
) -> str:
    """获取事件的可读描述"""
    if id_manager:
        # 检查日志模板
        for template_id, encoded_id in id_manager.log_template_to_id.items():
            if encoded_id == event_id:
                if str(template_id) in template_mapping:
                    content = template_mapping[str(template_id)]
                    return f"LOG: {content}"
                else:
                    return f"LOG_TEMPLATE (原始ID: {template_id}, 编码ID: {event_id})"

        # 检查Span开始事件
        for span_name, encoded_id in id_manager.span_start_to_id.items():
            if encoded_id == event_id:
                return f"SPAN_START: {span_name}"

        # 检查Span结束事件
        for span_name, encoded_id in id_manager.span_end_to_id.items():
            if encoded_id == event_id:
                return f"SPAN_END: {span_name}"

    # 使用范围检测作为备选方案
    if 1 <= event_id <= 5000:
        return f"SPAN_START (ID: {event_id})"
    elif 5001 <= event_id <= 10000:
        return f"SPAN_END (ID: {event_id})"
    elif 10001 <= event_id < 20001:
        return f"SPECIAL_EVENT (ID: {event_id})"
    elif event_id >= 20001:
        return f"LOG_TEMPLATE (ID: {event_id})"
    else:
        return f"未知事件 (ID: {event_id})"


def classify_pattern_type(source_desc: str, target_desc: str) -> str:
    """分类模式类型"""
    if source_desc.startswith("LOG") and target_desc.startswith("LOG"):
        return "日志到日志转换 (可能的错误级联)"
    elif source_desc.startswith("LOG") and target_desc.startswith("SPAN_END"):
        return "日志到Span结束 (日志在span完成前)"
    elif source_desc.startswith("SPAN_START") and target_desc.startswith("LOG"):
        return "Span开始到日志 (span启动后的日志)"
    elif source_desc.startswith("SPAN_START") and target_desc.startswith("SPAN_END"):
        return "Span生命周期 (开始到结束)"
    elif source_desc.startswith("SPECIAL_EVENT"):
        return "特殊事件转换"
    else:
        return "复杂转换"


def analyze_root_causes(
    patterns: List[Dict], template_mapping: Dict[str, str], id_manager=None
) -> None:
    """分析根因并生成假设"""
    print("\n🎯 详细根因分析")
    print("=" * 80)

    service_issues = {}
    log_patterns = []
    error_cascades = []
    timing_issues = []

    for i, pattern_info in enumerate(patterns[:10], 1):
        pattern = pattern_info["pattern"]
        source_id, target_id = pattern[0], pattern[1]

        source_desc = get_event_description(source_id, template_mapping, id_manager)
        target_desc = get_event_description(target_id, template_mapping, id_manager)
        pattern_type = classify_pattern_type(source_desc, target_desc)

        score = pattern_info["score"]
        abnormal_support = pattern_info["abnormal_support"]
        services = pattern_info.get("services", [])

        print(f"\n📍 模式 #{i} (可疑度: {score:.3f})")
        print(f"   🔗 事件转换: {source_id} → {target_id}")
        print(f"   📊 异常支持度: {abnormal_support}")
        print(f"   🏢 涉及服务: {services}")
        print(f"   🔵 源事件: {source_desc}")
        print(f"   🔴 目标事件: {target_desc}")
        print(f"   💭 模式类型: {pattern_type}")

        # 收集分析数据
        for service_id in services:
            if service_id not in service_issues:
                service_issues[service_id] = []
            service_issues[service_id].append(
                {
                    "pattern": f"{source_id}→{target_id}",
                    "type": pattern_type,
                    "score": score,
                    "support": abnormal_support,
                }
            )

        if "日志到日志" in pattern_type:
            error_cascades.append(pattern_info)
        elif "日志到Span" in pattern_type or "Span开始到日志" in pattern_type:
            timing_issues.append(pattern_info)

        if source_desc.startswith("LOG"):
            log_patterns.append((source_desc, abnormal_support))

    # 生成根因假设
    print("\n🔮 根因假设生成:")
    print("-" * 60)

    if error_cascades:
        print(f"1. 🔄 错误级联问题 ({len(error_cascades)} 个模式)")
        print("   - 日志事件之间的异常转换表明存在错误传播")
        print("   - 建议检查异常处理和错误恢复机制")

    if timing_issues:
        print(f"2. ⏰ 时序同步问题 ({len(timing_issues)} 个模式)")
        print("   - Span和日志事件的时序异常")
        print("   - 建议检查服务间的同步机制和超时设置")

    if service_issues:
        print("3. 🏢 服务特定问题:")
        for service_id, issues in service_issues.items():
            if len(issues) >= 2:  # 服务有多个问题
                print(f"   - 服务 {service_id}: {len(issues)} 个可疑模式")
                issue_types = set(issue["type"] for issue in issues)
                print(f"     类型: {', '.join(issue_types)}")

    # 频繁出现的日志模式
    if log_patterns:
        freq_logs = {}
        for log_desc, support in log_patterns:
            freq_logs[log_desc] = freq_logs.get(log_desc, 0) + support

        if freq_logs:
            print("4. 📝 高频异常日志:")
            sorted_logs = sorted(freq_logs.items(), key=lambda x: x[1], reverse=True)
            for log_desc, total_support in sorted_logs[:3]:
                print(f"   - {log_desc[:100]}... (支持度: {total_support})")


def main():
    """主函数"""
    print("🚀 启动增强版Nezha根因分析...")

    try:
        # 添加src目录到Python路径
        import sys

        src_path = Path(__file__).parent / "src"
        if str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))

        # 导入Nezha组件
        from nezha.integration import run_nezha_pipeline

        # 设置数据路径
        input_folder = Path(
            r"D:\workspace\Nezha\test\ts0-ts-preserve-service-request-replace-method-cw7ndj"
        )

        if not input_folder.exists():
            print(f"❌ 数据文件夹不存在: {input_folder}")
            return False

        print(f"📁 使用数据文件夹: {input_folder}")

        # 加载日志模板映射
        template_mapping = load_log_templates(input_folder)

        # 运行Nezha分析流水线
        print("\n🔄 运行Nezha分析流水线...")
        start_time = time.time()

        results, id_manager = run_nezha_pipeline(
            input_folder=input_folder,
            normal_ratio=0.6,  # 60%作为正常数据
            min_support=3,  # 最小支持度阈值
            min_score=0.5,  # 最小可疑度分数
            top_k=10,  # 返回前10个模式
            need_logs=True,  # 需要日志数据
            return_id_manager=True,  # 返回ID管理器
        )

        analysis_time = time.time() - start_time

        if not results or not results.get("ranked_patterns"):
            print("❌ Nezha分析未返回结果")
            return False

        # 显示分析结果
        patterns = results["ranked_patterns"]
        print(f"\n📊 分析完成 (耗时: {analysis_time:.2f}秒)")
        print(f"🎯 找到 {len(patterns)} 个可疑模式")
        print(f"⚡ 总处理时间: {results.get('processing_time_seconds', 0):.2f}秒")

        # 执行详细根因分析
        analyze_root_causes(patterns, template_mapping, id_manager)

        # 保存结果
        output_file = "enhanced_nezha_results.json"
        with open(output_file, "w", encoding="utf-8") as f:
            results["template_mapping"] = template_mapping
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"\n💾 详细结果已保存到: {output_file}")
        print("✅ 增强分析完成")

        return True

    except Exception as e:
        print(f"❌ 分析过程中出现错误: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    if not success:
        print("\n💥 分析失败，请检查错误信息")
        exit(1)
    else:
        print("\n🎉 分析成功完成！")
