#!/usr/bin/env python3
"""
完整数据分析脚本 - 处理所有trace，不进行采样
"""

import multiprocessing
import os
import sys
import time
from pathlib import Path

# 将项目根目录添加到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入必要的模块
from data_loaders import LogLoader
from src.nezha import generate_event_graph, get_events_within_trace_parquet
from src.nezha.alarm_detector import AlarmDetector
from src.nezha.log_processor import load_trace_parquet
from src.nezha.metric_processor import MetricProcessor
from src.nezha.utils import timeit


def full_analysis(
    data_dir="D:/workspace/Nezha/data",
    output_dir="D:/workspace/Nezha/results/full_analysis",
    ns="ts",
    min_score=0.67,
    topk=10,
):
    """
    完整分析所有数据，不进行采样

    Args:
        data_dir: 数据目录路径
        output_dir: 结果输出目录
        ns: 命名空间 ("ts" 或 "hipster")
        min_score: 最小分数阈值
        topk: 返回的前K个结果
    """
    start_time = time.time()
    print(f"\n{'=' * 20} 开始完整数据分析 {'=' * 20}")
    print(f"命名空间: {ns}")
    print("处理所有trace数据（无采样）")

    # 创建输出目录
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # 第1步: 预处理日志
    print(f"\n{'=' * 10} 第1步: 预处理日志 {'=' * 10}")

    # 使用LogLoader进行日志预处理
    with multiprocessing.Pool() as pool:
        log_loader = LogLoader(data_dir=data_dir)
        normal_logs, abnormal_logs = log_loader.load(pool)
        print(
            f"预处理完成: 正常阶段 {len(normal_logs)} 条日志, 异常阶段 {len(abnormal_logs)} 条日志"
        )

    # 第2步: 处理告警
    print(f"\n{'=' * 10} 第2步: 处理告警 {'=' * 10}")
    # 加载指标数据
    metric_processor = MetricProcessor(data_dir=data_dir)
    normal_metrics = metric_processor.load_metrics(phase="normal")
    abnormal_metrics = metric_processor.load_metrics(phase="abnormal")
    print(f"正常阶段指标: {len(normal_metrics)} 条记录")
    print(f"异常阶段指标: {len(abnormal_metrics)} 条记录")

    # 计算阈值
    print("从正常阶段指标计算阈值...")
    thresholds = metric_processor.calculate_thresholds(
        normal_metrics, std_multiplier=3.0
    )

    # 检测告警
    print("检测异常阶段指标的告警...")
    alarm_detector = AlarmDetector()
    alarm_detector.thresholds = thresholds
    alarms = alarm_detector.detect_alarms(abnormal_metrics)
    print(f"检测到 {len(alarms)} 个告警")

    # 第3步: 构建所有正常阶段事件图
    print(f"\n{'=' * 10} 第3步: 构建所有正常阶段事件图 {'=' * 10}")
    normal_trace_file = os.path.join(data_dir, "normal_traces.parquet")
    normal_event_graphs = process_all_traces(
        trace_file=normal_trace_file,
        logs_df=normal_logs,
        alarm_list=[],  # 正常阶段没有告警
        ns=ns,
    )
    print(f"生成了 {len(normal_event_graphs)} 个正常阶段事件图")

    # 第4步: 构建所有异常阶段事件图
    print(f"\n{'=' * 10} 第4步: 构建所有异常阶段事件图 {'=' * 10}")
    abnormal_trace_file = os.path.join(data_dir, "abnormal_traces.parquet")
    abnormal_event_graphs = process_all_traces(
        trace_file=abnormal_trace_file, logs_df=abnormal_logs, alarm_list=alarms, ns=ns
    )
    print(f"生成了 {len(abnormal_event_graphs)} 个异常阶段事件图")

    # 第5步: 直接进行模式分析和排序
    print(f"\n{'=' * 10} 第5步: 直接进行模式分析和排序 {'=' * 10}")

    # 直接计算模式支持度
    normal_pattern_dict = get_pattern_support(normal_event_graphs)
    print(f"获取到 {len(normal_pattern_dict)} 个正常模式")

    abnormal_pattern_dict = get_pattern_support(abnormal_event_graphs)
    print(f"获取到 {len(abnormal_pattern_dict)} 个异常模式")

    # 计算正常模式分数
    print("排序正常模式...")
    score_dict = calculate_normal_scores(
        normal_pattern_dict, abnormal_pattern_dict, min_score
    )
    print(f"找到 {len(score_dict)} 个正常模式")

    # 获取深度和服务信息
    print("获取模式深度和服务信息...")
    results = calculate_results_simple(score_dict, normal_event_graphs, alarms)
    print(f"生成了 {len(results)} 个结果")

    # 按分数和深度排序
    results.sort(key=lambda i: (i["score"], i["deepth"]), reverse=True)

    # 输出排序后的结果
    print(f"\n排序结果（共 {len(results)} 个）：")
    result_list = results[:topk] if topk > 0 else results

    for idx, result in enumerate(result_list):
        events = result["events"]
        source_event = events.split("_")[0]
        target_event = events.split("_")[1]

        print(f"\n结果 #{idx + 1}:")
        print(f"  分数: {result['score']:.3f}")
        print(f"  深度: {result['deepth']}")
        print(f"  服务: {result['service']}")

        if "resource" in result:
            print(f"  资源告警: {result['resource']}")

        print(f"  源事件: {source_event}")
        print(f"  目标事件: {target_event}")

    # 保存结果
    result_file = os.path.join(output_dir, f"{ns}_full_analysis_results.txt")
    with open(result_file, "w", encoding="utf-8") as f:
        f.write(f"完整根因分析结果 ({ns})\n")
        f.write("处理了所有trace数据（无采样）\n")
        f.write(f"总计找到 {len(result_list)} 个潜在根因\n\n")

        for idx, result in enumerate(result_list):
            events = result["events"]
            source_event = events.split("_")[0]
            target_event = events.split("_")[1]

            f.write(f"根因 #{idx + 1}:\n")
            f.write(f"  分数: {result['score']:.3f}\n")
            f.write(f"  深度: {result['deepth']}\n")
            f.write(f"  服务: {result['service']}\n")

            if "resource" in result:
                f.write(f"  资源告警: {result['resource']}\n")

            f.write(f"  源事件: {source_event}\n")
            f.write(f"  目标事件: {target_event}\n\n")

    print(f"\n结果已保存到: {result_file}")

    # 完成
    end_time = time.time()
    print(f"\n{'=' * 20} 分析完成 {'=' * 20}")
    print(f"总运行时间: {end_time - start_time:.2f} 秒")

    return result_list


