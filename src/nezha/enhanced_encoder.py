"""
Enhanced Event Encoder for Nezha

Extends rcabench_platform's event encoding with frequency counting support.
"""

from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

import polars as pl
from rcabench_platform.v2.logging import logger
from rcabench_platform.v2.samplers.event_encoding import EventEncoder, EventIDManager


class NezhaEventEncoder(EventEncoder):
    """
    Enhanced event encoder that returns pattern frequencies instead of just sets.

    Extends rcabench_platform's EventEncoder to support frequency counting
    for Nezha's enhanced pattern representation.
    """

    def encode_trace_events_with_frequency(
        self, trace_spans_df: pl.DataFrame, trace_logs_df: Optional[pl.DataFrame] = None
    ) -> Dict[Tuple[int, int], int]:
        """
        Encode a single trace into event pairs with frequency counts.

        Args:
            trace_spans_df: DataFrame containing spans for one trace
            trace_logs_df: Optional DataFrame containing logs for the trace

        Returns:
            Dictionary mapping event pairs to their frequency counts
        """
        # Get basic event pairs from parent class
        event_pairs_set = super().encode_trace_events(trace_spans_df, trace_logs_df)

        # For now, since the parent returns a set, each pattern has frequency 1
        # But we implement the frequency structure for future enhancements
        event_pair_frequencies = {}
        for pair in event_pairs_set:
            event_pair_frequencies[pair] = 1

        return event_pair_frequencies

    def encode_trace_events_detailed(
        self, trace_spans_df: pl.DataFrame, trace_logs_df: Optional[pl.DataFrame] = None
    ) -> Dict[Tuple[int, int], int]:
        """
        Detailed encoding that actually counts frequencies within a trace.

        This method reimplements the encoding logic to properly count
        how many times each event transition occurs within a single trace.
        """
        # Check for root span
        root_spans_df = trace_spans_df.filter(
            (pl.col("service_name") == "loadgenerator")
            & (pl.col("parent_span_id").is_null() | (pl.col("parent_span_id") == ""))
        )

        if root_spans_df.height == 0:
            logger.debug("No loadgenerator root span found, skipping trace")
            return {}

        # Build span hierarchy
        spans_data = {}
        children_map = defaultdict(list)

        for row in trace_spans_df.iter_rows(named=True):
            span_id = row["span_id"]
            parent_id = row.get("parent_span_id")

            spans_data[span_id] = row

            if parent_id and parent_id != "":
                children_map[parent_id].append(span_id)

        # Prepare log events by span
        log_events_by_span = defaultdict(list)
        if trace_logs_df is not None and len(trace_logs_df) > 0:
            for row in trace_logs_df.iter_rows(named=True):
                template_id = row.get("attr.template_id")
                if template_id is not None:
                    span_id = row.get("span_id")
                    timestamp = row.get("time")
                    log_event_id = self.event_manager.get_log_event_id(template_id)

                    if span_id:
                        log_events_by_span[span_id].append((log_event_id, timestamp))

            # Sort log events within each span by timestamp
            for span_id in log_events_by_span:
                log_events_by_span[span_id].sort(key=lambda x: x[1])

        # Count event pair frequencies
        event_pair_counter = Counter()

        # 1. Generate span internal event pairs with frequencies
        for span_id, span_data in spans_data.items():
            service_span_name = f"{span_data['service_name']}_{span_data['span_name']}"
            span_start_id = self.event_manager.get_span_start_id(service_span_name)
            span_end_id = self.event_manager.get_span_end_id(service_span_name)

            # Build internal event sequence for this span
            span_events = [span_start_id]  # Start with span start

            # Add log events (sorted by timestamp)
            if span_id in log_events_by_span:
                for log_event_id, _ in log_events_by_span[span_id]:
                    span_events.append(log_event_id)

            # Add status error event (if applicable)
            if span_data.get("attr.status_code") == "Error":
                error_event_id = self.event_manager.get_special_event_id("status_error")
                span_events.append(error_event_id)

            # Add performance degradation event (if applicable)
            duration = span_data.get("duration", 0)
            p90_threshold = self.performance_thresholds.get(service_span_name)
            if p90_threshold and duration > p90_threshold:
                perf_event_id = self.event_manager.get_special_event_id(
                    "perf_degradation"
                )
                span_events.append(perf_event_id)

            # End with span end
            span_events.append(span_end_id)

            # Extract and count internal pairs for this span
            span_pairs = self._extract_event_pairs_with_frequency(span_events)
            event_pair_counter.update(span_pairs)

        # 2. Generate span relation event pairs (parent end -> child start)
        for parent_id, children in children_map.items():
            if parent_id in spans_data:
                parent_data = spans_data[parent_id]
                parent_service_span = (
                    f"{parent_data['service_name']}_{parent_data['span_name']}"
                )
                parent_end_id = self.event_manager.get_span_end_id(parent_service_span)

                for child_id in children:
                    if child_id in spans_data:
                        child_data = spans_data[child_id]
                        child_service_span = (
                            f"{child_data['service_name']}_{child_data['span_name']}"
                        )
                        child_start_id = self.event_manager.get_span_start_id(
                            child_service_span
                        )

                        # Add parent->child transition
                        transition_pair = (parent_end_id, child_start_id)
                        event_pair_counter[transition_pair] += 1

        return dict(event_pair_counter)

    def _extract_event_pairs_with_frequency(self, event_ids: List[int]) -> Counter:
        """
        Extract consecutive event pairs with frequency counting.

        Args:
            event_ids: List of event IDs in sequence

        Returns:
            Counter object with event pair frequencies
        """
        if len(event_ids) < 2:
            return Counter()

        pairs = []
        for i in range(len(event_ids) - 1):
            pairs.append((event_ids[i], event_ids[i + 1]))

        return Counter(pairs)


