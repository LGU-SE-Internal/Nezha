#!/usr/bin/env python3
"""
直接采样分析脚本 - 避免重复构建事件图
"""

import multiprocessing
import os
import random
import sys
import time
from pathlib import Path

# 将项目根目录添加到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入必要的模块
from data_loaders import LogLoader
from src.nezha import (
    from_id_to_template,
    generate_event_graph,
    get_events_within_trace_parquet,
)
from src.nezha.alarm_detector import AlarmDetector
from src.nezha.log_processor import load_trace_parquet
from src.nezha.metric_processor import MetricProcessor


def direct_sampling_analysis(
    data_dir="D:/workspace/Nezha/data",
    output_dir="D:/workspace/Nezha/results/direct_sampled",
    ns="ts",
    sample_size=300,
    random_seed=42,
    min_score=0.67,
    topk=10,
):
    """
    直接使用采样方法进行分析，避免重复构建事件图

    Args:
        data_dir: 数据目录路径
        output_dir: 结果输出目录
        ns: 命名空间 ("ts" 或 "hipster")
        sample_size: 采样的trace数量
        random_seed: 随机种子
        min_score: 最小分数阈值
        topk: 返回的前K个结果
    """
    start_time = time.time()
    print(f"\n{'=' * 20} 开始直接采样分析 {'=' * 20}")
    print(f"采样数量: {sample_size}")
    print(f"命名空间: {ns}")

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

    # 打印日志示例
    if not normal_logs.empty:
        print("\n日志示例 (正常阶段):")
        columns = list(normal_logs.columns)
        print(f"日志列: {columns}")

        # 显示日志示例
        log_sample = normal_logs.head(3)
        # 确保log_temp和temp_id列存在
        if "log_temp" in log_sample.columns and "temp_id" in log_sample.columns:
            # 只显示主要列
            sample_columns = ["temp_id", "log_temp", "Timestamp", "Service"]
            sample_columns = [
                col for col in sample_columns if col in log_sample.columns
            ]
            print(log_sample[sample_columns])

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

    # 第3步: 采样和事件图构建 - 正常阶段
    print(f"\n{'=' * 10} 第3步: 构建正常阶段事件图 {'=' * 10}")
    normal_trace_file = os.path.join(data_dir, "normal_traces.parquet")
    normal_event_graphs = sample_and_process(
        trace_file=normal_trace_file,
        logs_df=normal_logs,
        alarm_list=[],  # 正常阶段没有告警
        ns=ns,
        sample_size=sample_size,
        random_seed=random_seed,
    )
    print(f"生成了 {len(normal_event_graphs)} 个正常阶段事件图")

    # 第4步: 采样和事件图构建 - 异常阶段
    print(f"\n{'=' * 10} 第4步: 构建异常阶段事件图 {'=' * 10}")
    abnormal_trace_file = os.path.join(data_dir, "abnormal_traces.parquet")
    abnormal_event_graphs = sample_and_process(
        trace_file=abnormal_trace_file,
        logs_df=abnormal_logs,
        alarm_list=alarms,
        ns=ns,
        sample_size=sample_size,
        random_seed=random_seed,
    )
    print(f"生成了 {len(abnormal_event_graphs)} 个异常阶段事件图")

    # 第5步: 直接进行模式分析和排序
    print(f"\n{'=' * 10} 第5步: 直接进行模式分析和排序 {'=' * 10}")

    # 直接计算模式支持度
    normal_pattern_dict = get_pattern_support(normal_event_graphs)
    print(f"获取到 {len(normal_pattern_dict)} 个正常模式")

    abnormal_pattern_dict = get_pattern_support(abnormal_event_graphs)
    print(f"获取到 {len(abnormal_pattern_dict)} 个异常模式")

    # 创建模板映射
    template_map = create_template_map(normal_logs)
    print(f"创建了 {len(template_map)} 个模板映射") if template_map else print(
        "未能创建模板映射"
    )

    # 直接计算异常模式分数
    print("\n排序异常模式...")
    abnormal_pattern_score = calculate_abnormal_scores(
        normal_pattern_dict, abnormal_pattern_dict, min_score
    )
    print(f"找到 {len(abnormal_pattern_score)} 个异常模式")

    # 计算正常模式分数
    print("排序正常模式...")
    score_dict = calculate_normal_scores(
        normal_pattern_dict, abnormal_pattern_dict, min_score
    )
    print(f"找到 {len(score_dict)} 个正常模式")

    # 获取深度和服务信息
    print("获取模式深度和服务信息...")
    results = calculate_results(score_dict, normal_event_graphs, alarms, template_map)
    print(f"生成了 {len(results)} 个结果")

    # 按分数和深度排序
    results.sort(
        key=lambda i: (i["score"], i["deepth"]), reverse=True
    )  # 输出排序后的结果
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
    result_file = os.path.join(output_dir, f"{ns}_direct_sampled_results.txt")
    with open(result_file, "w", encoding="utf-8") as f:
        f.write(f"采样根因分析结果 ({ns})\n")
        f.write(f"采样数量: {sample_size}\n")
        f.write(f"总计找到 {len(result_list)} 个潜在根因\n\n")

        for idx, result in enumerate(result_list):
            events = result["events"]
            source_id = int(events.split("_")[0])
            target_id = int(events.split("_")[1])

            # 转换为模板
            source_template = from_id_to_template(source_id, template_map)
            target_template = from_id_to_template(target_id, template_map)

            f.write(f"根因 #{idx + 1}:\n")
            f.write(f"  分数: {result['score']:.3f}\n")
            f.write(f"  深度: {result['deepth']}\n")
            f.write(f"  服务: {result['service']}\n")

            if "resource" in result:
                f.write(f"  资源告警: {result['resource']}\n")

            f.write(f"  源模板ID: {source_id}\n")
            f.write(f"  源模板: {source_template}\n")
            f.write(f"  目标模板ID: {target_id}\n")
            f.write(f"  目标模板: {target_template}\n\n")

    print(f"\n结果已保存到: {result_file}")

    # 完成
    end_time = time.time()
    print(f"\n{'=' * 20} 分析完成 {'=' * 20}")
    print(f"总运行时间: {end_time - start_time:.2f} 秒")

    return result_list