@timeit()
def process_all_traces(trace_file, logs_df, alarm_list, ns="ts"):
    """
    处理所有trace生成事件图（不采样）

    Args:
        trace_file: trace Parquet文件路径
        logs_df: 日志DataFrame
        alarm_list: 告警列表
        ns: 命名空间

    Returns:
        event_graphs: 事件图列表
    """
    start_time = time.time()

    # 加载trace数据
    print(f"加载trace数据: {trace_file}")
    trace_reader, trace_ids = load_trace_parquet(trace_file)
    total_traces = len(trace_ids)
    print(f"加载了 {total_traces} 个trace IDs")
    print("处理所有trace（无采样）")

    # 确保SpanId是列而不是索引
    if logs_df.index.name == "SpanId":
        logs_df = logs_df.reset_index()
        print("重置SpanId索引为列以优化处理")

    # 处理所有trace
    print(f"开始处理 {len(trace_ids)} 个trace...")

    # 使用多进程处理
    num_workers = min(multiprocessing.cpu_count(), 6)  # 可以用更多进程
    batch_size = min(100, len(trace_ids))  # 增大批次大小
    event_graphs = []
    processed_count = 0

    # 创建进程池
    with multiprocessing.Pool(processes=num_workers) as pool:
        for i in range(0, len(trace_ids), batch_size):
            batch_start = time.time()
            batch_trace_ids = trace_ids[i : min(i + batch_size, len(trace_ids))]
            batch_size_actual = len(batch_trace_ids)

            # 并行处理批次中的每个trace
            tasks = [
                (trace_reader, logs_df, trace_id, alarm_list, ns)
                for trace_id in batch_trace_ids
            ]

            # 使用map处理批次
            batch_results = pool.starmap(get_events_within_trace_parquet, tasks)

            # 处理结果
            batch_event_graphs = []
            for trace in batch_results:
                try:
                    if trace and len(trace.spans) > 0:
                        event_graph = generate_event_graph(trace)
                        # 确保事件图有内容
                        if (
                            hasattr(event_graph, "adjacency_list")
                            and event_graph.adjacency_list
                        ):
                            batch_event_graphs.append(event_graph)
                        elif (
                            hasattr(event_graph, "node_list") and event_graph.node_list
                        ):
                            batch_event_graphs.append(event_graph)
                except Exception as e:
                    print(f"处理trace结果时发生错误: {str(e)}")

            # 将批次结果添加到总结果中
            event_graphs.extend(batch_event_graphs)
            processed_count += batch_size_actual

            batch_time = time.time() - batch_start
            throughput = batch_size_actual / max(0.001, batch_time)
            print(
                f"批次进度：{processed_count}/{len(trace_ids)} 个trace ({processed_count / len(trace_ids) * 100:.1f}%), 速率: {throughput:.2f} traces/sec"
            )
            print(f"批次生成事件图: {len(batch_event_graphs)} 个")

    # 完成
    total_time = time.time() - start_time
    print(
        f"完整处理完成，耗时 {total_time:.2f} 秒。生成了 {len(event_graphs)} 个事件图"
    )

    return event_graphs


