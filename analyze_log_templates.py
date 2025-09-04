#!/usr/bin/env python3
"""
日志模板解析器 - 查看Nezha分析结果中的日志模板实际内容
"""

import json
import sys
from pathlib import Path

import polars as pl

# Add src to path
current_dir = Path(__file__).parent
src_dir = current_dir / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))

from rcabench_platform.v2.logging import logger


def load_log_templates(data_folder: Path):
    """从日志数据中加载模板映射"""
    logger.info("加载日志模板...")

    template_mapping = {}

    # 加载正常和异常日志
    for log_file in ["normal_logs.parquet", "abnormal_logs.parquet"]:
        log_path = data_folder / log_file
        if log_path.exists():
            logs_df = pl.read_parquet(log_path)

            # 获取模板ID到模板内容的映射
            template_data = (
                logs_df.select(
                    ["attr.template_id", "attr.log_template", "service_name"]
                )
                .unique()
                .sort("attr.template_id")
            )

            for row in template_data.iter_rows(named=True):
                template_id = row["attr.template_id"]
                template_content = row["attr.log_template"]
                service_name = row["service_name"]

                if template_id not in template_mapping:
                    template_mapping[template_id] = {
                        "template": template_content,
                        "services": set(),
                    }
                template_mapping[template_id]["services"].add(service_name)

    # 转换services为列表以便JSON序列化
    for template_id in template_mapping:
        template_mapping[template_id]["services"] = list(
            template_mapping[template_id]["services"]
        )

    logger.info(f"加载了 {len(template_mapping)} 个日志模板")
    return template_mapping


def analyze_log_templates_in_results(results_file: Path, template_mapping: dict):
    """分析结果中的日志模板"""

    with open(results_file, "r") as f:
        results = json.load(f)

    logger.info("分析结果中的日志模板...")

    # 从rcabench_platform的EventIDManager中得知日志模板的ID范围是从20001开始
    LOG_TEMPLATE_START = 20001

    log_template_patterns = []

    for pattern_info in results["results"]["ranked_patterns"]:
        pattern = pattern_info["pattern"]
        source_id, target_id = pattern

        # 检查是否涉及日志模板事件
        source_is_log = source_id >= LOG_TEMPLATE_START
        target_is_log = target_id >= LOG_TEMPLATE_START

        if source_is_log or target_is_log:
            pattern_analysis = {
                "pattern": pattern,
                "rank": pattern_info["rank"],
                "score": pattern_info["score"],
                "abnormal_support": pattern_info["abnormal_support"],
                "normal_support": pattern_info["normal_support"],
                "depth": pattern_info["depth"],
                "services": pattern_info["services"],
                "source_type": "log_template"
                if source_is_log
                else get_event_type(source_id),
                "target_type": "log_template"
                if target_is_log
                else get_event_type(target_id),
                "source_template": None,
                "target_template": None,
            }

            # 查找对应的模板内容
            if source_is_log:
                # 日志模板ID从LOG_TEMPLATE_START开始编号
                template_id = source_id - LOG_TEMPLATE_START + 1  # 假设从1开始编号
                if template_id in template_mapping:
                    pattern_analysis["source_template"] = template_mapping[template_id]

            if target_is_log:
                template_id = target_id - LOG_TEMPLATE_START + 1
                if template_id in template_mapping:
                    pattern_analysis["target_template"] = template_mapping[template_id]

            log_template_patterns.append(pattern_analysis)

    return log_template_patterns


def get_event_type(event_id: int) -> str:
    """根据事件ID确定事件类型"""
    if 1 <= event_id <= 5000:
        return "span_start"
    elif 5001 <= event_id <= 10000:
        return "span_end"
    elif 10001 <= event_id <= 20000:
        return "special_event"
    elif event_id >= 20001:
        return "log_template"
    else:
        return "unknown"


def print_log_template_analysis(log_template_patterns: list, template_mapping: dict):
    """打印日志模板分析结果"""

    print("=" * 80)
    print("日志模板分析报告")
    print("=" * 80)

    if not log_template_patterns:
        print("在Top可疑模式中未发现涉及日志模板的模式")
        return

    print(f"发现 {len(log_template_patterns)} 个涉及日志模板的可疑模式\n")

    for i, pattern_info in enumerate(log_template_patterns):
        print(f"--- 模式 {i + 1} (排名 #{pattern_info['rank']}) ---")
        print(f"模式: {pattern_info['pattern']}")
        print(f"可疑度评分: {pattern_info['score']:.3f}")
        print(f"异常支持度: {pattern_info['abnormal_support']}")
        print(f"正常支持度: {pattern_info['normal_support']}")
        print(f"平均深度: {pattern_info['depth']:.1f}")
        print(f"涉及服务: {pattern_info['services']}")
        print(f"源事件类型: {pattern_info['source_type']}")
        print(f"目标事件类型: {pattern_info['target_type']}")

        if pattern_info["source_template"]:
            print("\n源日志模板:")
            print(f"  内容: {pattern_info['source_template']['template']}")
            print(f"  服务: {pattern_info['source_template']['services']}")

        if pattern_info["target_template"]:
            print("\n目标日志模板:")
            print(f"  内容: {pattern_info['target_template']['template']}")
            print(f"  服务: {pattern_info['target_template']['services']}")

        print()

    # 显示所有模板的统计
    print("\n" + "=" * 60)
    print("所有日志模板统计")
    print("=" * 60)

    print(f"总共发现 {len(template_mapping)} 个不同的日志模板")

    # 按服务分组显示模板
    service_templates = {}
    for template_id, template_info in template_mapping.items():
        for service in template_info["services"]:
            if service not in service_templates:
                service_templates[service] = []
            service_templates[service].append(
                {"id": template_id, "template": template_info["template"]}
            )

    print("\n按服务分组的模板数量:")
    for service, templates in sorted(service_templates.items()):
        print(f"  {service}: {len(templates)} 个模板")


def main():
    """主函数"""
    data_folder = Path(
        "D:/workspace/Nezha/test/ts0-ts-preserve-service-request-replace-method-cw7ndj"
    )
    results_file = Path("D:/workspace/Nezha/analysis_results.json")

    if not data_folder.exists():
        logger.error(f"数据文件夹不存在: {data_folder}")
        return 1

    if not results_file.exists():
        logger.error(f"分析结果文件不存在: {results_file}")
        logger.info("请先运行 analyze_real_data.py 生成分析结果")
        return 1

    try:
        # 加载日志模板
        template_mapping = load_log_templates(data_folder)

        # 分析结果中的日志模板
        log_template_patterns = analyze_log_templates_in_results(
            results_file, template_mapping
        )

        # 打印分析结果
        print_log_template_analysis(log_template_patterns, template_mapping)

        # 保存详细的模板映射
        template_output = Path("log_templates.json")
        with open(template_output, "w", encoding="utf-8") as f:
            json.dump(template_mapping, f, indent=2, ensure_ascii=False)
        logger.info(f"日志模板映射已保存到: {template_output}")

        return 0

    except Exception as e:
        logger.error(f"分析失败: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