def sample_and_process(
    trace_file, logs_df, alarm_list, ns="ts", sample_size=300, random_seed=42
):
    """
    采样并处理trace生成事件图

    Args:
        trace_file: trace Parquet文件路径
        logs_df: 日志DataFrame
        alarm_list: 告警列表
        ns: 命名空间
        sample_size: 采样数量
        random_seed: 随机种子

    Returns:
        event_graphs: 事件图列表
    """
    start_time = time.time()

    # 设置随机种子
    random.seed(random_seed)

    # 加载trace数据
    print(f"加载trace数据: {trace_file}")
    trace_reader, trace_ids = load_trace_parquet(trace_file)
    total_traces = len(trace_ids)
    print(f"加载了 {total_traces} 个trace IDs")

    # 随机采样
    if sample_size >= total_traces:
        print(f"采样数量 {sample_size} 大于等于总数 {total_traces}，使用所有trace")
        sampled_trace_ids = trace_ids
    else:
        # 确保trace_ids是列表类型
        trace_ids_list = list(trace_ids)  # 转换为标准Python列表

        sampled_trace_ids = random.sample(trace_ids_list, sample_size)
        print(f"从 {total_traces} 个trace中随机采样了 {sample_size} 个")

    # 确保SpanId是列而不是索引
    if logs_df.index.name == "SpanId":
        logs_df = logs_df.reset_index()
        print("重置SpanId索引为列以优化处理")

    # 处理采样的trace
    print(f"开始处理 {len(sampled_trace_ids)} 个采样trace...")

    # 使用多进程处理
    num_workers = multiprocessing.cpu_count()
    batch_size = min(50, len(sampled_trace_ids))  # 批次大小
    event_graphs = []
    processed_count = 0

    # 创建进程池
    with multiprocessing.Pool(processes=num_workers) as pool:
        for i in range(0, len(sampled_trace_ids), batch_size):
            batch_start = time.time()
            batch_trace_ids = sampled_trace_ids[
                i : min(i + batch_size, len(sampled_trace_ids))
            ]
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
                f"批次进度：{processed_count}/{len(sampled_trace_ids)} 个trace ({processed_count / len(sampled_trace_ids) * 100:.1f}%), 速率: {throughput:.2f} traces/sec"
            )
            print(f"批次生成事件图: {len(batch_event_graphs)} 个")

    # 完成
    total_time = time.time() - start_time
    print(
        f"采样处理完成，耗时 {total_time:.2f} 秒。生成了 {len(event_graphs)} 个事件图"
    )

    return event_graphs


def get_pattern_support(event_graphs):
    """
    从事件图列表中获取模式支持度

    Args:
        event_graphs: 事件图列表

    Returns:
        Dict: 模式支持度字典
    """
    result_support_dict = {}
    total_pair = set()

    print(f"正在处理 {len(event_graphs)} 个事件图...")

    for i, event_graph in enumerate(event_graphs):
        # 重要：调用get_support()方法来计算支持度
        support_dict = event_graph.get_support()

        if i < 3:  # 打印前几个事件图的调试信息
            print(
                f"事件图 #{i + 1}: 节点数={len(event_graph.node_list)}, 边数={len(event_graph.adjacency_list)}, 支持度模式数={len(support_dict)}"
            )
            if support_dict:
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


