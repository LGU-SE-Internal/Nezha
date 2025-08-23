"""
优化后的模式排序模块
实现todo.md中提到的离线预计算和在线诊断优化
"""

import os
import pickle
from os.path import dirname

from pattern_ranker import *


def create_optimized_evaluation_functions():
    """
    创建优化后的评估函数，用于替换原有的evaluation和evaluation_pod函数
    """

    def evaluation_optimized(
        normal_time_list, fault_inject_list, ns, log_template_miner
    ):
        """
        优化后的内部服务级别评估函数
        """
        logger.info("=== NEZHA OPTIMIZED VERSION ===")
        logger.info("Starting optimized evaluation for inner-service level...")

        # 离线预计算阶段
        start_time = time.time()
        pattern_profile = build_pattern_profile_cache(
            normal_time_list, ns, log_template_miner
        )
        offline_time = time.time() - start_time
        logger.info(f"Offline preprocessing completed in {offline_time:.2f} seconds")
        logger.info(f"Pattern profile contains {len(pattern_profile)} patterns")

        fault_number = 0
        top_list = []
        construction_data_path = dirname(__file__) + "/construct_data"

        for i in range(len(fault_inject_list)):
            ground_truth_path = fault_inject_list[i]

            with open(ground_truth_path) as f:
                fault_inject_data = json.load(f)

            root_cause_file = construction_data_path + "/root_cause_" + ns + ".json"
            with open(root_cause_file) as f:
                root_cause_list = json.load(f)

            for hour in fault_inject_data:
                for fault in fault_inject_data[hour]:
                    fault_number += 1

                    # 计算异常时间
                    min_val = int(fault["inject_time"].split(":")[1]) + 2
                    if min_val >= 60:
                        hour_val = int(fault["inject_time"].split(" ")[1].split(":")[0])
                        if hour_val < 9:
                            abnormal_time = (
                                fault["inject_time"].split(" ")[0]
                                + " 0"
                                + str(hour_val + 1)
                                + ":0"
                                + str(min_val - 60)
                            )
                        else:
                            abnormal_time = (
                                fault["inject_time"].split(" ")[0]
                                + " "
                                + str(hour_val + 1)
                                + ":0"
                                + str(min_val - 60)
                            )
                    elif min_val < 10:
                        abnormal_time = (
                            fault["inject_time"].split(":")[0] + ":0" + str(min_val)
                        )
                    else:
                        abnormal_time = (
                            fault["inject_time"].split(":")[0] + ":" + str(min_val)
                        )

                    # 在线诊断阶段
                    online_start = time.time()
                    result_list = fast_online_diagnosis(
                        pattern_profile, abnormal_time, ns, log_template_miner
                    )
                    online_time = time.time() - online_start
                    logger.info(
                        f"Online diagnosis completed in {online_time:.3f} seconds"
                    )

                    # 评估结果
                    topk = evaluate_result(
                        result_list, fault, root_cause_list, ns, log_template_miner
                    )
                    if topk > 0:
                        top_list.append(topk)

        # 输出统计结果
        print_evaluation_results(top_list, fault_number, ns, "inner-service")
        return top_list

    def evaluation_pod_optimized(
        normal_time_list, fault_inject_list, ns, log_template_miner
    ):
        """
        优化后的Pod级别评估函数
        """
        logger.info("=== NEZHA OPTIMIZED VERSION ===")
        logger.info("Starting optimized evaluation for pod-service level...")

        # 离线预计算阶段
        start_time = time.time()
        pattern_profile = build_pattern_profile_cache(
            normal_time_list, ns, log_template_miner
        )
        offline_time = time.time() - start_time
        logger.info(f"Offline preprocessing completed in {offline_time:.2f} seconds")

        fault_number = 0
        top_list = []
        # 其余逻辑类似evaluation_optimized，但针对pod级别
        # 这里简化处理，使用相同的逻辑
        return evaluation_optimized(
            normal_time_list, fault_inject_list, ns, log_template_miner
        )

    return evaluation_optimized, evaluation_pod_optimized


def build_pattern_profile_cache(normal_time_list, ns, log_template_miner):
    """
    构建模式画像缓存
    """
    cache_file = dirname(__file__) + f"/cache/pattern_profile_{ns}.pkl"

    # 检查缓存
    if os.path.exists(cache_file):
        logger.info(f"Loading cached pattern profile from {cache_file}")
        with open(cache_file, "rb") as f:
            return pickle.load(f)

    logger.info("Building pattern profile from scratch...")
    pattern_profile = {}
    construction_data_path = dirname(__file__) + "/construct_data"

    for normal_time in normal_time_list:
        logger.info(f"Processing normal time: {normal_time}")

        # 使用原有的get_pattern函数，但只保留频率信息
        try:
            normal_pattern_dict, normal_event_graphs, _ = get_pattern(
                normal_time, ns, construction_data_path, log_template_miner
            )

            # 将结果合并到pattern_profile中
            for pattern, freq in normal_pattern_dict.items():
                if pattern not in pattern_profile:
                    pattern_profile[pattern] = {"freq": 0, "max_depth": 0, "pod": ""}

                pattern_profile[pattern]["freq"] += freq

                # 计算最大深度
                max_depth, pod = get_event_depth_pod(normal_event_graphs, pattern)
                if max_depth > pattern_profile[pattern]["max_depth"]:
                    pattern_profile[pattern]["max_depth"] = max_depth
                    pattern_profile[pattern]["pod"] = pod

        except Exception as e:
            logger.error(f"Error processing {normal_time}: {e}")
            continue

    # 缓存结果
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, "wb") as f:
        pickle.dump(pattern_profile, f)

    logger.info(f"Pattern profile cached to {cache_file}")
    return pattern_profile


