from itertools import starmap
from pathlib import Path
from typing import Tuple

import pandas as pd
from drain3 import TemplateMiner
from drain3.file_persistence import FilePersistence
from drain3.template_miner_config import TemplateMinerConfig

from parse_utils import extract_log


class LogParser:
    def __init__(self, base_dir: Path):
        self.data_dir = Path(base_dir)
        self.output_dir = self.data_dir / "logs_processed"
        self.normal_output = self.output_dir / "normal_logs"
        self.abnormal_output = self.output_dir / "abnormal_logs"
        self.normal_output.mkdir(parents=True, exist_ok=True)
        self.abnormal_output.mkdir(parents=True, exist_ok=True)
    def parse(self, pool):
        """Process log data and save results to CSV file for each pod."""
        # normal_groups, abnormal_groups = await asyncio.gather(
        #    *[self.read_and_group(normal) for normal in [True, False]]
        # )
        normal_groups = self.read_and_group(normal=True)
        abnormal_groups = self.read_and_group(normal=False)
        all_services = set(normal_groups.keys()).union(set(abnormal_groups.keys()))

        # result = await asyncio.gather(
        #    *[
        #        self._process_pod(
        #            service,
        #            normal_groups.get(service, pd.DataFrame()),
        #            abnormal_groups.get(service, pd.DataFrame()),
        #            pool,
        #        )
        #        for service in all_services
        #    ]
        # )
        result = list(
            starmap(
                self._process_pod,
                [
                    (
                        service,
                        normal_groups.get(service, pd.DataFrame()),
                        abnormal_groups.get(service, pd.DataFrame()),
                        pool,
                    )
                    for service in all_services
                ],
            )
        )
        normal_result, abnormal_result = zip(
            *[
                ((normal_group), (abnormal_group))
                for normal_group, abnormal_group in result
            ]
        )
        return pd.concat(normal_result), pd.concat(abnormal_result)

    def read_and_group(self, normal: bool = True) -> dict:
        log_path = (
            self.data_dir / "normal_logs.parquet"
            if normal
            else self.data_dir / "abnormal_logs.parquet"
        )
        df = pd.read_parquet(log_path)
        name_col = "ServiceName"
        return {name: group for name, group in df.groupby(name_col)}

    def _process_pod(
        self, pod, normal_group: pd.DataFrame, abnormal_group: pd.DataFrame, pool
    ):
        """Process logs for a pod and save results to a CSV file."""
        template_miner = get_template_miner()
        if not normal_group.empty:
            normal_group, template_miner = pool.apply(
                batch_process,
                args=(normal_group, pod, template_miner, self.normal_output),
            )
        if not abnormal_group.empty:
            abnormal_group, _ = pool.apply(
                batch_process,
                args=(abnormal_group, pod, template_miner, self.abnormal_output),
            )

        return (normal_group, abnormal_group)


def get_template_miner(use_persistence_handler="None", config=TemplateMinerConfig()):
    if use_persistence_handler == "redis":
        from drain3.redis_persistence import RedisPersistence

        template_miner = TemplateMiner(
            persistence_handler=RedisPersistence(
                redis_host="localhost",
                redis_port=6379,
                redis_db=1,
                redis_key="drain",
                redis_pass=None,
                is_ssl=False,
            ),
            config=config,
        )
    elif use_persistence_handler == "file":
        template_miner = TemplateMiner(
            persistence_handler=FilePersistence("./drain_state"),
            config=config,
        )
    else:
        template_miner = TemplateMiner(config=config)
    return template_miner


def parse_with_drain(
    log_df: pd.DataFrame, pod, template_miner: TemplateMiner
) -> pd.DataFrame:
    """parse logs with drain and add template id and template mined columns to the dataframe."""
    log_df["temp_id"] = pd.Series(dtype=str)
    log_df["log_temp"] = pd.Series(dtype=str)

    if pod == "ts-ui-dashboard":
        template_miner.config.drain_sim_th = 0.8
    for index, row in log_df.iterrows():
        result = template_miner.add_log_message(row["message"])
        log_df.at[index, "temp_id"] = result["cluster_id"]
        log_df.at[index, "log_temp"] = result["template_mined"]
    return log_df, template_miner


def batch_process(
    batch: pd.DataFrame, pod, template_miner: TemplateMiner, output_dir: Path
) -> Tuple[pd.DataFrame, TemplateMiner]:
    """Process each batch and return the processed DataFrame."""
    batch[["Body", "message", "log_level"]] = batch.apply(
        extract_log, axis="columns", result_type="expand"
    )
    batch.dropna(subset=["log_level"], inplace=True)  # Drop rows with no log level
    batch, template_miner = parse_with_drain(batch, pod, template_miner)
    final_df = batch[["Timestamp", "log_level", "temp_id", "log_temp", "Body"]]
    final_df['Service'] = pod
    if final_df.size == 0:
        # print(f"No logs for {pod}")
        return pd.DataFrame(), template_miner
    save_path = output_dir / f"{pod}_logs.parquet"
    final_df.to_parquet(save_path, index=False)
    # print(f"Logs for {pod} saved to {output_file}")
    return final_df, template_miner
