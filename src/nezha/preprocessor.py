"""
Nezha Preprocessor - Data preprocessing using rcabench_platform components.

Handles data loading, event encoding, and preparation for Nezha algorithm.
"""

import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import polars as pl
from rcabench_platform.v2.logging import logger

from .data_structures import (
    EnhancedEventPattern,
    PatternSupport,
    ProcessingMetrics,
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
        self.event_manager = None
        self.encoder = None
        self.performance_thresholds = {}

        # Statistics
        self.processing_metrics = None

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

    def compute_span_depths(self, trace_spans_df: pl.DataFrame) -> Dict[str, int]:
        """
        Compute depth for each span based on parent-child relationships.

        Optimized implementation using precomputed children map and deque-based BFS.

        Args:
            trace_spans_df: DataFrame containing spans for a single trace

        Returns:
            Dictionary mapping span_id to depth (root=0)
        """
        from collections import defaultdict, deque

        span_depths: Dict[str, int] = {}

        if trace_spans_df.is_empty():
            return span_depths

        # Extract needed columns as Python lists (faster than iter_rows)
        cols = ["span_id", "parent_span_id", "service_name"]
        for c in cols:
            if c not in trace_spans_df.columns:
                # Missing critical column; return empty depths
                return {}

        span_ids = trace_spans_df.get_column("span_id").to_list()
        parent_ids = (
            trace_spans_df.get_column("parent_span_id").to_list()
            if "parent_span_id" in trace_spans_df.columns
            else [None] * len(span_ids)
        )
        service_names = trace_spans_df.get_column("service_name").to_list()

        # Build children map in O(n)
        children_map: Dict[Optional[str], List[str]] = defaultdict(list)
        for sid, pid in zip(span_ids, parent_ids):
            if pid and pid != "":
                children_map[pid].append(sid)

        # Identify roots: loadgenerator with no parent
        roots: List[str] = []
        for sid, pid, sname in zip(span_ids, parent_ids, service_names):
            if sname == "loadgenerator" and (not pid or pid == ""):
                roots.append(sid)
                span_depths[sid] = 0

        # BFS from each root
        dq: deque = deque((root, 0) for root in roots)
        while dq:
            current_span, current_depth = dq.popleft()
            for child in children_map.get(current_span, []):
                if child not in span_depths:
                    depth = current_depth + 1
                    span_depths[child] = depth
                    dq.append((child, depth))

        # Any remaining spans (no reachable root), set depth 0
        for sid in span_ids:
            if sid not in span_depths:
                span_depths[sid] = 0

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

        # Ensure dependencies are initialized
        assert self.event_manager is not None, "Event manager not initialized"

        # Build event to span/service mapping using event manager (vectorized extraction)
        event_to_span: Dict[int, str] = {}
        event_to_service: Dict[int, str] = {}

        needed_cols = ["service_name", "span_name", "span_id"]
        if all(c in trace_spans_df.columns for c in needed_cols):
            svc = trace_spans_df.get_column("service_name").to_list()
            sname = trace_spans_df.get_column("span_name").to_list()
            sid = trace_spans_df.get_column("span_id").to_list()

            get_start = self.event_manager.get_span_start_id
            get_end = self.event_manager.get_span_end_id
            for service_name, span_name, span_id in zip(svc, sname, sid):
                service_span_name = f"{service_name}_{span_name}"
                span_start_id = get_start(service_span_name)
                span_end_id = get_end(service_span_name)
                event_to_span[span_start_id] = span_id
                event_to_span[span_end_id] = span_id
                event_to_service[span_start_id] = service_name
                event_to_service[span_end_id] = service_name

        # Add log events to mapping if available
        if trace_logs_df is not None and not trace_logs_df.is_empty():
            cols = ["attr.template_id", "span_id", "service_name"]
            if all(c in trace_logs_df.columns for c in cols):
                tids = trace_logs_df.get_column("attr.template_id").to_list()
                lsid = trace_logs_df.get_column("span_id").to_list()
                lsvc = trace_logs_df.get_column("service_name").to_list()
                get_log_id = self.event_manager.get_log_event_id
                for template_id, span_id, service_name in zip(tids, lsid, lsvc):
                    if template_id and span_id and service_name:
                        log_event_id = get_log_id(template_id)
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

            pattern_info[pattern_key] = {
                "depth": pattern_depth,
                "service": pattern_service_name,  # Use service name directly
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

        # Get trace ID (fast path)
        trace_id = trace_df.get_column("trace_id")[0]
        if not trace_id:
            return None

        # Use our enhanced encoder to get event pairs with frequencies
        assert self.encoder is not None, "Encoder not initialized"
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

        # Calculate performance score (vectorized)
        if (
            "service_name" in trace_df.columns
            and "span_name" in trace_df.columns
            and "duration" in trace_df.columns
        ):
            df = trace_df.select(
                [
                    (pl.col("service_name") + pl.lit("_") + pl.col("span_name")).alias(
                        "svc_span"
                    ),
                    (pl.col("duration").fill_null(0) / 1_000_000).alias("duration_ms"),
                ]
            )

            # Map thresholds via Python dict (small per-trace set, acceptable)
            thresholds_ms = [
                (self.performance_thresholds.get(svc_span, 0) or 0) / 1_000_000
                for svc_span in df.get_column("svc_span").to_list()
            ]
            df = df.with_columns(pl.Series(name="threshold_ms", values=thresholds_ms))

            df = df.with_columns(
                (
                    pl.when(
                        (pl.col("threshold_ms") > 0)
                        & (pl.col("duration_ms") > pl.col("threshold_ms"))
                    )
                    .then(pl.col("duration_ms") / pl.col("threshold_ms"))
                    .otherwise(0.0)
                ).alias("ratio")
            )

            df = df.with_columns(
                pl.when(pl.col("ratio") >= 5.0)
                .then(3.0)
                .when(pl.col("ratio") >= 3.0)
                .then(2.0)
                .when(pl.col("ratio") >= 1.5)
                .then(1.0)
                .otherwise(0.0)
                .alias("score")
            )
            performance_score = float(df.get_column("score").sum())
        else:
            performance_score = 0.0

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
