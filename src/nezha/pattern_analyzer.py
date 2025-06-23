import datetime
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from log import Logger

from .alarm_manager import prepare_alarm_data
from .integrator import data_integrate_parquet
from .log_processor import load_processed_logs

# 设置日志
log_path = (
    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    + "/log/"
    + str(datetime.datetime.now().strftime("%Y-%m-%d"))
    + "_nezha.log"
)
logger = Logger(log_path, logging.DEBUG, __name__).getlog()


def from_id_to_template(
    event_id: int, template_map: Optional[Dict[int, str]] = None
) -> str:
    """
    将事件ID转换为对应的日志模板

    Args:
        event_id: 事件ID
        template_map: ID到模板的映射字典

    Returns:
        str: 对应的日志模板文本或原始事件ID
    """
    if template_map is None:
        return str(event_id)

    return template_map.get(event_id, str(event_id))


class PatternAnalyzer:
    """
    模式分析器：用于分析事件图中的模式并进行排序
    """

    def __init__(
        self,
        data_dir: str = "D:/workspace/Nezha/data",
        rca_dir: str = "D:/workspace/Nezha/rca_data",
        normal_logs_df=None,
        abnormal_logs_df=None,
    ):
        """
        初始化模式分析器

        Args:
            data_dir: 数据目录路径
            rca_dir: RCA结果存储目录
            normal_logs_df: 可选的正常阶段日志DataFrame
            abnormal_logs_df: 可选的异常阶段日志DataFrame
        """
        self.data_dir = Path(data_dir)
        self.rca_dir = Path(rca_dir)
        self.template_maps = {}  # 存储各命名空间的ID到模板映射
        self.normal_logs_df = normal_logs_df  # 存储正常阶段的日志DataFrame
        self.abnormal_logs_df = abnormal_logs_df  # 存储异常阶段的日志DataFrame

    def load_template_map(self, ns: str) -> Dict[int, str]:
        """
        从处理过的日志中加载日志模板映射

        Args:
            ns: 命名空间，如 'ts' 或 'hipster'

        Returns:
            Dict[int, str]: ID到模板的映射字典
        """
        if ns in self.template_maps:
            return self.template_maps[ns]

        template_map = {}
        try:
            # 尝试首先使用预加载的日志DataFrame
            if self.normal_logs_df is not None:
                logs = self.normal_logs_df
                logger.info("使用预加载的日志DataFrame获取模板映射")
            else:
                # 否则从文件加载
                logs = load_processed_logs(self.data_dir, phase="normal")

            # 检查是否有模板ID和模板文本列
            if (
                not logs.empty
                and "temp_id" in logs.columns
                and "log_temp" in logs.columns
            ):
                # 从日志数据创建模板映射
                temp_id_col = (
                    logs["temp_id"].astype(int) if "temp_id" in logs.columns else None
                )
                log_temp_col = logs["log_temp"] if "log_temp" in logs.columns else None

                if temp_id_col is not None and log_temp_col is not None:
                    # 创建唯一的模板映射
                    unique_templates = {}
                    for idx, temp_id in enumerate(temp_id_col):
                        if temp_id not in unique_templates:
                            unique_templates[temp_id] = log_temp_col.iloc[idx]

                    template_map = unique_templates
                    logger.info(
                        f"从处理过的日志中提取了 {len(template_map)} 个模板映射"
                    )
            else:
                logger.warning("处理过的日志中没有找到模板信息")

            self.template_maps[ns] = template_map
            return template_map

        except Exception as e:
            logger.error(f"从日志中提取模板映射出错: {e}")
            return {}

    def get_pattern(
        self, phase: str = "normal", ns: str = "ts", topk: int = 30, event_graphs=None
    ) -> Tuple[Dict, List, List]:
        """
        获取指定阶段（正常/异常）的模式

        Args:
            phase: 阶段，"normal" 或 "abnormal"
            ns: 命名空间，如 "ts" 或 "hipster"
            topk: 返回的前K个模式
            event_graphs: 可选的已有事件图列表，如果提供则直接使用

        Returns:
            Tuple: (模式支持度字典, 事件图列表, 告警列表)
        """
        try:
            # 如果已经提供了事件图，直接使用
            if event_graphs:
                logger.info(f"使用提供的 {len(event_graphs)} 个事件图进行模式计算")
                pattern_support_dict = self.get_pattern_support(event_graphs)
                return pattern_support_dict, event_graphs, []

            # 构建路径
            log_data_path = self.data_dir

            # 根据阶段使用对应的 parquet 文件路径
            trace_file = os.path.join(self.data_dir, f"{phase}_traces.parquet")
            logger.info(f"使用 {phase} 阶段的 trace 数据: {trace_file}")

            # 获取指标数据并生成告警
            alarm_manager = prepare_alarm_data(
                data_dir=str(self.data_dir), regenerate_thresholds=False
            )

            # 获取当前阶段的所有告警
            alarm_list = []
            if phase == "abnormal":
                # 对于异常阶段，我们获取所有告警
                alarm_list = alarm_manager.generate_alarms()
                logger.info(f"为 {phase} 阶段生成 {len(alarm_list)} 个告警")

            # 检查是否有预加载的日志DataFrame
            logs_df = None
            if phase == "normal" and self.normal_logs_df is not None:
                logs_df = self.normal_logs_df
                logger.info(f"使用预加载的正常阶段日志DataFrame: {len(logs_df)} 条记录")
            elif phase == "abnormal" and self.abnormal_logs_df is not None:
                logs_df = self.abnormal_logs_df
                logger.info(f"使用预加载的异常阶段日志DataFrame: {len(logs_df)} 条记录")

            # 使用 parquet 集成函数
            event_graphs = data_integrate_parquet(
                trace_file=trace_file,
                log_data_path=str(log_data_path),
                alarm_list=alarm_list,
                ns=ns,
                phase=phase,
                logs_df=logs_df,  # 传递预加载的日志DataFrame
            )

            # 获取模式支持度
            pattern_support_dict = self.get_pattern_support(event_graphs)
            logger.info(
                f"从 {len(event_graphs)} 个事件图中提取了 {len(pattern_support_dict)} 个模式"
            )

            return pattern_support_dict, event_graphs, alarm_list

        except Exception as e:
            logger.error(f"获取{phase}阶段模式时出错: {e}")
            return {}, [], []

    def get_pattern_support(self, event_graphs: List) -> Dict:
        """
        从事件图列表中获取模式支持度

        Args:
            event_graphs: 事件图列表

        Returns:
            Dict: 模式支持度字典，键为模式，值为支持度
        """
        result_support_dict = {}
        total_pair = set()

        for event_graph in event_graphs:
            # 合并支持度
            for key, value in event_graph.support_dict.items():
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

        return result_support_dict

    def get_event_depth_pod(
        self, event_graphs: List, event_pair: str
    ) -> Tuple[int, str]:
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

    def abnormal_pattern_ranker(
        self,
        normal_pattern_dict: Dict,
        abnormal_pattern_dict: Dict,
        min_score: float = 0.67,
    ) -> List:
        """
        对异常模式进行排序

        Args:
            normal_pattern_dict: 正常模式支持度字典
            abnormal_pattern_dict: 异常模式支持度字典
            min_score: 最小分数阈值

        Returns:
            List: 排序后的模式列表
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

    def pattern_ranker(
        self,
        normal_pattern_dict: Dict = None,
        normal_event_graphs: List = None,
        ns: str = "ts",
        topk: int = 10,
        min_score: float = 0.67,
    ) -> Tuple[List[Dict], List]:
        """
        模式排序主函数

        Args:
            normal_pattern_dict: 正常模式支持度字典，如果为None则自动获取
            normal_event_graphs: 正常事件图列表，如果为None则自动获取
            ns: 命名空间
            topk: 返回的前K个模式
            min_score: 最小分数阈值

        Returns:
            Tuple: (排序后的结果列表, 异常模式分数列表)
        """
        # 加载模板映射
        template_map = self.load_template_map(ns) or {}

        # 如果没有提供正常模式数据，则自动获取
        if normal_pattern_dict is None or normal_event_graphs is None:
            normal_pattern_dict, normal_event_graphs, _ = self.get_pattern(
                phase="normal", ns=ns
            )

        # 获取异常模式
        abnormal_pattern_dict, abnormal_graphs, alarm_list = self.get_pattern(
            phase="abnormal", ns=ns
        )

        # 排序异常模式
        abnormal_pattern_score = self.abnormal_pattern_ranker(
            normal_pattern_dict, abnormal_pattern_dict, min_score
        )

        # 计算正常模式的分数
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

        # 过滤低分数模式
        score_dict = {k: v for k, v in score_dict.items() if v >= min_score}

        # 过滤非根模式
        move_list = set()
        for key in score_dict:
            # 只保留包含告警指标的模式（CPU, Network, Memory）
            target_event_id = int(key.split("_")[1])
            target_template = from_id_to_template(target_event_id, template_map)

            if (
                "Cpu" not in target_template
                and "Network" not in target_template
                and "Memory" not in target_template
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
            depth, service_name = self.get_event_depth_pod(normal_event_graphs, key)

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

        # 按分数和深度排序
        result_list = sorted(
            result_list, key=lambda i: (i["score"], i["deepth"]), reverse=True
        )

        logger.info(f"排序后的结果列表: {len(result_list)} 个模式")

        return result_list[:topk] if topk > 0 else result_list, abnormal_pattern_score
