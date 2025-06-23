import glob
import logging
import os

import pandas as pd

from log import Logger

# 设置日志
log_path = (
     os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    + "/log/"
    + str(pd.Timestamp.now().strftime("%Y-%m-%d"))
    + "_nezha.log"
)
logger = Logger(log_path, logging.DEBUG, __name__).getlog()


def load_processed_logs(log_data_path, phase="abnormal"):
    """
    Load processed log files from parquet format
    :parameter
        log_data_path - path to the data folder
        phase - 'abnormal' or 'normal'
    :return
        combined_logs - DataFrame with all logs containing SpanId, Timestamp, log_temp, temp_id, Service
    """
    # First check if we have a direct parquet file for the phase
    direct_file = os.path.join(log_data_path, f"{phase}_logs.parquet")
    if os.path.exists(direct_file):
        try:
            logger.info(f"Loading logs directly from {direct_file}")
            df = pd.read_parquet(direct_file)

            # Verify essential columns exist
            essential_columns = ["Timestamp", "log_temp", "temp_id", "Service"]
            missing_columns = [
                col for col in essential_columns if col not in df.columns
            ]
            if missing_columns:
                logger.warning(f"File {direct_file} missing columns: {missing_columns}")

            # Check for SpanId column, might be named differently
            if "SpanId" not in df.columns:
                span_id_candidates = [
                    col for col in df.columns if "span" in col.lower()
                ]
                if span_id_candidates:
                    df = df.rename(columns={span_id_candidates[0]: "SpanId"})
                else:
                    # Create empty SpanId column if it doesn't exist
                    df["SpanId"] = None
                    logger.warning(f"No SpanId column found in {direct_file}")

            # Set SpanId as index for faster lookup if it exists and has valid values
            if "SpanId" in df.columns and not df["SpanId"].isna().all():
                df = df.set_index("SpanId")

            logger.info(f"Loaded {len(df)} logs from {os.path.basename(direct_file)}")
            return df

        except Exception as e:
            logger.warning(f"Failed to load direct log file {direct_file}: {e}")
            # Fall back to legacy method

    # Legacy method: look in logs_processed folder
    phase_folder = "abnormal_logs" if phase == "abnormal" else "normal_logs"
    log_folder_path = os.path.join(log_data_path, "logs_processed", phase_folder)

    if not os.path.exists(log_folder_path):
        logger.warning(f"Log folder {log_folder_path} not found")
        return pd.DataFrame()

    all_logs = []

    # Get all parquet files in the folder
    parquet_files = glob.glob(os.path.join(log_folder_path, "*.parquet"))

    for file_path in parquet_files:
        try:
            # Read parquet file - already contains Service column
            df = pd.read_parquet(file_path)

            # Verify essential columns exist
            essential_columns = ["Timestamp", "log_temp", "temp_id", "Service"]
            missing_columns = [
                col for col in essential_columns if col not in df.columns
            ]
            if missing_columns:
                logger.warning(f"File {file_path} missing columns: {missing_columns}")

            # Check for SpanId column, might be named differently
            if "SpanId" not in df.columns:
                span_id_candidates = [
                    col for col in df.columns if "span" in col.lower()
                ]
                if span_id_candidates:
                    df = df.rename(columns={span_id_candidates[0]: "SpanId"})
                else:
                    # Create empty SpanId column if it doesn't exist
                    df["SpanId"] = None
                    logger.warning(f"No SpanId column found in {file_path}")

            all_logs.append(df)
            logger.info(f"Loaded {len(df)} logs from {os.path.basename(file_path)}")

        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")

    if all_logs:
        combined_logs = pd.concat(all_logs, ignore_index=True)
        # Set SpanId as index for faster lookup if it exists and has valid values
        if (
            "SpanId" in combined_logs.columns
            and not combined_logs["SpanId"].isna().all()
        ):
            combined_logs = combined_logs.set_index("SpanId")
        logger.info(f"Total loaded logs: {len(combined_logs)}")
        return combined_logs
    else:
        logger.warning("No log files found")
        return pd.DataFrame()


