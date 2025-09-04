"""
Nezha Preprocessor - Data preprocessing using rcabench_platform components.

Handles data loading, event encoding, and preparation for Nezha algorithm.
"""

import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import polars as pl
from rcabench_platform.v2.logging import logger
from rcabench_platform.v2.samplers.event_encoding import EventEncoder, EventIDManager

from .data_structures import (
    EnhancedEventPattern,
    PatternSupport,
    ProcessingMetrics,
    ServiceMapping,
    TraceData,
)
from .enhanced_encoder import NezhaEventEncoder, NezhaEventIDManager


class NezhaPreprocessor:
    """
    Preprocessor for Nezha algorithm using rcabench_platform components.

    Integrates with rcabench_platform's event encoding system and adds
    enhanced pattern representation with depth and service information.
    """

    def __init__(self, input_folder: Path):
        """
        Initialize preprocessor.

        Args:
            input_folder: Path to input data folder containing traces and logs
        """
        self.input_folder = input_folder
        self.event_manager: Optional[EventIDManager] = None
        self.encoder: Optional[EventEncoder] = None
        self.service_mapping: Optional[ServiceMapping] = None
        self.performance_thresholds: Dict[str, float] = {}

        # Statistics
        self.processing_metrics: Optional[ProcessingMetrics] = None

    def initialize_encoding_system(self, traces_df: pl.DataFrame) -> None:
        """Initialize event encoding system from rcabench_platform."""
        logger.info("Initializing enhanced event encoding system...")

        # Initialize enhanced event manager and encoder
        self.event_manager = NezhaEventIDManager()
        self.encoder = NezhaEventEncoder(self.event_manager)

        # Extract span names and load performance thresholds
        self.event_manager.extract_span_names_from_traces(traces_df)
        self.encoder.load_performance_thresholds(self.input_folder)

        # Store performance thresholds
        self.performance_thresholds = self.encoder.performance_thresholds.copy()

        logger.info(f"Loaded {len(self.performance_thresholds)} performance thresholds")

    def create_service_mapping(self, traces_df: pl.DataFrame) -> ServiceMapping:
        """Create service name to ID mapping."""
        logger.info("Creating service mapping...")

        # Get unique service names
        service_names = traces_df.select("service_name").unique().to_series().to_list()

        # Create mapping
        self.service_mapping = ServiceMapping.create(service_names)

        logger.info(f"Created mapping for {len(service_names)} services")
        return self.service_mapping

    def compute_span_depths(self, trace_spans_df: pl.DataFrame) -> Dict[str, int]:
        """
        Compute depth for each span based on parent-child relationships.

        Args:
            trace_spans_df: DataFrame containing spans for a single trace

        Returns:
            Dictionary mapping span_id to depth (root=0)
        """
        span_depths = {}

        # Build parent-child mapping
        span_data = {}
        for row in trace_spans_df.iter_rows(named=True):
            span_id = row["span_id"]
            parent_id = row.get("parent_span_id")
            span_data[span_id] = {
                "parent_id": parent_id,
                "service_name": row["service_name"],
            }

        # Find root spans (loadgenerator with no parent)
        root_spans = []
        for span_id, data in span_data.items():
            if data["service_name"] == "loadgenerator" and (
                not data["parent_id"] or data["parent_id"] == ""
            ):
                root_spans.append(span_id)
                span_depths[span_id] = 0

        # BFS to compute depths
        queue = [(span_id, 0) for span_id in root_spans]

        while queue:
            current_span, current_depth = queue.pop(0)

            # Find children
            for span_id, data in span_data.items():
                if data["parent_id"] == current_span and span_id not in span_depths:
                    span_depths[span_id] = current_depth + 1
                    queue.append((span_id, current_depth + 1))

        # Assign depth 0 to spans without computed depth (isolated spans)
        for span_id in span_data:
            if span_id not in span_depths:
                span_depths[span_id] = 0

        return span_depths

    def enhance_event_pairs(
        self,
        event_pair_frequencies: Dict[Tuple[int, int], int],
        trace_spans_df: pl.DataFrame,
        trace_logs_df: Optional[pl.DataFrame] = None,
    ) -> List[EnhancedEventPattern]:
        """
        Convert event pair frequencies to enhanced patterns with depth and service info.

        Args:
            event_pair_frequencies: Dictionary mapping event pairs to their frequencies
            trace_spans_df: Spans data for the trace
            trace_logs_df: Optional logs data for the trace

        Returns:
            List of enhanced event patterns
        """
        if not event_pair_frequencies:
            return []

        # Compute span depths
        span_depths = self.compute_span_depths(trace_spans_df)

        # Build event to span mapping using event manager
        event_to_span = {}
        event_to_service = {}

        for row in trace_spans_df.iter_rows(named=True):
            service_name = row["service_name"]
            span_name = row["span_name"]
            span_id = row["span_id"]

            service_span_name = f"{service_name}_{span_name}"

            # Map event IDs to span and service
            span_start_id = self.event_manager.get_span_start_id(service_span_name)
            span_end_id = self.event_manager.get_span_end_id(service_span_name)

            event_to_span[span_start_id] = span_id
            event_to_span[span_end_id] = span_id
            event_to_service[span_start_id] = service_name
            event_to_service[span_end_id] = service_name

        # Add log events to mapping if available
        if trace_logs_df is not None:
            for row in trace_logs_df.iter_rows(named=True):
                template_id = row.get("attr.template_id")
                span_id = row.get("span_id")
                service_name = row.get("service_name")

                if template_id and span_id and service_name:
                    log_event_id = self.event_manager.get_log_event_id(template_id)
                    event_to_span[log_event_id] = span_id
                    event_to_service[log_event_id] = service_name

        # Add special events mapping (placeholder for context)
        for event_type in ["status_error", "perf_degradation"]:
            _ = self.event_manager.get_special_event_id(event_type)
            # Special events inherit from their context span - handled in pattern creation

        # Since event_pair_frequencies is a dict, we use the actual frequencies
        pattern_info = {}

        for (source_id, target_id), frequency in event_pair_frequencies.items():
            pattern_key = (source_id, target_id)

            # Determine depth and service for this pattern
            source_span = event_to_span.get(source_id, "")
            _ = event_to_span.get(
                target_id, ""
            )  # target_span unused but kept for clarity

            # Use source span depth as pattern depth
            pattern_depth = span_depths.get(source_span, 0)

            # Use source event service or fallback to target event service
            pattern_service_name = event_to_service.get(
                source_id
            ) or event_to_service.get(target_id, "unknown")

            pattern_service_id = self.service_mapping.get_service_id(
                pattern_service_name
            )

            pattern_info[pattern_key] = {
                "depth": pattern_depth,
                "service": pattern_service_id,
                "frequency": frequency,
            }

        # Create enhanced patterns with actual frequencies
        enhanced_patterns = []
        for pattern_key, info in pattern_info.items():
            enhanced_pattern = EnhancedEventPattern(
                pattern=pattern_key,
                count=info["frequency"],  # Use actual frequency
                depth=info["depth"],
                service=info["service"],
            )
            enhanced_patterns.append(enhanced_pattern)

        return enhanced_patterns

    def process_single_trace(
        self, trace_df: pl.DataFrame, logs_df: Optional[pl.DataFrame] = None
    ) -> Optional[TraceData]:
        """
        Process a single trace and return enhanced trace data.

        Args:
            trace_df: DataFrame containing spans for one trace
            logs_df: Optional DataFrame containing logs for the trace

        Returns:
            TraceData object or None if processing failed
        """
        if trace_df.is_empty():
            return None

        # Get trace ID
        trace_id = trace_df.select("trace_id").unique().item()
        if not trace_id:
            return None

        # Use our enhanced encoder to get event pairs with frequencies
        event_pair_frequencies = self.encoder.encode_trace_events_detailed(
            trace_df, logs_df
        )

        # Enhance event pairs with depth and service information
        enhanced_patterns = self.enhance_event_pairs(
            event_pair_frequencies, trace_df, logs_df
        )

        # Calculate trace metrics
        total_spans = trace_df.height
        error_count = trace_df.filter(pl.col("attr.status_code") == "Error").height

        # Calculate performance score
        performance_score = 0.0
        for row in trace_df.iter_rows(named=True):
            service_span_name = f"{row['service_name']}_{row['span_name']}"
            duration_ms = (row.get("duration", 0) or 0) / 1_000_000  # Convert to ms
            threshold_ms = (
                self.performance_thresholds.get(service_span_name, 0) / 1_000_000
            )

            if threshold_ms > 0 and duration_ms > threshold_ms:
                ratio = duration_ms / threshold_ms
                if ratio >= 5.0:
                    performance_score += 3.0
                elif ratio >= 3.0:
                    performance_score += 2.0
                elif ratio >= 1.5:
                    performance_score += 1.0

        # Determine root service
        root_service = "unknown"
        root_spans = trace_df.filter(
            (pl.col("service_name") == "loadgenerator")
            & (pl.col("parent_span_id").is_null() | (pl.col("parent_span_id") == ""))
        )
        if not root_spans.is_empty():
            root_service = "loadgenerator"

        return TraceData(
            trace_id=trace_id,
            enhanced_patterns=enhanced_patterns,
            root_service=root_service,
            total_spans=total_spans,
            error_count=error_count,
            performance_score=performance_score,
        )

    def process_all_traces(
        self, traces_df: pl.DataFrame, logs_df: Optional[pl.DataFrame] = None
    ) -> Tuple[List[TraceData], ProcessingMetrics]:
        """
        Process all traces and return enhanced trace data.

        Args:
            traces_df: DataFrame containing all trace data
            logs_df: Optional DataFrame containing all log data

        Returns:
            Tuple of (trace_data_list, processing_metrics)
        """
        start_time = time.time()
        logger.info("Starting trace processing...")

        # Initialize encoding system
        self.initialize_encoding_system(traces_df)

        # Create service mapping
        self.create_service_mapping(traces_df)

        # Group traces by trace_id
        trace_groups = traces_df.partition_by("trace_id", as_dict=True)

        # Group logs by trace_id if available
        log_groups = {}
        if logs_df is not None:
            log_groups = logs_df.partition_by("trace_id", as_dict=True)

        # Process each trace
        trace_data_list = []
        total_patterns = 0

        logger.info(f"Processing {len(trace_groups)} traces...")

        for (trace_id,), trace_df in trace_groups.items():
            if not trace_id:
                continue

            # Get logs for this trace
            trace_logs = log_groups.get((trace_id,), None)

            # Process trace
            trace_data = self.process_single_trace(trace_df, trace_logs)

            if trace_data:
                trace_data_list.append(trace_data)
                total_patterns += len(trace_data.enhanced_patterns)

        # Calculate unique patterns
        all_patterns = set()
        for trace_data in trace_data_list:
            for pattern in trace_data.enhanced_patterns:
                all_patterns.add(pattern.pattern)

        # Create processing metrics
        processing_time = time.time() - start_time
        self.processing_metrics = ProcessingMetrics(
            total_traces=len(trace_groups),
            processed_traces=len(trace_data_list),
            total_patterns=total_patterns,
            unique_patterns=len(all_patterns),
            processing_time_seconds=processing_time,
        )

        self.processing_metrics.log_summary()

        return trace_data_list, self.processing_metrics

    def load_and_process_data(
        self, need_logs: bool = True
    ) -> Tuple[List[TraceData], ProcessingMetrics]:
        """
        Load data from input folder and process it.

        Args:
            need_logs: Whether to load and process log data

        Returns:
            Tuple of (trace_data_list, processing_metrics)
        """
        # Load data from input folder and process it.
        # Note: rcabench_platform serde functions would be used if needed

        # Load traces (always needed)
        normal_traces = pl.read_parquet(self.input_folder / "normal_traces.parquet")
        abnormal_traces = pl.read_parquet(self.input_folder / "abnormal_traces.parquet")
        traces_df = pl.concat([normal_traces, abnormal_traces])

        logger.info(f"Loaded {len(traces_df)} trace records")

        # Load logs if needed
        logs_df = None
        if need_logs:
            try:
                normal_logs = pl.read_parquet(self.input_folder / "normal_logs.parquet")
                abnormal_logs = pl.read_parquet(
                    self.input_folder / "abnormal_logs.parquet"
                )
                logs_df = pl.concat([normal_logs, abnormal_logs])
                logger.info(f"Loaded {len(logs_df)} log records")
            except Exception as e:
                logger.warning(f"Failed to load logs: {e}")
                logs_df = None

        # Process all traces
        return self.process_all_traces(traces_df, logs_df)


def create_pattern_support(trace_data_list: List[TraceData]) -> PatternSupport:
    """
    Create pattern support structure from processed traces.

    Args:
        trace_data_list: List of processed trace data

    Returns:
        PatternSupport object with aggregated pattern information
    """
    support = PatternSupport()

    for trace_data in trace_data_list:
        for pattern in trace_data.enhanced_patterns:
            support.add_pattern(pattern)

    return support
