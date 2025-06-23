"""
Log parsing and template mining for Nezha preprocessing.
This module handles the conversion of raw logs to structured event IDs using Drain3.
"""

import json
import re
from typing import Dict, Optional, Tuple
from loguru import logger

from drain3 import TemplateMiner
from drain3.file_persistence import FilePersistence
from drain3.template_miner_config import TemplateMinerConfig


class LogParser:
    """Handles log parsing using Drain3 template mining."""

    def __init__(
        self, config_file: str, persistence_file: str, profiling_enabled: bool = False
    ):
        """
        Initialize log parser with Drain3.

        Args:
            config_file: Path to Drain3 configuration file
            persistence_file: Path to template persistence file
            profiling_enabled: Whether to enable profiling
        """
        self.config_file = config_file
        self.persistence_file = persistence_file
        self.template_miner = self._initialize_template_miner(profiling_enabled)

    def _initialize_template_miner(self, profiling_enabled: bool) -> TemplateMiner:
        """Initialize Drain3 template miner."""
        # Load configuration
        config = TemplateMinerConfig()
        config.load(self.config_file)
        config.profiling_enabled = profiling_enabled

        # Setup persistence
        persistence = FilePersistence(self.persistence_file)

        # Create template miner
        template_miner = TemplateMiner(persistence, config=config)

        logger.info(f"Initialized template miner with config: {self.config_file}")
        return template_miner

    def parse_log(
        self, raw_log: str, pod: str, include_pod_in_template: bool = False
    ) -> int:
        """
        Parse a log message and return its cluster ID.

        Args:
            raw_log: Raw log message
            pod: Pod name that generated the log
            include_pod_in_template: Whether to include pod name in template

        Returns:
            Cluster ID assigned by Drain3
        """
        # Extract log message and service from raw log and pod
        log_message, service = self.extract_log_and_service(raw_log, pod)

        # Optionally include pod name for more specific clustering
        if include_pod_in_template:
            log_message = f"{log_message}_{pod}"

        # Process with Drain3
        result = self.template_miner.add_log_message(log_message)

        # Log template changes
        if result["change_type"] != "none":
            logger.debug(
                f"{service} | {result['change_type']} | {result['template_mined']}"
            )

        return result["cluster_id"]

    def get_template(self, cluster_id: int) -> str:
        """
        Get template string from cluster ID.

        Args:
            cluster_id: Drain3 cluster ID

        Returns:
            Template string, or empty string if not found
        """
        for cluster in self.template_miner.drain.clusters:
            if cluster.cluster_id == cluster_id:
                return cluster.get_template()

        logger.warning(f"Template not found for cluster ID: {cluster_id}")
        return ""

    def get_cluster_info(self, cluster_id: int) -> Optional[Dict]:
        """
        Get detailed information about a cluster.

        Args:
            cluster_id: Drain3 cluster ID

        Returns:
            Dictionary with cluster information or None if not found
        """
        for cluster in self.template_miner.drain.clusters:
            if cluster.cluster_id == cluster_id:
                return {
                    "cluster_id": cluster.cluster_id,
                    "template": cluster.get_template(),
                    "size": cluster.size,
                    "log_ids": getattr(cluster, "log_ids", []),
                }
        return None

    def get_all_templates(self) -> Dict[int, str]:
        """Get all templates as a dictionary mapping cluster_id -> template."""
        templates = {}
        for cluster in self.template_miner.drain.clusters:
            templates[cluster.cluster_id] = cluster.get_template()
        return templates

    def save_state(self) -> None:
        """Save the current state of the template miner."""
        self.template_miner.save_state("manual_save")
        logger.info("Template miner state saved")

    def get_statistics(self) -> Dict:
        """Get statistics about parsed logs."""
        total_clusters = len(self.template_miner.drain.clusters)
        total_messages = sum(
            cluster.size for cluster in self.template_miner.drain.clusters
        )

        return {
            "total_clusters": total_clusters,
            "total_messages": total_messages,
            "avg_messages_per_cluster": total_messages / total_clusters
            if total_clusters > 0
            else 0,
        }

    @staticmethod
    def extract_log_and_service(raw_log: str, pod: str) -> Tuple[str, str]:
        """
        Extract clean log message and service name from raw log and pod.

        Args:
            raw_log: Raw log content (may be JSON)
            pod: Pod name

        Returns:
            Tuple of (clean_log_message, service_name)
        """
        # Extract service name from pod
        service = LogParser._extract_service_from_pod(pod)

        # Handle special case for alarm logs
        if "alarm" in pod.lower():
            return raw_log.strip(), "alarm"

        # Parse log message from JSON or return as-is
        log_message = LogParser._parse_log_message(raw_log, service)

        return log_message.strip(), service

    @staticmethod
    def _extract_service_from_pod(pod: str) -> str:
        """Extract service name from pod name."""
        # Common service patterns for microservices
        service_patterns = [
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
        ]

        pod_lower = pod.lower()

        # Check for known service patterns
        for service in service_patterns:
            if service in pod_lower:
                return service

        # Handle train-ticket services (ts- prefix)
        if pod.startswith("ts-"):
            # Extract service name between hyphens
            parts = pod.split("-")
            if len(parts) >= 2:
                return "-".join(parts[:2])  # e.g., "ts-service"

        # Fallback: extract first part before hyphen
        parts = pod.split("-")
        if len(parts) > 0:
            return parts[0]

        return "unknown"

    @staticmethod
    def _parse_log_message(raw_log: str, service: str) -> str:
        """Parse log message from potentially JSON-formatted log."""
        try:
            # Try to parse as JSON
            if raw_log.strip().startswith("{") and raw_log.strip().endswith("}"):
                log_data = json.loads(raw_log)

                # Different services have different JSON structures
                if service in [
                    "checkoutservice",
                    "currencyservice",
                    "emailservice",
                    "frontend",
                    "paymentservice",
                    "productcatalogservice",
                    "recommendationservice",
                    "shippingservice",
                ]:
                    # Nested JSON structure: {"log": "{"message": "..."}", ...}
                    inner_log = log_data.get("log", raw_log)
                    if isinstance(inner_log, str) and inner_log.startswith("{"):
                        inner_data = json.loads(inner_log)
                        return inner_data.get("message", inner_log)
                    return inner_log

                elif service in ["adservice", "cartservice"]:
                    # Simple JSON structure: {"log": "message", ...}
                    return log_data.get("log", raw_log)

                # Train-ticket services
                elif service.startswith("ts-"):
                    log_content = log_data.get("log", raw_log)
                    # Extract content between specific patterns
                    if isinstance(log_content, str):
                        # Pattern: "  content " or " content "
                        match = re.search(r"  (.+?#.+?) ", log_content)
                        if not match:
                            match = re.search(r" (.+?#.+?) ", log_content)
                        if match:
                            return match.group(1)
                    return log_content

                # Default: try "log" field
                return log_data.get("log", raw_log)

            # Not JSON, return as-is
            return raw_log

        except json.JSONDecodeError:
            # JSON parsing failed, return original
            return raw_log
        except Exception as e:
            logger.warning(f"Error parsing log message: {e}")
            return raw_log
