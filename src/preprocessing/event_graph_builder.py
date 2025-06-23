"""
Event graph construction for Nezha preprocessing.
This module handles the conversion of raw trace and log data into structured event graphs.
"""

import pandas as pd
from typing import List, Dict, Optional
from loguru import logger

from ..common.types import EventGraph, EventNode, AlarmEvent
from .log_parsing import LogParser


class EventGraphBuilder:
    """Builds event graphs from trace and log data."""

    def __init__(self, log_parser: LogParser):
        """
        Initialize event graph builder.

        Args:
            log_parser: Log parser for converting logs to event IDs
        """
        self.log_parser = log_parser

    def build_event_graphs(
        self,
        trace_df: pd.DataFrame,
        log_df: pd.DataFrame,
        trace_ids: List[str],
        alarms: List[AlarmEvent],
        namespace: str = "default",
    ) -> List[EventGraph]:
        """
        Build event graphs from trace and log data.

        Args:
            trace_df: DataFrame with trace data (indexed by TraceID)
            log_df: DataFrame with log data (indexed by SpanID)
            trace_ids: List of trace IDs to process
            alarms: List of alarm events to integrate
            namespace: Namespace for context-specific processing

        Returns:
            List of EventGraph objects
        """
        logger.info(f"Building event graphs for {len(trace_ids)} traces")

        event_graphs = []
        alarm_map = self._create_alarm_map(alarms)

        for trace_id in trace_ids:
            try:
                event_graph = self._build_single_event_graph(
                    trace_id, trace_df, log_df, alarm_map, namespace
                )

                if event_graph and event_graph.nodes:
                    event_graphs.append(event_graph)

            except Exception as e:
                logger.warning(f"Error building event graph for trace {trace_id}: {e}")
                continue

        logger.info(f"Successfully built {len(event_graphs)} event graphs")
        return event_graphs

    def _build_single_event_graph(
        self,
        trace_id: str,
        trace_df: pd.DataFrame,
        log_df: pd.DataFrame,
        alarm_map: Dict[str, List[AlarmEvent]],
        namespace: str,
    ) -> Optional[EventGraph]:
        """Build event graph for a single trace."""

        # Create event graph
        event_graph = EventGraph(trace_id=trace_id)

        try:
            # Get spans for this trace
            if trace_id not in trace_df.index:
                logger.debug(f"Trace {trace_id} not found in trace data")
                return None

            spans = trace_df.loc[[trace_id]]

            if len(spans) == 0:
                return None

            # Process each span
            span_nodes = {}  # span_id -> list of nodes

            for _, span_row in spans.iterrows():
                span_nodes_list = self._process_span(
                    span_row, log_df, alarm_map, namespace, event_graph
                )

                span_id = str(span_row["SpanID"])
                span_nodes[span_id] = span_nodes_list

            # Add inter-span relationships
            self._add_span_relationships(spans, span_nodes, event_graph)

            return event_graph

        except Exception as e:
            logger.error(f"Error processing trace {trace_id}: {e}")
            return None

    def _process_span(
        self,
        span_row: pd.Series,
        log_df: pd.DataFrame,
        alarm_map: Dict[str, List[AlarmEvent]],
        namespace: str,
        event_graph: EventGraph,
    ) -> List[EventNode]:
        """Process a single span and return its event nodes."""

        span_id = str(span_row["SpanID"])
        pod = str(span_row["PodName"])
        parent_id = (
            str(span_row["ParentID"]) if pd.notna(span_row["ParentID"]) else None
        )
        operation = str(span_row["OperationName"])
        start_time = int(span_row["StartTimeUnixNano"])
        end_time = int(span_row["EndTimeUnixNano"])

        # Extract service name
        service = self.log_parser.extract_log_and_service("", pod)[1]

        nodes = []

        # Create span start event
        start_log = f"{service} {operation} start"
        start_event_id = self.log_parser.parse_log(start_log, pod)

        start_node = EventNode(
            event_id=start_event_id,
            timestamp=start_time,
            pod=pod,
            service=service,
            span_id=span_id,
            parent_span_id=parent_id,
            event_type="span_start",
            raw_content=start_log,
        )

        event_graph.add_node(start_node)
        nodes.append(start_node)

        # Process logs within this span
        log_nodes = self._process_span_logs(span_id, log_df, pod, service, event_graph)
        nodes.extend(log_nodes)

        # Create span end event
        end_log = f"{service} {operation} end"
        end_event_id = self.log_parser.parse_log(end_log, pod)

        end_node = EventNode(
            event_id=end_event_id,
            timestamp=end_time,
            pod=pod,
            service=service,
            span_id=span_id,
            parent_span_id=parent_id,
            event_type="span_end",
            raw_content=end_log,
        )

        event_graph.add_node(end_node)
        nodes.append(end_node)

        # Add alarm events for this pod
        alarm_nodes = self._process_span_alarms(
            pod, start_time, alarm_map, namespace, event_graph
        )
        nodes.extend(alarm_nodes)

        # Sort all nodes by timestamp
        nodes.sort(key=lambda x: x.timestamp)

        # Add intra-span edges
        for i in range(len(nodes) - 1):
            event_graph.add_edge(nodes[i], nodes[i + 1])

        return nodes

    def _process_span_logs(
        self,
        span_id: str,
        log_df: pd.DataFrame,
        pod: str,
        service: str,
        event_graph: EventGraph,
    ) -> List[EventNode]:
        """Process logs within a span."""

        log_nodes = []

        try:
            if span_id not in log_df.index:
                return log_nodes

            logs = log_df.loc[[span_id]]

            for _, log_row in logs.iterrows():
                timestamp = int(log_row["TimeUnixNano"])
                raw_log = str(log_row["Log"])

                # Parse log to get event ID
                event_id = self.log_parser.parse_log(raw_log, pod)

                log_node = EventNode(
                    event_id=event_id,
                    timestamp=timestamp,
                    pod=pod,
                    service=service,
                    span_id=span_id,
                    event_type="log",
                    raw_content=raw_log,
                )

                event_graph.add_node(log_node)
                log_nodes.append(log_node)

        except Exception as e:
            logger.warning(f"Error processing logs for span {span_id}: {e}")

        return log_nodes

    def _process_span_alarms(
        self,
        pod: str,
        start_time: int,
        alarm_map: Dict[str, List[AlarmEvent]],
        namespace: str,
        event_graph: EventGraph,
    ) -> List[EventNode]:
        """Process alarm events for a pod."""

        alarm_nodes = []

        if pod not in alarm_map:
            return alarm_nodes

        alarms = alarm_map[pod]

        for i, alarm in enumerate(alarms):
            # Create alarm event
            alarm_event_id = self.log_parser.parse_log(alarm.metric_type, "alarm")

            # Place alarm event at span start + small offset
            alarm_timestamp = start_time + i + 1

            alarm_node = EventNode(
                event_id=alarm_event_id,
                timestamp=alarm_timestamp,
                pod=pod,
                service=alarm.service,
                span_id=None,  # Alarms don't belong to specific spans
                event_type="alarm",
                raw_content=f"{alarm.metric_type}:{alarm.metric_value}",
            )

            event_graph.add_node(alarm_node)
            alarm_nodes.append(alarm_node)

        return alarm_nodes

    def _add_span_relationships(
        self,
        spans: pd.DataFrame,
        span_nodes: Dict[str, List[EventNode]],
        event_graph: EventGraph,
    ) -> None:
        """Add relationships between spans (parent-child)."""

        # Create span ID to start node mapping
        span_start_nodes = {}
        for span_id, nodes in span_nodes.items():
            if nodes:
                # Find start node (first node with span_start type)
                start_node = next(
                    (node for node in nodes if node.event_type == "span_start"),
                    nodes[0],  # fallback to first node
                )
                span_start_nodes[span_id] = start_node

        # Add parent-child relationships
        for _, span_row in spans.iterrows():
            span_id = str(span_row["SpanID"])
            parent_id = (
                str(span_row["ParentID"]) if pd.notna(span_row["ParentID"]) else None
            )
            pod = str(span_row["PodName"])

            if parent_id and parent_id != "root" and parent_id in span_start_nodes:
                child_start = span_start_nodes.get(span_id)
                parent_spans = spans[spans["SpanID"] == parent_id]

                if len(parent_spans) > 0 and child_start:
                    parent_pod = str(parent_spans.iloc[0]["PodName"])

                    if parent_pod == pod:
                        # Same pod: find appropriate insertion point based on timestamp
                        parent_nodes = span_nodes.get(parent_id, [])
                        self._insert_child_span_same_pod(
                            parent_nodes, child_start, event_graph
                        )
                    else:
                        # Different pod: connect to parent start
                        parent_start = span_start_nodes.get(parent_id)
                        if parent_start:
                            event_graph.add_edge(parent_start, child_start)

    def _insert_child_span_same_pod(
        self,
        parent_nodes: List[EventNode],
        child_start: EventNode,
        event_graph: EventGraph,
    ) -> None:
        """Insert child span into parent span based on timestamp."""

        # Find the appropriate parent node to connect to
        for i, parent_node in enumerate(parent_nodes):
            if parent_node.timestamp < child_start.timestamp:
                # Connect to this parent node
                event_graph.add_edge(parent_node, child_start)
                break
        else:
            # If no suitable parent node found, connect to first node
            if parent_nodes:
                event_graph.add_edge(parent_nodes[0], child_start)

    def _create_alarm_map(
        self, alarms: List[AlarmEvent]
    ) -> Dict[str, List[AlarmEvent]]:
        """Create mapping from pod to alarms."""
        alarm_map = {}

        for alarm in alarms:
            if alarm.pod not in alarm_map:
                alarm_map[alarm.pod] = []
            alarm_map[alarm.pod].append(alarm)

        return alarm_map

    def validate_event_graph(self, event_graph: EventGraph) -> bool:
        """
        Validate an event graph for consistency.

        Args:
            event_graph: Event graph to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            # Check basic structure
            if not event_graph.nodes:
                logger.warning(f"Event graph {event_graph.trace_id} has no nodes")
                return False

            # Check that all edges reference existing nodes
            node_set = set(event_graph.nodes)

            for source, targets in event_graph.adjacency_list.items():
                if source not in node_set:
                    logger.warning(f"Edge source {source} not in node set")
                    return False

                for target in targets:
                    if target not in node_set:
                        logger.warning(f"Edge target {target} not in node set")
                        return False

            # Check timestamp ordering within spans
            span_nodes = {}
            for node in event_graph.nodes:
                if node.span_id:
                    if node.span_id not in span_nodes:
                        span_nodes[node.span_id] = []
                    span_nodes[node.span_id].append(node)

            for span_id, nodes in span_nodes.items():
                sorted_nodes = sorted(nodes, key=lambda x: x.timestamp)
                if sorted_nodes != nodes:
                    logger.debug(f"Timestamp ordering issue in span {span_id}")

            return True

        except Exception as e:
            logger.error(f"Error validating event graph: {e}")
            return False

    def get_graph_statistics(self, event_graphs: List[EventGraph]) -> Dict:
        """Get statistics about the event graphs."""
        if not event_graphs:
            return {"total_graphs": 0}

        total_nodes = sum(len(graph.nodes) for graph in event_graphs)
        total_edges = sum(len(graph.edges) for graph in event_graphs)

        node_types = {}
        for graph in event_graphs:
            for node in graph.nodes:
                node_type = node.event_type
                node_types[node_type] = node_types.get(node_type, 0) + 1

        return {
            "total_graphs": len(event_graphs),
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "avg_nodes_per_graph": total_nodes / len(event_graphs),
            "avg_edges_per_graph": total_edges / len(event_graphs),
            "node_type_distribution": node_types,
        }
