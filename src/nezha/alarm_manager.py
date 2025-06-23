import datetime
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from log import Logger

from .alarm_detector import AlarmDetector
from .metric_processor import MetricProcessor

# 设置日志
log_path = (
    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    + "/log/"
    + str(datetime.datetime.now().strftime("%Y-%m-%d"))
    + "_nezha.log"
)
logger = Logger(log_path, logging.DEBUG, __name__).getlog()


class AlarmManager:
    """告警管理器：管理指标处理和告警检测的整体流程"""

    def __init__(
        self,
        data_dir: str = "D:/workspace/Nezha/data",
        threshold_dir: str = "D:/workspace/Nezha/metric_threshold",
    ):
        self.data_dir = Path(data_dir)
        self.threshold_dir = Path(threshold_dir)
        self.metric_processor = MetricProcessor(str(self.data_dir))
        self.alarm_detector = AlarmDetector(str(self.threshold_dir))

    def prepare_thresholds(self, std_multiplier: float = 3.0) -> Dict:
        """
        准备阈值：从正常阶段数据计算阈值并保存

        Args:
            std_multiplier: 标准差倍数，用于设置阈值

        Returns:
            Dict: 计算的阈值
        """
        # 加载正常阶段指标
        normal_metrics = self.metric_processor.load_metrics(phase="normal")

        # 计算阈值
        thresholds = self.metric_processor.calculate_thresholds(
            normal_metrics, std_multiplier
        )

        # 保存阈值
        self.metric_processor.save_thresholds(str(self.threshold_dir))

        return thresholds

    def generate_alarms(self, at_time: Optional[pd.Timestamp] = None) -> List[Dict]:
        """
        生成告警：从异常阶段数据中检测告警

        Args:
            at_time: 指定时间点，如果提供则只检测该时间点的数据，
                    如果为None则处理所有时间点的数据

        Returns:
            List[Dict]: 告警列表
        """
        # 加载异常阶段指标
        abnormal_metrics = self.metric_processor.load_metrics(phase="abnormal")

        if abnormal_metrics.empty:
            logger.warning("异常阶段指标数据为空")
            return []

        # 如果指定了时间，过滤数据
        if at_time is not None:
            abnormal_metrics = abnormal_metrics[abnormal_metrics["TimeUnix"] == at_time]
            if abnormal_metrics.empty:
                logger.warning(f"在时间 {at_time} 没有找到指标数据")
                return []

        # 检测告警
        alarms = self.alarm_detector.detect_alarms(abnormal_metrics)

        logger.info(f"生成了 {len(alarms)} 个告警")
        return alarms

    def load_and_prepare(self) -> None:
        """加载配置和准备数据"""
        # 加载阈值
        self.alarm_detector.load_thresholds()

    def get_all_alarm_times(self) -> List[pd.Timestamp]:
        """获取异常阶段所有时间点"""
        try:
            abnormal_metrics = self.metric_processor.load_metrics(phase="abnormal")
            return sorted(abnormal_metrics["TimeUnix"].unique())
        except Exception as e:
            logger.error(f"获取时间点失败: {e}")
            return []


def prepare_alarm_data(
    data_dir: str = "D:/workspace/Nezha/data",
    threshold_dir: str = "D:/workspace/Nezha/metric_threshold",
    regenerate_thresholds: bool = False,
) -> AlarmManager:
    """
    准备告警数据的便捷函数

    Args:
        data_dir: 数据目录
        threshold_dir: 阈值目录
        regenerate_thresholds: 是否重新生成阈值

    Returns:
        AlarmManager: 配置好的告警管理器
    """
    manager = AlarmManager(data_dir, threshold_dir)

    # 如果需要，重新生成阈值
    if regenerate_thresholds:
        manager.prepare_thresholds()
    else:
        # 否则只加载现有阈值
        manager.load_and_prepare()

    return manager
