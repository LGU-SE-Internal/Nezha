import datetime
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

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

# HTTP持续时间指标列表
HTTP_DURATION_METRICS = [
    "hubble_http_request_duration_p50_seconds",
    "hubble_http_request_duration_p90_seconds",
    "hubble_http_request_duration_p95_seconds",
    "hubble_http_request_duration_p99_seconds",
]

# 默认选择的metrics
DEFAULT_SELECTED_METRICS = [
    "k8s.pod.cpu.usage",
    "k8s.pod.cpu.node.utilization",
    "k8s.pod.cpu_limit_utilization",
    "k8s.pod.memory.usage",
    "k8s.pod.memory_limit_utilization",
    "hubble_http_request_duration_p50_seconds",
    "hubble_http_request_duration_p90_seconds",
    "hubble_http_request_duration_p95_seconds",
    "hubble_http_request_duration_p99_seconds",
]


class MetricProcessor:
    """指标处理器：加载、预处理和分析指标数据"""

    def __init__(self, data_dir: str = "D:/workspace/Nezha/data"):
        self.data_dir = Path(data_dir)
        self.thresholds = {}  # 存储各服务各指标的阈值
    @timeit()
    def load_metrics(
        self, phase: str = "normal", selected_metrics: List[str] = DEFAULT_SELECTED_METRICS
    ) -> pd.DataFrame:
        """
        加载并预处理指标数据

        Args:
            phase: "normal" 或 "abnormal"
            selected_metrics: 选择的指标列表，默认为 DEFAULT_SELECTED_METRICS

        Returns:
            pd.DataFrame: 处理后的指标数据
        """
        file_path = self.data_dir / f"{phase}_metrics.parquet"

        if not file_path.exists():
            logger.warning(f"指标文件不存在: {file_path}")
            return pd.DataFrame()

        try:
            # 加载指标数据
            df = pd.read_parquet(file_path)
            logger.info(f"加载{phase}指标数据: {len(df)} 条记录")

            # 选择指标
            if selected_metrics:
                original_count = len(df)
                df = df[df["MetricName"].isin(selected_metrics)]
                logger.info(f"指标过滤: {original_count} -> {len(df)} 条记录")

            # 重命名HTTP持续时间指标
            df = self._rename_http_duration_metrics(df)

            return df

        except Exception as e:
            logger.error(f"加载指标数据失败: {e}")
            return pd.DataFrame()

    def _rename_http_duration_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """重命名HTTP持续时间指标，添加服务端/客户端标识"""
        if "MetricName" not in df.columns or "Attributes" not in df.columns:
            return df

        renamed_count = 0

        for idx, row in df.iterrows():
            metric_name = row.get("MetricName", "")
            attributes = row.get("Attributes", "")

            if metric_name in HTTP_DURATION_METRICS:
                reporter = self._extract_reporter(attributes)
                if reporter:
                    new_name = f"{metric_name}_{reporter}"
                    df.at[idx, "MetricName"] = new_name
                    renamed_count += 1

        if renamed_count > 0:
            logger.info(f"重命名了 {renamed_count} 个HTTP持续时间指标")

        return df

    def _extract_reporter(self, attributes: str) -> Optional[str]:
        """从attributes中提取reporter字段"""
        try:
            if isinstance(attributes, str) and attributes.strip().startswith("{"):
                attrs_dict = json.loads(attributes)
                reporter = attrs_dict.get("reporter", "").lower()
                return reporter if reporter in ["server", "client"] else None
        except Exception:
            pass
        return None

    def extract_service_info(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        提取服务信息，确保ServiceName列存在
        如果ServiceName不存在，尝试从ResourceAttributes提取
        """
        if "ServiceName" not in df.columns and "ResourceAttributes" in df.columns:
            # 从ResourceAttributes提取服务名
            df["ServiceName"] = df["ResourceAttributes"].apply(
                self._extract_service_name
            )

        return df

    def _extract_service_name(self, resource_attrs: str) -> str:
        """从ResourceAttributes中提取服务名"""
        try:
            if isinstance(resource_attrs, str) and resource_attrs.strip().startswith(
                "{"
            ):
                attrs_dict = json.loads(resource_attrs)
                # 尝试从pod名称提取服务名
                pod_name = attrs_dict.get("k8s.pod.name", "")
                if pod_name:
                    # 假设格式为 service-name-xxx-xxx
                    parts = pod_name.split("-")
                    if len(parts) >= 2:
                        return "-".join(parts[:-2]) if len(parts) > 2 else parts[0]

                # 尝试其他字段
                return (
                    attrs_dict.get("service.name")
                    or attrs_dict.get("k8s.deployment.name")
                    or "unknown"
                )
        except Exception:
            pass
        return "unknown"
    @timeit()
    def calculate_thresholds(
        self, normal_metrics: pd.DataFrame, std_multiplier: float = 3.0
    ) -> Dict:
        """
        计算正常阶段各服务各指标的阈值

        Args:
            normal_metrics: 正常阶段的指标数据
            std_multiplier: 标准差倍数，用于设置阈值

        Returns:
            Dict: {service_name: {metric_name: {"mean": float, "std": float, "threshold": float}}}
        """
        thresholds = {}

        # 确保有ServiceName
        normal_metrics = self.extract_service_info(normal_metrics)

        # 按服务和指标分组计算
        for service_name, service_df in normal_metrics.groupby("ServiceName"):
            service_thresholds = {}

            for metric_name, metric_df in service_df.groupby("MetricName"):
                values = metric_df["Value"].dropna().values
                if len(values) > 2:  # 需要足够的样本
                    mean_val = np.mean(values)
                    std_val = np.std(values)
                    threshold = mean_val + std_multiplier * std_val

                    service_thresholds[metric_name] = {
                        "mean": float(mean_val),
                        "std": float(std_val),
                        "threshold": float(threshold),
                    }
                    logger.debug(
                        f"服务 {service_name} 指标 {metric_name}: 平均值={mean_val:.4f}, 标准差={std_val:.4f}, 阈值={threshold:.4f}"
                    )

            if service_thresholds:
                thresholds[service_name] = service_thresholds

        self.thresholds = thresholds
        logger.info(f"计算了 {len(thresholds)} 个服务的阈值")
        return thresholds

    def save_thresholds(
        self, output_dir: str = "D:/workspace/Nezha/metric_threshold"
    ) -> None:
        """保存阈值到CSV文件"""
        if not self.thresholds:
            logger.warning("没有阈值可保存")
            return

        os.makedirs(output_dir, exist_ok=True)

        for service_name, metrics in self.thresholds.items():
            file_path = os.path.join(output_dir, f"{service_name}.csv")

            # 准备数据
            metric_names = list(metrics.keys())
            means = [metrics[m]["mean"] for m in metric_names]
            stds = [metrics[m]["std"] for m in metric_names]
            thresholds = [metrics[m]["threshold"] for m in metric_names]

            # 创建DataFrame并保存
            df = pd.DataFrame(
                {
                    "MetricName": metric_names,
                    "Mean": means,
                    "Std": stds,
                    "Threshold": thresholds,
                }
            )

            df.to_csv(file_path, index=False)
            logger.info(f"保存服务 {service_name} 的阈值到 {file_path}")

    def load_thresholds(
        self, input_dir: str = "D:/workspace/Nezha/metric_threshold"
    ) -> Dict:
        """从CSV文件加载阈值"""
        thresholds = {}

        if not os.path.exists(input_dir):
            logger.warning(f"阈值目录不存在: {input_dir}")
            return thresholds

        for file_name in os.listdir(input_dir):
            if file_name.endswith(".csv"):
                service_name = file_name.replace(".csv", "")
                file_path = os.path.join(input_dir, file_name)

                try:
                    df = pd.read_csv(file_path)
                    service_thresholds = {}

                    for _, row in df.iterrows():
                        metric_name = row["MetricName"]
                        service_thresholds[metric_name] = {
                            "mean": row["Mean"],
                            "std": row["Std"],
                            "threshold": row["Threshold"],
                        }

                    thresholds[service_name] = service_thresholds
                    logger.debug(
                        f"加载服务 {service_name} 的阈值，包含 {len(service_thresholds)} 个指标"
                    )

                except Exception as e:
                    logger.error(f"加载阈值文件 {file_path} 失败: {e}")

        self.thresholds = thresholds
        logger.info(f"加载了 {len(thresholds)} 个服务的阈值")
        return thresholds