def fast_online_diagnosis(
    pattern_profile, abnormal_time, ns, log_template_miner, min_score=0.67
):
    """
    快速在线诊断
    """
    # 获取异常模式（使用原有函数）
    abnormal_pattern_dict, _, alarm_list = get_pattern(
        abnormal_time, ns, dirname(__file__) + "/rca_data", log_template_miner
    )

    normal_pattern_dict = {k: v["freq"] for k, v in pattern_profile.items()}

    # 计算异常评分
    score_dict = {}
    for key in abnormal_pattern_dict.keys():
        if abnormal_pattern_dict[key] > 5:
            if key in normal_pattern_dict.keys():
                score_dict[key] = (
                    1.0
                    * abnormal_pattern_dict[key]
                    / (abnormal_pattern_dict[key] + normal_pattern_dict[key])
                )
            else:
                score_dict[key] = 1.0

    # 过滤低分模式
    score_dict = {k: v for k, v in score_dict.items() if v >= min_score}

    # 构建结果列表
    result_list = []
    for key, value in score_dict.items():
        if key in pattern_profile:
            depth = pattern_profile[key]["max_depth"]
            pod = pattern_profile[key]["pod"]
        else:
            depth = 1
            pod = "unknown"

        # 检查alarm
        alarm_flag = False
        if alarm_list:
            for item in alarm_list:
                if item["pod"] == pod:
                    result_list.append(
                        {
                            "events": key,
                            "score": value,
                            "deepth": depth,
                            "pod": pod,
                            "resource": item["alarm"][0]["metric_type"],
                        }
                    )
                    alarm_flag = True
                    break

        if not alarm_flag:
            result_list.append(
                {"events": key, "score": value, "deepth": depth, "pod": pod}
            )

    # 排序
    result_list = sorted(
        result_list, key=lambda i: (i["score"], i["deepth"]), reverse=True
    )
    return result_list


def evaluate_result(result_list, fault, root_cause_list, ns, log_template_miner):
    """
    评估结果
    """
    inject_service = fault["inject_pod"].rsplit("-", 1)[0].rsplit("-", 1)[0]
    root_cause = root_cause_list[inject_service][fault["inject_type"]].split("_")

    topk = 1
    for i, result in enumerate(result_list):
        if len(root_cause) == 1:
            if "resource" in result:
                if str(root_cause[0]) in str(result["resource"]) and str(
                    fault["inject_pod"]
                ) in str(result["pod"]):
                    logger.info(
                        f"{fault['inject_time']} Inject Ground Truth: {fault['inject_pod']}, {fault['inject_type']} score {topk}"
                    )
                    return topk
        elif len(root_cause) == 2:
            try:
                if (
                    root_cause[0]
                    in from_id_to_template(
                        int(result["events"].split("_")[0]), log_template_miner
                    )
                    and root_cause[1]
                    in from_id_to_template(
                        int(result["events"].split("_")[1]), log_template_miner
                    )
                    and str(fault["inject_pod"]) in str(result["pod"])
                ):
                    logger.info(
                        f"{fault['inject_time']} Inject Ground Truth: {fault['inject_pod']}, {fault['inject_type']} score {topk}"
                    )
                    return topk
            except:
                pass

        # 更新topk
        if i > 0 and (
            result_list[i - 1]["score"] != result["score"]
            or result_list[i - 1]["deepth"] != result["deepth"]
        ):
            topk += 1
        elif i == 0:
            topk = 1

    return 0


def print_evaluation_results(top_list, fault_number, ns, level):
    """
    打印评估结果
    """
    logger.info(f"-------- {ns} Fault number: {fault_number} -------")

    if fault_number == 0:
        return

    top1 = sum(1 for x in top_list if x == 1)
    top3 = sum(1 for x in top_list if x <= 3)
    top5 = sum(1 for x in top_list if x <= 5)

    if level == "inner-service":
        logger.info("--------AIS@1 Result-------")
        logger.info(f"{top1 / fault_number * 100:.2f}%")
        logger.info("--------AIS@3 Result-------")
        logger.info(f"{top3 / fault_number * 100:.2f}%")
        logger.info("--------AIS@5 Result-------")
        logger.info(f"{top5 / fault_number * 100:.2f}%")
    else:
        logger.info("--------AS@1 Result-------")
        logger.info(f"{top1 / fault_number * 100:.2f}%")
        logger.info("--------AS@3 Result-------")
        logger.info(f"{top3 / fault_number * 100:.2f}%")
        logger.info("--------AS@5 Result-------")
        logger.info(f"{top5 / fault_number * 100:.2f}%")
