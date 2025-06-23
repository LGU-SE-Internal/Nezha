import datetime
import json
import logging
import os
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from .utils import timeit
from log import Logger

# 设置日志
log_path = (
    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    + "/log/"
    + str(datetime.datetime.now().strftime("%Y-%m-%d"))
    + "_nezha.log"
)
logger = Logger(log_path, logging.DEBUG, __name__).getlog()


class AlarmDetector:
    """告警检测器：根据阈值检测指标数据中的异常值"""

    def __init__(self, threshold_dir: str = "D:/workspace/Nezha/metric_threshold"):
        self.threshold_dir = Path(threshold_dir)
        self.thresholds = None

    def load_thresholds(self) -> Dict:
        """
        加载指标阈值

        Returns:
            Dict: 加载的阈值字典
        """
        try:
            threshold_path = self.threshold_dir / "thresholds.json"
            if threshold_path.exists():
                with open(threshold_path, "r") as f:
                    self.thresholds = json.load(f)
                logger.info(f"成功从 {str(threshold_path)} 加载阈值")
                return self.thresholds
            else:
                logger.warning(f"阈值文件 {str(threshold_path)} 不存在")
                self.thresholds = {}
                return {}
        except Exception as e:
            logger.error(f"加载阈值失败: {e}")
            self.thresholds = {}
            return {}
    @timeit()
    def detect_alarms(self, metrics_df: pd.DataFrame) -> List[Dict]:
        """
        检测告警：根据阈值识别指标数据中的异常值

        Args:
            metrics_df: 包含指标数据的DataFrame

        Returns:
            List[Dict]: 告警列表
        """
        # 如果阈值未加载，先加载阈值
        if self.thresholds is None:
            self.load_thresholds()

        # 如果没有有效的阈值，无法检测告警
        if not self.thresholds:
            logger.warning("没有有效的阈值，跳过告警检测")
            return []

        alarm_list = []

        try:
            # 确保有ServiceName列，如果没有但有PodName，则使用PodName作为ServiceName
            if (
                "ServiceName" not in metrics_df.columns
                and "PodName" in metrics_df.columns
            ):
                metrics_df["ServiceName"] = metrics_df["PodName"]
                logger.info("未找到ServiceName列，使用PodName列代替")

            # 如果找不到MetricType列，尝试其他可能的列名
            if (
                "MetricType" not in metrics_df.columns
                and "MetricName" in metrics_df.columns
            ):
                metrics_df["MetricType"] = metrics_df["MetricName"]
                logger.info("未找到MetricType列，使用MetricName列代替")

            # 如果找不到MetricValue列，尝试其他可能的列名
            if (
                "MetricValue" not in metrics_df.columns
                and "Value" in metrics_df.columns
            ):
                metrics_df["MetricValue"] = metrics_df["Value"]
                logger.info("未找到MetricValue列，使用Value列代替")

            # 如果仍然没有ServiceName列，无法进行分组
            if "ServiceName" not in metrics_df.columns:
                logger.error("指标数据中没有ServiceName或PodName列，无法进行分组")
                return []

            # 确保关键列存在
            if (
                "MetricType" not in metrics_df.columns
                or "MetricValue" not in metrics_df.columns
            ):
                logger.error("指标数据中缺少必要的列: MetricType或MetricValue")
                return []

            # 对每个服务分组处理
            service_groups = metrics_df.groupby("ServiceName")

            for service_name, service_metrics in service_groups:
                # 分组处理每个服务的指标
                alarms_for_service = []

                # 检查每种指标类型
                for metric_type, threshold in self.thresholds.items():
                    # 过滤当前指标类型的数据
                    metric_data = service_metrics[
                        service_metrics["MetricType"] == metric_type
                    ]

                    # 如果没有该类型的数据，跳过
                    if metric_data.empty:
                        continue

                    # 计算平均值
                    avg_value = np.mean(metric_data["MetricValue"])

                    # 检查是否超过阈值
                    if "upper" in threshold and avg_value > threshold["upper"]:
                        alarms_for_service.append(
                            {
                                "metric_type": metric_type,
                                "alarm_flag": True,
                                "avg_value": float(avg_value),
                                "threshold": float(threshold["upper"]),
                                "alarm_type": "upper",
                            }
                        )
                    elif "lower" in threshold and avg_value < threshold["lower"]:
                        alarms_for_service.append(
                            {
                                "metric_type": metric_type,
                                "alarm_flag": True,
                                "avg_value": float(avg_value),
                                "threshold": float(threshold["lower"]),
                                "alarm_type": "lower",
                            }
                        )

                # 如果该服务有告警，添加到告警列表
                if alarms_for_service:
                    alarm_list.append(
                        {"service": service_name, "alarm": alarms_for_service}
                    )
        except Exception as e:
            logger.error(f"检测告警时出错: {e}")

        return alarm_list

    def generate_alarms_from_file(
        self, metrics_file: str, is_abnormal: bool = True
    ) -> List[Dict]:
        """
        从指标文件生成告警

        Args:
            metrics_file: 指标文件路径
            is_abnormal: 是否为异常阶段数据

        Returns:
            List[Dict]: 告警列表
        """
        try:
            import pandas as pd

            # 直接从文件加载指标数据
            df = (
                pd.read_parquet(metrics_file)
                if metrics_file.endswith(".parquet")
                else pd.read_csv(metrics_file)
            )
            return self.detect_alarms(df)
        except Exception as e:
            logger.error(f"从文件生成告警失败: {e}")
            return []