@timeit()
def get_pattern_support(event_graphs):
    """
    从事件图列表中获取模式支持度
    """
    result_support_dict = {}
    total_pair = set()

    print(f"正在处理 {len(event_graphs)} 个事件图...")

    for i, event_graph in enumerate(event_graphs):
        # 重要：调用get_support()方法来计算支持度
        support_dict = event_graph.get_support()

        if i < 5:  # 打印前几个事件图的调试信息
            print(
                f"事件图 #{i + 1}: 节点数={len(event_graph.node_list) if hasattr(event_graph, 'node_list') else 0}, 边数={len(event_graph.adjacency_list) if hasattr(event_graph, 'adjacency_list') else 0}, 支持度模式数={len(support_dict)}"
            )
            if support_dict and i < 3:
                print(f"  示例支持度: {list(support_dict.items())[:3]}")

        # 合并支持度
        for key, value in support_dict.items():
            if key in result_support_dict:
                result_support_dict[key] += value
            else:
                result_support_dict[key] = value

        # 合并模式对集合
        total_pair = total_pair.union(event_graph.pair_set)

    # 按支持度降序排序
    result_support_dict = dict(
        sorted(result_support_dict.items(), key=lambda x: x[1], reverse=True)
    )

    print(f"总共获得 {len(result_support_dict)} 个模式，{len(total_pair)} 个唯一模式对")
    if result_support_dict:
        print(f"前5个模式: {list(result_support_dict.items())[:5]}")

    return result_support_dict


@timeit()
def calculate_normal_scores(normal_pattern_dict, abnormal_pattern_dict, min_score=0.67):
    """
    计算正常模式分数
    """
    score_dict = {}

    for key in normal_pattern_dict:
        if normal_pattern_dict[key] > 5:  # 仅考虑支持度大于5的模式
            if key not in score_dict:
                score_dict[key] = 0

            if key in abnormal_pattern_dict:
                # 正常支持度 / (正常支持度 + 异常支持度)
                score_dict[key] = normal_pattern_dict[key] / (
                    normal_pattern_dict[key] + abnormal_pattern_dict[key]
                )
            else:
                score_dict[key] = 1.0  # 异常没有出现的模式得分1.0

    # 过滤低分数的模式
    filtered_dict = {k: v for k, v in score_dict.items() if v >= min_score}

    return filtered_dict