def load_processed_logs_by_trace(log_data_path, trace_ids, phase="abnormal"):
    """
    Load processed log files from parquet format filtered by trace IDs
    :parameter
        log_data_path - path to the logs_processed folder
        trace_ids - list of trace IDs to filter logs for
        phase - 'abnormal' or 'normal'
    :return
        filtered_logs - DataFrame with logs for specified trace IDs, with SpanId as index
    """
    phase_folder = "abnormal_logs" if phase == "abnormal" else "normal_logs"
    log_folder_path = os.path.join(log_data_path, phase_folder)

    all_logs = []

    # Get all parquet files in the folder
    parquet_files = glob.glob(os.path.join(log_folder_path, "*.parquet"))

    # Convert trace_ids to a set for faster lookup
    trace_ids_set = set(trace_ids)

    for file_path in parquet_files:
        try:
            # Read parquet file
            df = pd.read_parquet(file_path)

            # Filter by trace ID if TraceId column exists
            if "TraceId" in df.columns:
                filtered_df = df[df["TraceId"].isin(trace_ids_set)]
                if len(filtered_df) > 0:
                    all_logs.append(filtered_df)
                    logger.info(
                        f"Loaded {len(filtered_df)} logs from {os.path.basename(file_path)} for specified traces"
                    )
            else:
                logger.warning(
                    f"No TraceId column in {file_path}, skipping trace filtering"
                )
                all_logs.append(df)

        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")

    if all_logs:
        combined_logs = pd.concat(all_logs, ignore_index=True)
        # Check if we have SpanId column for indexing
        if (
            "SpanId" in combined_logs.columns
            and not combined_logs["SpanId"].isna().all()
        ):
            combined_logs = combined_logs.set_index("SpanId")
        logger.info(f"Total loaded logs: {len(combined_logs)}")
        return combined_logs
    else:
        logger.warning("No log files found or no logs matching trace IDs")
        return pd.DataFrame()


def load_trace_parquet(trace_file_path):
    """
    Load trace data from parquet format
    :parameter
        trace_file_path - path to the trace parquet file
    :return
        trace_data - DataFrame with trace data
        unique_trace_ids - List of unique trace IDs
    """
    try:
        # Check if the file exists
        if not os.path.exists(trace_file_path):
            logger.error(f"Trace file does not exist: {trace_file_path}")
            return pd.DataFrame(), []

        # Load the trace data
        trace_data = pd.read_parquet(trace_file_path)

        # Check essential columns
        essential_columns = [
            "Timestamp",
            "TraceId",
            "SpanId",
            "ParentSpanId",
            "SpanName",
            "ServiceName",
            "Duration",
        ]

        # Convert column names to match our expected format if needed
        column_mapping = {}
        lowercase_columns = {col.lower(): col for col in trace_data.columns}

        for col in essential_columns:
            if col not in trace_data.columns and col.lower() in lowercase_columns:
                column_mapping[lowercase_columns[col.lower()]] = col

        if column_mapping:
            trace_data = trace_data.rename(columns=column_mapping)

        # Check again for missing columns
        missing_columns = [
            col for col in essential_columns if col not in trace_data.columns
        ]
        if missing_columns:
            logger.warning(f"Trace data missing columns: {missing_columns}")

            # Try to use alternative column names for critical fields
            if "TraceId" not in trace_data.columns:
                trace_id_candidates = [
                    col
                    for col in trace_data.columns
                    if "trace" in col.lower() and "id" in col.lower()
                ]
                if trace_id_candidates:
                    trace_data = trace_data.rename(
                        columns={trace_id_candidates[0]: "TraceId"}
                    )
                    logger.info(f"Renamed column {trace_id_candidates[0]} to TraceId")

            if "SpanId" not in trace_data.columns:
                span_id_candidates = [
                    col
                    for col in trace_data.columns
                    if "span" in col.lower() and "id" in col.lower()
                ]
                if span_id_candidates:
                    trace_data = trace_data.rename(
                        columns={span_id_candidates[0]: "SpanId"}
                    )
                    logger.info(f"Renamed column {span_id_candidates[0]} to SpanId")

        # Extract unique trace IDs
        if "TraceId" in trace_data.columns:
            unique_trace_ids = trace_data["TraceId"].unique().tolist()
            # Set TraceId as index for faster lookup
            trace_data = trace_data.set_index("TraceId")
        else:
            logger.error("TraceId column not found in trace data")
            return pd.DataFrame(), []

        logger.info(
            f"Loaded trace data with {len(trace_data)} spans from {len(unique_trace_ids)} unique traces"
        )

        return trace_data, unique_trace_ids
    except Exception as e:
        logger.error(f"Error loading trace parquet file {trace_file_path}: {e}")
        return pd.DataFrame(), []
