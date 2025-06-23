#!/usr/bin/env python3
"""
统一数据加载器模块
提供TraceLoader、LogLoader、MetricLoader和UnifiedDataLoader
支持parquet数据加载、字段适配、采样、并行处理等功能
"""

import datetime
import json
import logging
import multiprocessing
import time
from os.path import dirname
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from log import Logger
from log_processing import LogParser

# 日志配置
log_path = (
    dirname(__file__)
    + "/log/"
    + str(datetime.datetime.now().strftime("%Y-%m-%d"))
    + "_nezha.log"
)
logger = Logger(log_path, logging.DEBUG, __name__).getlog()




class LogLoader:
    """Log数据加载器，支持multiprocessing并行处理"""

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)

    def load(self, pool):
        return LogParser(self.data_dir).parse(pool)






if __name__ == "__main__":
    with multiprocessing.Pool() as pool:
        #normal = pool.apply(UnifiedDataLoader().load_all)
        #abnormal = pool.apply(UnifiedDataLoader().load_all, args=("abnormal",))
        normal,abnormal =  LogLoader().load(pool)