@timeit()
def get_event_depth_pod(event_graphs, event_pair):
    """
    获取事件对应的深度和服务名
    """
    source_event = event_pair.split("_")[0]
    max_depth = 0
    service_name = ""

    for event_graph in event_graphs:
        depth, service = event_graph.get_deepth_pod(source_event)
        if depth > max_depth:
            max_depth = depth
            service_name = service

    return max_depth, service_name


@timeit()
def calculate_results_simple(score_dict, normal_event_graphs, alarm_list):
    """
    计算最终结果 - 简化版本，直接使用事件文本
    """
    # 过滤非根模式
    move_list = set()
    for key in score_dict:
        # 只保留包含告警指标的模式（CPU, Network, Memory）
        target_event = key.split("_")[1]

        if (
            "cpu" not in target_event
            and "hubble" not in target_event
            and "memory" not in target_event
        ):
            # 如果目标不是告警指标，检查是否是根事件
            for key1 in score_dict:
                # 如果当前模式的源是另一个模式的目标，且分数不高于父模式，则移除
                if (
                    key.split("_")[0] == key1.split("_")[1]
                    and score_dict[key] <= score_dict[key1]
                ):
                    move_list.add(key)

    # 删除非根模式
    for item in move_list:
        if item in score_dict:
            score_dict.pop(item)

    # 构建结果列表
    result_list = []
    depth_dict = {}

    for key, value in score_dict.items():
        # 获取事件深度和service_name
        depth, service_name = get_event_depth_pod(normal_event_graphs, key)

        if service_name not in depth_dict:
            depth_dict[service_name] = depth
        elif depth_dict[service_name] < depth:
            depth_dict[service_name] = depth

        # 如果service_name为空，使用默认值
        if not service_name:
            service_name = "unknown-service"
            depth = 1

        # 检查是否存在告警
        alarm_flag = False
        if alarm_list:
            for alarm in alarm_list:
                # 匹配服务名
                alarm_service = alarm.get("service", "")
                if service_name.startswith(alarm_service):
                    result_list.append(
                        {
                            "events": key,
                            "score": value,
                            "deepth": depth,  # 保持原来的拼写错误以兼容
                            "service": service_name,
                            "resource": alarm["alarm"][0]["metric_type"],
                        }
                    )
                    alarm_flag = True
                    break

        if not alarm_flag:
            result_list.append(
                {
                    "events": key,
                    "score": value,
                    "deepth": depth,
                    "service": service_name,
                }
            )

    # 对于每个服务，只保留最深的告警
    move_indices = set()
    for alarm in alarm_list:
        alarm_service = alarm.get("service", "")

        if alarm_service in depth_dict:
            max_depth = depth_dict[alarm_service]
            move_flag = False

            for i, item in enumerate(result_list):
                if "resource" in item and item["service"].startswith(alarm_service):
                    if max_depth > item["deepth"]:
                        move_indices.add(i)
                    elif max_depth == item["deepth"] and move_flag:
                        move_indices.add(i)
                    else:
                        move_flag = True

    # 删除多余结果
    sorted_indices = sorted(list(move_indices), reverse=True)
    for idx in sorted_indices:
        if idx < len(result_list):
            result_list.pop(idx)

    return result_list


def main():
    """主函数"""
    # 默认参数
    data_dir = "D:/workspace/Nezha/data"
    output_dir = "D:/workspace/Nezha/results/full_analysis"
    ns = "ts"  # 可以改为 "hipster"
    min_score = 0.67
    topk = 10

    # 处理命令行参数
    if len(sys.argv) > 1:
        ns = sys.argv[1]

    if len(sys.argv) > 2 and sys.argv[2].replace(".", "", 1).isdigit():
        min_score = float(sys.argv[2])

    if len(sys.argv) > 3 and sys.argv[3].isdigit():
        topk = int(sys.argv[3])

    # 运行完整分析
    full_analysis(
        data_dir=data_dir, output_dir=output_dir, ns=ns, min_score=min_score, topk=topk
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