def create_template_map(logs_df):
    """
    从日志DataFrame创建模板映射

    Args:
        logs_df: 日志DataFrame

    Returns:
        Dict: 模板ID到模板文本的映射
    """
    template_map = {}

    if (
        not logs_df.empty
        and "temp_id" in logs_df.columns
        and "log_temp" in logs_df.columns
    ):
        # 从日志中提取唯一模板
        unique_templates = logs_df.drop_duplicates(subset=["temp_id"])
        # 创建映射
        for _, row in unique_templates.iterrows():
            try:
                temp_id = int(row["temp_id"])
                log_temp = row["log_temp"]
                template_map[temp_id] = log_temp
            except Exception as e:
                print(f"处理模板映射时出错: {e}")
                pass

    return template_map


def calculate_abnormal_scores(
    normal_pattern_dict, abnormal_pattern_dict, min_score=0.67
):
    """
    计算异常模式分数

    Args:
        normal_pattern_dict: 正常模式支持度字典
        abnormal_pattern_dict: 异常模式支持度字典
        min_score: 最小分数阈值

    Returns:
        List: 排序后的异常模式
    """
    score_dict = {}

    # 计算每个模式的分数
    for key in abnormal_pattern_dict.keys():
        if abnormal_pattern_dict[key] > 5:  # 支持度大于5的模式
            if key not in score_dict:
                score_dict[key] = 0

            if key in normal_pattern_dict:
                # 异常支持度 / (异常支持度 + 正常支持度)
                score_dict[key] = abnormal_pattern_dict[key] / (
                    abnormal_pattern_dict[key] + normal_pattern_dict[key]
                )
            else:
                score_dict[key] = 1.0  # 正常没有出现的模式得分1.0

    # 过滤低分数的模式
    filtered_dict = {k: v for k, v in score_dict.items() if v >= min_score}

    # 按分数降序排序
    sorted_patterns = sorted(
        filtered_dict, key=lambda x: filtered_dict[x], reverse=True
    )

    return sorted_patterns


def calculate_normal_scores(normal_pattern_dict, abnormal_pattern_dict, min_score=0.67):
    """
    计算正常模式分数

    Args:
        normal_pattern_dict: 正常模式支持度字典
        abnormal_pattern_dict: 异常模式支持度字典
        min_score: 最小分数阈值

    Returns:
        Dict: 模式分数字典
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


def get_event_depth_pod(event_graphs, event_pair):
    """
    获取事件对应的深度和服务名

    Args:
        event_graphs: 事件图列表
        event_pair: 事件对，格式为 "source_target"

    Returns:
        Tuple: (最大深度, 对应的服务名称)
    """
    source = int(event_pair.split("_")[0])
    max_depth = 0
    service_name = ""

    for event_graph in event_graphs:
        depth, service = event_graph.get_deepth_pod(source)
        if depth > max_depth:
            max_depth = depth
            service_name = service

    return max_depth, service_name


def calculate_results(score_dict, normal_event_graphs, alarm_list, template_map):
    """
    计算最终结果

    Args:
        score_dict: 模式分数字典
        normal_event_graphs: 正常事件图列表
        alarm_list: 告警列表
        template_map: 模板映射字典

    Returns:
        List: 结果列表
    """
    # 过滤非根模式
    move_list = set()
    for key in score_dict:
        # 只保留包含告警指标的模式（CPU, Network, Memory）
        target_event_id = int(key.split("_")[1])
        target_template = from_id_to_template(target_event_id, template_map)

        if (
            "cpu" not in target_template
            and "http" not in target_template
            and "memory" not in target_template
        ):
            # 如果目标不是告警指标，检查是否是根事件
            for key1 in score_dict:
                # 如果当前模式的源是另一个模式的目标，且分数不高于父模式，则移除
                if (
                    int(key.split("_")[0]) == int(key1.split("_")[1])
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
    output_dir = "D:/workspace/Nezha/results/direct_sampled"
    ns = "ts"  # 可以改为 "hipster"
    sample_size = 300
    min_score = 0.67
    topk = 10

    # 处理命令行参数
    if len(sys.argv) > 1:
        ns = sys.argv[1]

    if len(sys.argv) > 2 and sys.argv[2].isdigit():
        sample_size = int(sys.argv[2])

    if len(sys.argv) > 3 and sys.argv[3].replace(".", "", 1).isdigit():
        min_score = float(sys.argv[3])

    if len(sys.argv) > 4 and sys.argv[4].isdigit():
        topk = int(sys.argv[4])

    # 运行采样分析
    direct_sampling_analysis(
        data_dir=data_dir,
        output_dir=output_dir,
        ns=ns,
        sample_size=sample_size,
        min_score=min_score,
        topk=topk,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