class NezhaEventIDManager(EventIDManager):
    """
    Enhanced Event ID Manager for Nezha with additional utility methods.
    """

    def get_event_type(self, event_id: int) -> str:
        """
        Get the type of an event based on its ID range.

        Args:
            event_id: Event ID to classify

        Returns:
            Event type string
        """
        if self.SPAN_START_BEGIN <= event_id <= self.SPAN_START_END:
            return "span_start"
        elif self.SPAN_END_BEGIN <= event_id <= self.SPAN_END_END:
            return "span_end"
        elif self.SPECIAL_EVENT_START <= event_id < self.LOG_TEMPLATE_START:
            return "special_event"
        elif event_id >= self.LOG_TEMPLATE_START:
            return "log_template"
        else:
            return "unknown"

    def get_event_description(self, event_id: int) -> str:
        """
        Get human-readable description of an event.

        Args:
            event_id: Event ID to describe

        Returns:
            Human-readable description
        """
        event_type = self.get_event_type(event_id)

        if event_type == "span_start":
            # Find the service_span_name for this ID
            for service_span_name, id_val in self.span_start_to_id.items():
                if id_val == event_id:
                    return f"START: {service_span_name}"
            return f"START: ID_{event_id}"

        elif event_type == "span_end":
            # Find the service_span_name for this ID
            for service_span_name, id_val in self.span_end_to_id.items():
                if id_val == event_id:
                    return f"END: {service_span_name}"
            return f"END: ID_{event_id}"

        elif event_type == "special_event":
            # Find the special event type
            for event_name, id_val in self.special_event_to_id.items():
                if id_val == event_id:
                    return f"SPECIAL: {event_name}"
            return f"SPECIAL: ID_{event_id}"

        elif event_type == "log_template":
            # Find the template ID
            for template_id, id_val in self.log_template_to_id.items():
                if id_val == event_id:
                    return f"LOG: template_{template_id}"
            return f"LOG: ID_{event_id}"

        else:
            return f"UNKNOWN: ID_{event_id}"

    def get_template_id_for_log_event(self, event_id: int) -> Optional[str]:
        """
        Get the original template ID for a log event.

        Args:
            event_id: Log event ID

        Returns:
            Original template ID or None
        """
        for template_id, id_val in self.log_template_to_id.items():
            if id_val == event_id:
                return template_id
        return None
