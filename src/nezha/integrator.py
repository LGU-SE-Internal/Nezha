import concurrent.futures
import datetime
import logging
import os

import pandas as pd

from log import Logger

from .event_processor import generate_event_graph, get_events_within_trace
from .log_processor import load_processed_logs_by_trace

# 设置日志
log_path = (
    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    + "/log/"
    + str(datetime.datetime.now().strftime("%Y-%m-%d"))
    + "_nezha.log"
)
logger = Logger(log_path, logging.DEBUG, __name__).getlog()


def data_integrate(
    trace_file, trace_id_file, log_data_path, alarm_list, ns, phase="abnormal"
):
    """
    func data_integrate: integrate multimodal data to event graph
    :parameter
        trace_file - path to trace CSV file
        trace_id_file - path to trace ID CSV file
        log_data_path - path to the logs_processed folder
        alarm_list - list of alarm dictionaries
        ns - namespace
        phase - 'abnormal' or 'normal' to specify which logs to load
    :return
        list of event graph
    """
    logger.info(f"Starting data integration with {len(alarm_list)} alarms")

    # Read trace IDs
    trace_id_reader = pd.read_csv(
        trace_id_file, index_col=False, header=None, engine="c"
    )

    # Get the list of trace IDs
    trace_ids = trace_id_reader[0].tolist()
    logger.info(f"Loaded {len(trace_ids)} trace IDs")

    # Load processed logs filtered by trace IDs
    log_reader = load_processed_logs_by_trace(log_data_path, trace_ids, phase)

    trace_reader = pd.read_csv(
        trace_file,
        index_col="TraceID",
        usecols=[
            "TraceID",
            "SpanID",
            "ParentID",
            "PodName",
            "StartTimeUnixNano",
            "EndTimeUnixNano",
            "OperationName",
        ],
        engine="c",
    )

    log_sequences = []
    event_graphs = []

    # Process traces to extract events
    with concurrent.futures.ProcessPoolExecutor(max_workers=16) as executor1:
        futures1 = {
            executor1.submit(
                get_events_within_trace,
                trace_reader,
                log_reader,
                traceid,
                alarm_list,
                ns,
            )
            for traceid in trace_ids
        }

        for future1 in concurrent.futures.as_completed(futures1):
            trace = future1.result()
            if trace is not None:
                log_sequences.append(trace)
        executor1.shutdown()

    logger.info(f"Generated {len(log_sequences)} trace sequences")

    # Build event graphs from trace sequences
    with concurrent.futures.ProcessPoolExecutor(max_workers=16) as executor2:
        futures2 = {
            executor2.submit(generate_event_graph, trace) for trace in log_sequences
        }

        for future2 in concurrent.futures.as_completed(futures2):
            graph = future2.result()
            if graph is not None:
                event_graphs.append(graph)
        executor2.shutdown()

    # Calculate support for each graph
    for graph in event_graphs:
        graph.get_support()

    logger.info(f"Generated {len(event_graphs)} event graphs")
    logger.info("Data integration complete!")
    return event_graphs


def data_integrate_parquet(
    trace_file, log_data_path, alarm_list, ns, phase="abnormal", logs_df=None
):
    """
    data_integrate_parquet: integrate multimodal data to event graph using parquet format trace data

    :parameter
        trace_file - path to trace parquet file
        log_data_path - path to the data folder containing logs_*.parquet files
        alarm_list - list of alarm dictionaries
        ns - namespace
        phase - 'abnormal' or 'normal' to specify which logs to load
        logs_df - optional pandas DataFrame containing already processed logs
    :return
        list of event graph
    """
    from .event_processor import generate_event_graph, get_events_within_trace_parquet
    from .log_processor import load_processed_logs, load_trace_parquet

    logger.info(
        f"Starting data integration with {len(alarm_list)} alarms"
    )  # Load trace data from parquet
    trace_reader, trace_ids = load_trace_parquet(trace_file)
    logger.info(
        f"Loaded {len(trace_ids)} trace IDs from {os.path.basename(trace_file)}"
    )

    # Use the provided logs DataFrame if available
    if logs_df is not None:
        logger.info(f"Using provided logs DataFrame with {len(logs_df)} records")
        log_reader = logs_df

        # Set SpanId as index for faster lookup if it exists and has valid values
        if "SpanId" in log_reader.columns and not log_reader["SpanId"].isna().all():
            if log_reader.index.name != "SpanId":  # Only set if not already set
                log_reader = log_reader.set_index("SpanId")
    else:
        # Load processed logs - directly use the appropriate parquet file
        log_file = os.path.join(log_data_path, f"{phase}_logs.parquet")
        if os.path.exists(log_file):
            logger.info(f"Using direct log file: {os.path.basename(log_file)}")
            import pandas as pd

            log_reader = pd.read_parquet(log_file)

            # Set SpanId as index for faster lookup if it exists and has valid values
            if "SpanId" in log_reader.columns and not log_reader["SpanId"].isna().all():
                log_reader = log_reader.set_index("SpanId")
        else:
            # Fallback to legacy method
            logger.info(
                f"Log file {log_file} not found, using legacy log loading method"
            )
            log_reader = load_processed_logs(log_data_path, phase)

    log_sequences = []
    event_graphs = []

    # Process traces to extract events
    with concurrent.futures.ProcessPoolExecutor(max_workers=16) as executor1:
        futures1 = {
            executor1.submit(
                get_events_within_trace_parquet,
                trace_reader,
                log_reader,
                traceid,
                alarm_list,
                ns,
            )
            for traceid in trace_ids
        }

        for future1 in concurrent.futures.as_completed(futures1):
            trace = future1.result()
            if trace is not None:
                log_sequences.append(trace)
        executor1.shutdown()

    logger.info(f"Generated {len(log_sequences)} trace sequences")

    # Build event graphs from trace sequences
    with concurrent.futures.ProcessPoolExecutor(max_workers=16) as executor2:
        futures2 = {
            executor2.submit(generate_event_graph, trace) for trace in log_sequences
        }

        for future2 in concurrent.futures.as_completed(futures2):
            graph = future2.result()
            if graph is not None:
                event_graphs.append(graph)
        executor2.shutdown()

    # Calculate support for each graph
    for graph in event_graphs:
        graph.get_support()

    logger.info(f"Generated {len(event_graphs)} event graphs")
    logger.info("Data integration complete!")
    return event_graphs
