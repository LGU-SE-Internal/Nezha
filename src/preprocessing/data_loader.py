"""
Data loading utilities for Nezha preprocessing.
This module handles loading and parsing of trace, log, and metric data files.
"""

import pandas as pd
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from loguru import logger

from ..common.types import TimeWindow, MetricData
from datetime import datetime


class DataLoader:
    """Handles loading of trace, log, and metric data files."""

    def __init__(self, data_root_path: str):
        """
        Initialize data loader.

        Args:
            data_root_path: Root path to data directory
        """
        self.data_root_path = Path(data_root_path)

    def load_time_window_data(
        self, time_window: TimeWindow
    ) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], List[str], List[str]]:
        """
        Load all data files for a specific time window.

        Args:
            time_window: Time window specification

        Returns:
            Tuple of (trace_df, log_df, trace_ids, missing_files)
        """
        file_paths = self._get_file_paths(time_window)
        missing_files = []

        # Load trace data
        trace_df = None
        if file_paths["trace"].exists():
            try:
                trace_df = self.load_trace_data(str(file_paths["trace"]))
                logger.info(f"Loaded trace data: {len(trace_df)} records")
            except Exception as e:
                logger.error(f"Error loading trace data: {e}")
                missing_files.append("trace")
        else:
            missing_files.append("trace")

        # Load log data
        log_df = None
        if file_paths["log"].exists():
            try:
                log_df = self.load_log_data(str(file_paths["log"]))
                logger.info(f"Loaded log data: {len(log_df)} records")
            except Exception as e:
                logger.error(f"Error loading log data: {e}")
                missing_files.append("log")
        else:
            missing_files.append("log")

        # Load trace IDs
        trace_ids = []
        if file_paths["trace_id"].exists():
            try:
                trace_ids = self.load_trace_ids(str(file_paths["trace_id"]))
                logger.info(f"Loaded {len(trace_ids)} trace IDs")
            except Exception as e:
                logger.error(f"Error loading trace IDs: {e}")
                missing_files.append("trace_id")
        else:
            missing_files.append("trace_id")

        return trace_df, log_df, trace_ids, missing_files

    def load_trace_data(self, file_path: str) -> pd.DataFrame:
        """
        Load trace data from CSV file.

        Args:
            file_path: Path to trace CSV file

        Returns:
            DataFrame with trace data
        """
        required_columns = [
            "TraceID",
            "SpanID",
            "ParentID",
            "PodName",
            "StartTimeUnixNano",
            "EndTimeUnixNano",
            "OperationName",
        ]

        df = pd.read_csv(file_path, engine="c")

        # Validate required columns
        missing_cols = [col for col in required_columns if col not in df.columns]
        if missing_cols:
            logger.warning(f"Missing columns in trace data: {missing_cols}")

        # Set TraceID as index for faster lookups
        if "TraceID" in df.columns:
            df = df.set_index("TraceID")

        return df

    def load_log_data(self, file_path: str) -> pd.DataFrame:
        """
        Load log data from CSV file.

        Args:
            file_path: Path to log CSV file

        Returns:
            DataFrame with log data
        """
        required_columns = ["SpanID", "TimeUnixNano", "Log"]

        df = pd.read_csv(file_path, engine="c")

        # Validate required columns
        missing_cols = [col for col in required_columns if col not in df.columns]
        if missing_cols:
            logger.warning(f"Missing columns in log data: {missing_cols}")

        # Set SpanID as index for faster lookups
        if "SpanID" in df.columns:
            df = df.set_index("SpanID")

        return df

    def load_trace_ids(self, file_path: str) -> List[str]:
        """
        Load trace IDs from CSV file.

        Args:
            file_path: Path to trace ID CSV file

        Returns:
            List of trace IDs
        """
        df = pd.read_csv(file_path, header=None, engine="c")

        # Assume trace IDs are in the first column
        if len(df.columns) > 0:
            trace_ids = df.iloc[:, 0].astype(str).tolist()
            return trace_ids

        logger.warning(f"No trace IDs found in {file_path}")
        return []

    def load_metric_data(
        self, time_window: TimeWindow, target_timestamp: Optional[str] = None
    ) -> List[MetricData]:
        """
        Load metric data for a specific time window.

        Args:
            time_window: Time window specification
            target_timestamp: Specific timestamp to filter for

        Returns:
            List of MetricData objects
        """
        metric_dir = self.data_root_path / time_window.date / "metric"

        if not metric_dir.exists():
            logger.warning(f"Metric directory not found: {metric_dir}")
            return []

        metrics = []

        # Find metric files matching the time pattern
        pattern = f"*{time_window.hour}_{time_window.minute}*metric*.csv"
        metric_files = list(metric_dir.glob(pattern))

        if not metric_files:
            # Try alternative patterns
            pattern = "*metric*.csv"
            metric_files = list(metric_dir.glob(pattern))

        for metric_file in metric_files:
            try:
                file_metrics = self._parse_metric_file(
                    metric_file, target_timestamp, time_window
                )
                metrics.extend(file_metrics)
            except Exception as e:
                logger.warning(f"Error parsing metric file {metric_file}: {e}")

        logger.info(f"Loaded {len(metrics)} metric data points")
        return metrics

    def _parse_metric_file(
        self,
        metric_file: Path,
        target_timestamp: Optional[str],
        time_window: TimeWindow,
    ) -> List[MetricData]:
        """Parse a single metric file."""
        df = pd.read_csv(metric_file)
        metrics = []

        # Extract pod name from filename
        pod_name = self._extract_pod_from_filename(metric_file.name)
        service_name = self._extract_service_from_pod(pod_name)

        for _, row in df.iterrows():
            # Filter by timestamp if specified
            if target_timestamp:
                row_time = row.get("Time", row.get("TimeStamp", ""))
                if target_timestamp not in str(row_time):
                    continue

            # Create MetricData object
            metric = MetricData(
                pod=pod_name,
                service=service_name,
                timestamp=self._parse_timestamp(
                    row.get("Time", row.get("TimeStamp", "")), time_window
                ),
                cpu_usage=float(row.get("CpuUsageRate(%)", 0)),
                memory_usage=float(row.get("MemoryUsageRate(%)", 0)),
                network_latency=float(row.get("NetworkP90(ms)", 0)),
                syscall_read=int(row.get("SyscallRead", 0)),
                syscall_write=int(row.get("SyscallWrite", 0)),
            )

            # Add any additional columns as custom metrics
            for col in df.columns:
                if col not in [
                    "Time",
                    "TimeStamp",
                    "PodName",
                    "CpuUsageRate(%)",
                    "MemoryUsageRate(%)",
                    "NetworkP90(ms)",
                    "SyscallRead",
                    "SyscallWrite",
                ]:
                    try:
                        metric.custom_metrics[col] = float(row[col])
                    except (ValueError, TypeError):
                        metric.custom_metrics[col] = str(row[col])

            metrics.append(metric)

        return metrics

    def _get_file_paths(self, time_window: TimeWindow) -> Dict[str, Path]:
        """Get file paths for a time window."""
        base_path = self.data_root_path / time_window.date

        return {
            "trace": base_path
            / "trace"
            / f"{time_window.hour}_{time_window.minute}_trace.csv",
            "log": base_path
            / "log"
            / f"{time_window.hour}_{time_window.minute}_log.csv",
            "trace_id": base_path
            / "traceid"
            / f"{time_window.hour}_{time_window.minute}_traceid.csv",
        }

    def _extract_pod_from_filename(self, filename: str) -> str:
        """Extract pod name from metric filename."""
        # Remove file extension and metric suffix
        base_name = filename.replace(".csv", "").replace("_metric", "")

        # Split by underscore and take the first part (usually pod name)
        parts = base_name.split("_")
        if parts:
            return parts[0]

        return "unknown"

    def _extract_service_from_pod(self, pod_name: str) -> str:
        """Extract service name from pod name."""
        # Remove deployment hash suffix (e.g., "frontend-579b9bff58-t2dbm" -> "frontend")
        parts = pod_name.split("-")

        # Common patterns
        if len(parts) >= 2:
            # For most services: service-hash-id
            if parts[0] in [
                "adservice",
                "cartservice",
                "checkoutservice",
                "currencyservice",
                "emailservice",
                "frontend",
                "paymentservice",
                "productcatalogservice",
                "recommendationservice",
                "redis",
                "shippingservice",
            ]:
                return parts[0]

            # For train-ticket services: ts-service-hash-id
            if parts[0] == "ts" and len(parts) >= 3:
                return f"{parts[0]}-{parts[1]}"

        # Fallback
        return parts[0] if parts else "unknown"

    def _parse_timestamp(self, time_str: str, time_window: TimeWindow) -> datetime:
        """Parse timestamp string to datetime object."""
        try:
            # Try various timestamp formats
            if isinstance(time_str, str) and time_str:
                # ISO format
                if "T" in time_str:
                    return datetime.fromisoformat(time_str.replace("Z", "+00:00"))

                # Standard format
                if ":" in time_str:
                    return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")

            # Fallback: construct from time window
            return datetime.strptime(
                f"{time_window.date} {time_window.hour}:{time_window.minute}:00",
                "%Y-%m-%d %H:%M:%S",
            )

        except Exception as e:
            logger.warning(f"Error parsing timestamp '{time_str}': {e}")
            return datetime.now()

    def list_available_time_windows(self, date: str) -> List[TimeWindow]:
        """
        List all available time windows for a given date.

        Args:
            date: Date in YYYY-MM-DD format

        Returns:
            List of available TimeWindow objects
        """
        date_path = self.data_root_path / date

        if not date_path.exists():
            logger.warning(f"Date directory not found: {date_path}")
            return []

        trace_dir = date_path / "trace"
        if not trace_dir.exists():
            return []

        time_windows = []

        # Find all trace files and extract time windows
        for trace_file in trace_dir.glob("*_trace.csv"):
            name = trace_file.stem.replace("_trace", "")
            if "_" in name:
                hour, minute = name.split("_")
                time_window = TimeWindow(
                    start_time=f"{date} {hour}:{minute}",
                    date=date,
                    hour=hour,
                    minute=minute,
                )
                time_windows.append(time_window)

        return sorted(time_windows, key=lambda tw: (tw.hour, tw.minute))
