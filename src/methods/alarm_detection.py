"""
Alarm detection methods for identifying anomalies in metrics.
This module provides generic alarm detection algorithms independent of specific metrics.
"""

from typing import List, Dict, Optional, Callable
from loguru import logger

from ..common.types import MetricData, AlarmEvent


class AlarmDetector:
    """Generic alarm detection algorithms."""

    def __init__(
        self,
        detection_method: str = "threshold",
        cpu_threshold: float = 80.0,
        memory_threshold: float = 80.0,
        network_threshold: float = 1000.0,
    ):
        """
        Initialize alarm detector.

        Args:
            detection_method: Detection method ("threshold", "statistical", "custom")
            cpu_threshold: CPU usage threshold (percentage)
            memory_threshold: Memory usage threshold (percentage)
            network_threshold: Network latency threshold (ms)
        """
        self.detection_method = detection_method
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold
        self.network_threshold = network_threshold
        self.custom_detectors: Dict[str, Callable] = {}

    def detect_alarms(
        self,
        metrics: List[MetricData],
        namespace: str,
        thresholds: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> List[AlarmEvent]:
        """
        Detect alarms from metric data.

        Args:
            metrics: List of metric data
            namespace: Namespace for context-specific detection
            thresholds: Custom thresholds per service

        Returns:
            List of detected alarms
        """
        logger.info(
            f"Detecting alarms from {len(metrics)} metrics for namespace {namespace}"
        )

        alarms = []

        for metric in metrics:
            metric_alarms = self._detect_metric_alarms(metric, namespace, thresholds)
            alarms.extend(metric_alarms)

        logger.info(f"Detected {len(alarms)} alarms")
        return alarms

    def _detect_metric_alarms(
        self,
        metric: MetricData,
        namespace: str,
        thresholds: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> List[AlarmEvent]:
        """Detect alarms for a single metric data point."""
        alarms = []

        # Get service-specific thresholds if available
        service_thresholds = {}
        if thresholds and metric.service in thresholds:
            service_thresholds = thresholds[metric.service]

        # CPU alarm detection
        cpu_alarm = self._detect_cpu_alarm(metric, namespace, service_thresholds)
        if cpu_alarm:
            alarms.append(cpu_alarm)

        # Memory alarm detection
        memory_alarm = self._detect_memory_alarm(metric, namespace, service_thresholds)
        if memory_alarm:
            alarms.append(memory_alarm)

        # Network alarm detection
        network_alarm = self._detect_network_alarm(
            metric, namespace, service_thresholds
        )
        if network_alarm:
            alarms.append(network_alarm)

        # Custom metric alarms
        custom_alarms = self._detect_custom_metric_alarms(
            metric, namespace, service_thresholds
        )
        alarms.extend(custom_alarms)

        return alarms

    def _detect_cpu_alarm(
        self, metric: MetricData, namespace: str, service_thresholds: Dict[str, float]
    ) -> Optional[AlarmEvent]:
        """Detect CPU usage alarm."""
        if self.detection_method == "threshold":
            threshold = service_thresholds.get("cpu", self.cpu_threshold)

            if metric.cpu_usage > threshold:
                return AlarmEvent(
                    pod=metric.pod,
                    service=metric.service,
                    metric_type="Cpu",
                    metric_value=metric.cpu_usage,
                    threshold=threshold,
                    timestamp=metric.timestamp,
                    severity="warning"
                    if metric.cpu_usage < threshold * 1.2
                    else "critical",
                )

        elif self.detection_method == "statistical":
            return self._statistical_detection(
                metric, "cpu_usage", "Cpu", service_thresholds
            )

        return None

    def _detect_memory_alarm(
        self, metric: MetricData, namespace: str, service_thresholds: Dict[str, float]
    ) -> Optional[AlarmEvent]:
        """Detect memory usage alarm."""
        if self.detection_method == "threshold":
            threshold = service_thresholds.get("memory", self.memory_threshold)

            if metric.memory_usage > threshold:
                return AlarmEvent(
                    pod=metric.pod,
                    service=metric.service,
                    metric_type="Memory",
                    metric_value=metric.memory_usage,
                    threshold=threshold,
                    timestamp=metric.timestamp,
                    severity="warning"
                    if metric.memory_usage < threshold * 1.2
                    else "critical",
                )

        elif self.detection_method == "statistical":
            return self._statistical_detection(
                metric, "memory_usage", "Memory", service_thresholds
            )

        return None

    def _detect_network_alarm(
        self, metric: MetricData, namespace: str, service_thresholds: Dict[str, float]
    ) -> Optional[AlarmEvent]:
        """Detect network latency alarm."""
        if metric.network_latency <= 0:
            return None

        if self.detection_method == "threshold":
            # Use namespace-specific thresholds
            if namespace == "hipster":
                default_threshold = 200.0
            elif namespace == "ts":
                default_threshold = 300.0
            else:
                default_threshold = self.network_threshold

            threshold = service_thresholds.get("network", default_threshold)

            if metric.network_latency > threshold:
                return AlarmEvent(
                    pod=metric.pod,
                    service=metric.service,
                    metric_type="Network",
                    metric_value=metric.network_latency,
                    threshold=threshold,
                    timestamp=metric.timestamp,
                    severity="warning"
                    if metric.network_latency < threshold * 1.5
                    else "critical",
                )

        elif self.detection_method == "statistical":
            return self._statistical_detection(
                metric, "network_latency", "Network", service_thresholds
            )

        return None

    def _detect_custom_metric_alarms(
        self, metric: MetricData, namespace: str, service_thresholds: Dict[str, float]
    ) -> List[AlarmEvent]:
        """Detect alarms for custom metrics."""
        alarms = []

        for metric_name, value in metric.custom_metrics.items():
            if isinstance(value, (int, float)):
                # Check if we have a custom detector for this metric
                if metric_name in self.custom_detectors:
                    alarm = self.custom_detectors[metric_name](
                        metric, value, service_thresholds
                    )
                    if alarm:
                        alarms.append(alarm)

                # Default threshold check
                elif metric_name in service_thresholds:
                    threshold = service_thresholds[metric_name]
                    if value > threshold:
                        alarm = AlarmEvent(
                            pod=metric.pod,
                            service=metric.service,
                            metric_type=metric_name,
                            metric_value=float(value),
                            threshold=threshold,
                            timestamp=metric.timestamp,
                            severity="warning",
                        )
                        alarms.append(alarm)

        return alarms

    def _statistical_detection(
        self,
        metric: MetricData,
        metric_field: str,
        metric_type: str,
        service_thresholds: Dict[str, float],
    ) -> Optional[AlarmEvent]:
        """Statistical anomaly detection using mean + k*std."""
        # This would need historical data for proper statistical detection
        # For now, return None as placeholder
        logger.debug(f"Statistical detection not implemented for {metric_type}")
        return None

    def register_custom_detector(
        self,
        metric_name: str,
        detector_function: Callable[
            [MetricData, float, Dict[str, float]], Optional[AlarmEvent]
        ],
    ) -> None:
        """
        Register a custom detector for a specific metric.

        Args:
            metric_name: Name of the metric
            detector_function: Function that takes (metric, value, thresholds) and returns AlarmEvent or None
        """
        self.custom_detectors[metric_name] = detector_function
        logger.info(f"Registered custom detector for metric: {metric_name}")

    def load_thresholds_from_dict(
        self, threshold_config: Dict[str, Dict[str, float]]
    ) -> Dict[str, Dict[str, float]]:
        """
        Load and validate threshold configuration.

        Args:
            threshold_config: Service -> metric -> threshold mapping

        Returns:
            Validated threshold configuration
        """
        validated_config = {}

        for service, metrics in threshold_config.items():
            validated_config[service] = {}

            for metric, threshold in metrics.items():
                if isinstance(threshold, (int, float)) and threshold > 0:
                    validated_config[service][metric] = float(threshold)
                else:
                    logger.warning(
                        f"Invalid threshold for {service}.{metric}: {threshold}"
                    )

        logger.info(f"Loaded thresholds for {len(validated_config)} services")
        return validated_config

    def calculate_dynamic_thresholds(
        self, historical_metrics: List[MetricData], multiplier: float = 2.0
    ) -> Dict[str, Dict[str, float]]:
        """
        Calculate dynamic thresholds based on historical data.

        Args:
            historical_metrics: Historical metric data
            multiplier: Standard deviation multiplier

        Returns:
            Service -> metric -> threshold mapping
        """
        import statistics
        from collections import defaultdict

        service_metrics = defaultdict(lambda: defaultdict(list))

        # Group metrics by service
        for metric in historical_metrics:
            service_metrics[metric.service]["cpu"].append(metric.cpu_usage)
            service_metrics[metric.service]["memory"].append(metric.memory_usage)
            if metric.network_latency > 0:
                service_metrics[metric.service]["network"].append(
                    metric.network_latency
                )

        # Calculate thresholds
        thresholds = {}

        for service, metrics in service_metrics.items():
            thresholds[service] = {}

            for metric_name, values in metrics.items():
                if len(values) > 1:
                    mean = statistics.mean(values)
                    stdev = statistics.stdev(values)
                    threshold = mean + multiplier * stdev
                    thresholds[service][metric_name] = threshold
                else:
                    # Fallback to default thresholds
                    if metric_name == "cpu":
                        thresholds[service][metric_name] = self.cpu_threshold
                    elif metric_name == "memory":
                        thresholds[service][metric_name] = self.memory_threshold
                    elif metric_name == "network":
                        thresholds[service][metric_name] = self.network_threshold

        logger.info(f"Calculated dynamic thresholds for {len(thresholds)} services")
        return thresholds

    def set_detection_method(self, method: str) -> None:
        """Set the alarm detection method."""
        if method in ["threshold", "statistical", "custom"]:
            self.detection_method = method
            logger.info(f"Set detection method to: {method}")
        else:
            raise ValueError(f"Unknown detection method: {method}")

    def update_thresholds(
        self,
        cpu: Optional[float] = None,
        memory: Optional[float] = None,
        network: Optional[float] = None,
    ) -> None:
        """Update default thresholds."""
        if cpu is not None:
            self.cpu_threshold = cpu
        if memory is not None:
            self.memory_threshold = memory
        if network is not None:
            self.network_threshold = network

        logger.info(
            f"Updated thresholds: CPU={self.cpu_threshold}, "
            f"Memory={self.memory_threshold}, Network={self.network_threshold}"
        )
