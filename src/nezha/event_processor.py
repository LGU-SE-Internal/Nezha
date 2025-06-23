import datetime
import logging
import os

import numpy as np
import pandas as pd

from log import Logger

from .models import Event, EventGraph, Span, Trace

# 设置日志
log_path = (
    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    + "/log/"
    + str(datetime.datetime.now().strftime("%Y-%m-%d"))
    + "_nezha.log"
)
logger = Logger(log_path, logging.DEBUG, __name__).getlog()


def get_events_within_trace(trace_reader, log_reader, trace_id, alarm_list, ns):
    """
    func get_events_within_trace: get all metric alarm, log, span within a trace and transform to event
    :parameter
        trace_read - pd.csv_read(tracefile)
        log_reader - processed logs DataFrame with SpanId as index
        trace_id   - only one trace is processed at a time
        alarm_list - [{'service': 'cartservice', 'alarm': [{'metric_type': 'CpuUsageRate(%)', 'alarm_flag': True}]
        ns - namespace
    :return
        trace class with all event (events in the same span was order by timestamp)
    """
    trace = Trace("StartTraceId is %s" % trace_id)
    log_span_id_list = log_reader.index.tolist() if hasattr(log_reader, "index") else []
    try:
        # find all span within a trace
        spans = trace_reader.loc[
            [trace_id],
            [
                "SpanID",
                "ParentID",
                "PodName",
                "StartTimeUnixNano",
                "EndTimeUnixNano",
                "OperationName",
            ],
        ]

        if len(spans["SpanID"]) > 0:
            # process span independently and order by timestamp
            for span_index in range(len(spans["SpanID"])):
                # span event
                span_id = spans["SpanID"].iloc[span_index]
                parent_id = spans["ParentID"].iloc[span_index]
                pod_name = spans["PodName"].iloc[span_index]

                # Use the pod_name directly as service_name
                service_name = pod_name

                # Add operation event first
                span = Span(span_id, parent_id, service_name)

                # Create span start event
                start_event = (
                    service_name
                    + " "
                    + spans["OperationName"].iloc[span_index]
                    + " start"
                )
                span.append_event(
                    Event(
                        timestamp=np.ceil(
                            spans["StartTimeUnixNano"].iloc[span_index]
                        ).astype(int),
                        event=start_event,
                        service_name=service_name,
                        ns=ns,
                        spanid=span_id,
                        parentid=parent_id,
                    )
                )

                end_timestamp = np.ceil(
                    spans["EndTimeUnixNano"].iloc[span_index]
                ).astype(int)

                # log event - use processed logs
                try:
                    # Check if this span has logs in our processed log data
                    if span_id in log_span_id_list:
                        logs = log_reader.loc[[span_id]]

                        if len(logs) > 0:
                            for log_index in range(len(logs)):
                                row = logs.iloc[log_index]

                                # Get timestamp from the Timestamp column
                                if isinstance(row["Timestamp"], str):
                                    try:
                                        timestamp = (
                                            pd.to_datetime(row["Timestamp"]).timestamp()
                                            * 1e9
                                        )
                                    except Exception:
                                        timestamp = (
                                            np.ceil(
                                                spans["StartTimeUnixNano"].iloc[
                                                    span_index
                                                ]
                                            ).astype(int)
                                            + log_index
                                            + 1
                                        )
                                else:
                                    timestamp = (
                                        row["Timestamp"].timestamp() * 1e9
                                        if hasattr(row["Timestamp"], "timestamp")
                                        else np.ceil(
                                            spans["StartTimeUnixNano"].iloc[span_index]
                                        ).astype(int)
                                        + log_index
                                        + 1
                                    )

                                timestamp = np.ceil(timestamp).astype(int)

                                # Use log_temp as the event directly - already processed
                                event_content = (
                                    row["log_temp"]
                                    if "log_temp" in row
                                    else (
                                        row["Body"]
                                        if "Body" in row
                                        else f"Unknown Log {row['temp_id']}"
                                        if "temp_id" in row
                                        else "Unknown Log"
                                    )
                                )

                                # For logs with timestamp after span end
                                if timestamp - end_timestamp > 0:
                                    end_timestamp = timestamp + 1

                                # Add processed log as event
                                span.append_event(
                                    Event(
                                        timestamp=timestamp,
                                        event=event_content,
                                        service_name=service_name,
                                        ns=ns,
                                        spanid=span_id,
                                        parentid=parent_id,
                                    )
                                )
                except Exception as e:
                    logger.error(f"Error processing logs for span {span_id}: {e}")
                    pass

                # Create span end event
                end_event = (
                    service_name
                    + " "
                    + spans["OperationName"].iloc[span_index]
                    + " end"
                )
                span.append_event(
                    Event(
                        timestamp=end_timestamp,
                        event=end_event,
                        service_name=service_name,
                        ns=ns,
                        spanid=span_id,
                        parentid=parent_id,
                    )
                )

                # alarm event
                if ns == "hipster":
                    if len(span.events) > 2:
                        for i in range(len(alarm_list)):
                            alarm_dict = alarm_list[i]
                            # 使用 service 匹配
                            if alarm_dict.get("service", "") == service_name:
                                for index in range(len(alarm_dict["alarm"])):
                                    span.append_event(
                                        Event(
                                            timestamp=np.ceil(
                                                spans["StartTimeUnixNano"].iloc[
                                                    span_index
                                                ]
                                            ).astype(int)
                                            + index
                                            + 1,
                                            event=alarm_dict["alarm"][index][
                                                "metric_type"
                                            ],
                                            service_name="alarm",
                                            ns=ns,
                                            spanid=span_id,
                                            parentid=parent_id,
                                        )
                                    )
                                break
                elif ns == "ts":
                    for i in range(len(alarm_list)):
                        alarm_dict = alarm_list[i]
                        # 使用 service 匹配
                        if alarm_dict.get("service", "") == service_name:
                            for index in range(len(alarm_dict["alarm"])):
                                span.append_event(
                                    Event(
                                        timestamp=np.ceil(
                                            spans["StartTimeUnixNano"].iloc[span_index]
                                        ).astype(int)
                                        + index
                                        + 1,
                                        event=alarm_dict["alarm"][index]["metric_type"],
                                        service_name="alarm",
                                        ns=ns,
                                        spanid=span_id,
                                        parentid=parent_id,
                                    )
                                )
                            break

                # sort event by event timestamp
                span.sort_events()
                trace.append_spans(span)

            # sort span by span start timestamp
            trace.sort_spans()
    except Exception as e:
        logger.error(f"Error processing trace {trace_id}: {e}")
        pass

    return trace


def get_events_within_trace_parquet(trace_reader, log_reader, trace_id, alarm_list, ns):
    """
    func get_events_within_trace_parquet: get all metric alarm, log, span within a trace and transform to event
    Using parquet format trace data
    :parameter
        trace_reader - DataFrame from trace parquet file
        log_reader - processed logs DataFrame
        trace_id   - only one trace is processed at a time
        alarm_list - [{'service': 'cartservice', 'alarm': [{'metric_type': 'CpuUsageRate(%)', 'alarm_flag': True}]
        ns - namespace
    :return
        trace class with all event (events in the same span was order by timestamp)
    """
    trace = Trace(f"StartTraceId is {trace_id}")

    # Create lookup dictionaries for improved performance
    alarms_by_service = {}
    for alarm in alarm_list:
        service = alarm.get("service", "")
        if service:
            alarms_by_service[service] = alarm["alarm"]

    # Prepare a dictionary of logs by span ID if log_reader is indexed by SpanId
    has_span_index = hasattr(log_reader, "index") and log_reader.index.name == "SpanId"
    logs_by_span = {}

    try:
        # Find all spans within a trace
        spans = trace_reader.loc[[trace_id]]

        if len(spans) > 0:
            # Extract all span IDs in this trace
            span_ids = set()
            for span_index in range(len(spans)):
                span_id = spans.iloc[span_index]["SpanId"]
                span_ids.add(span_id)

            # If log_reader is not indexed by SpanId, create a more efficient lookup
            if not has_span_index and "SpanId" in log_reader.columns:
                # Filter logs to only include those with span_ids from this trace
                trace_logs = log_reader[log_reader["SpanId"].isin(span_ids)]
                # Group them by SpanId for faster lookup
                for span_id, span_logs in trace_logs.groupby("SpanId"):
                    logs_by_span[span_id] = span_logs

            # Process span independently and order by timestamp
            for span_index in range(len(spans)):
                # Extract span information
                row = spans.iloc[span_index]
                span_id = row["SpanId"]
                parent_id = row["ParentSpanId"]
                service_name = row["ServiceName"]

                # Create span - directly use the ServiceName
                span = Span(span_id, parent_id, service_name)

                # Extract timestamps - precompute and reuse
                start_timestamp = pd.to_datetime(row["Timestamp"])
                start_timestamp_nano = int(start_timestamp.timestamp() * 1e9)

                # Calculate end timestamp
                duration_nano = row["Duration"]
                end_timestamp_nano = start_timestamp_nano + duration_nano

                # Get operation name
                operation_name = row["SpanName"]

                # Create span start event
                start_event = f"{service_name} {operation_name} start"
                span.append_event(
                    Event(
                        timestamp=start_timestamp_nano,
                        event=start_event,
                        service_name=service_name,
                        ns=ns,
                        spanid=span_id,
                        parentid=parent_id,
                    )
                )

                # Process logs - find all logs for this span
                try:
                    span_logs = None

                    # Get logs for this span using the appropriate method
                    if has_span_index:
                        # If log_reader is indexed by SpanId, use loc
                        if span_id in log_reader.index:
                            span_logs = log_reader.loc[[span_id]]
                    else:
                        # Otherwise use the pre-grouped logs
                        span_logs = logs_by_span.get(span_id)

                    if span_logs is not None and len(span_logs) > 0:
                        for log_index, row in span_logs.iterrows():
                            # Get timestamp from the Timestamp column
                            try:
                                if isinstance(row["Timestamp"], str):
                                    timestamp = int(
                                        pd.to_datetime(row["Timestamp"]).timestamp()
                                        * 1e9
                                    )
                                else:
                                    timestamp = int(
                                        row["Timestamp"].timestamp() * 1e9
                                        if hasattr(row["Timestamp"], "timestamp")
                                        else start_timestamp_nano + log_index + 1
                                    )
                            except:
                                timestamp = start_timestamp_nano + 1

                            # Use log_temp as the event directly - already processed
                            event_content = (
                                row["log_temp"]
                                if "log_temp" in row
                                else (
                                    row["Body"]
                                    if "Body" in row
                                    else f"Unknown Log {row['temp_id']}"
                                    if "temp_id" in row
                                    else "Unknown Log"
                                )
                            )

                            # For logs with timestamp after span end
                            if timestamp > end_timestamp_nano:
                                end_timestamp_nano = timestamp + 1

                            # Add processed log as event
                            span.append_event(
                                Event(
                                    timestamp=timestamp,
                                    event=event_content,
                                    service_name=service_name,
                                    ns=ns,
                                    spanid=span_id,
                                    parentid=parent_id,
                                )
                            )
                except Exception as e:
                    logger.error(f"Error processing logs for span {span_id}: {e}")

                # Create span end event
                end_event = f"{service_name} {operation_name} end"
                span.append_event(
                    Event(
                        timestamp=end_timestamp_nano,
                        event=end_event,
                        service_name=service_name,
                        ns=ns,
                        spanid=span_id,
                        parentid=parent_id,
                    )
                )

                # Add alarm events if any - direct lookup instead of linear search
                if service_name in alarms_by_service:
                    service_alarms = alarms_by_service[service_name]

                    # Skip the conditional check for hipster
                    for index, alarm_data in enumerate(service_alarms):
                        span.append_event(
                            Event(
                                timestamp=start_timestamp_nano + index + 1,
                                event=alarm_data["metric_type"],
                                service_name="alarm",
                                ns=ns,
                                spanid=span_id,
                                parentid=parent_id,
                            )
                        )

                # Sort events by timestamp
                span.sort_events()
                trace.append_spans(span)

            # Sort spans by their start timestamp
            trace.sort_spans()
    except Exception as e:
        logger.error(f"Error processing trace {trace_id}: {e}")

    return trace


def generate_event_graph(trace):
    """
    func generate_event_graph: integrate events of different span to graph
    :parameter
        trace - trace including spans with all event from get_events_within_trace
    :return
        event_graph -
    """
    event_graph = EventGraph()

    for span in trace.spans:
        # add edge in the span group
        for index in range(1, len(span.events)):
            event_graph.add_edge(span.events[index - 1], span.events[index])

    for span in trace.spans:
        # add relation from parent to child
        for parent_span in trace.spans:
            if parent_span.spanid == span.parentid:
                if parent_span.service_name == span.service_name:
                    # if in the same pod, insert based on timestamp
                    start_timestamp = span.events[0].timestamp

                    for index in range(1, len(parent_span.events)):
                        if parent_span.events[index].timestamp > start_timestamp:
                            event_graph.add_edge(
                                parent_span.events[index - 1], span.events[0]
                            )
                            break
                else:
                    # if not in the same pod, insert after the first span of parent group
                    event_graph.add_edge(parent_span.events[0], span.events[0])
                break

    return event_graph
