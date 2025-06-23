import datetime
import logging
import os
from .utils import timeit
from log import Logger

# 设置日志
log_path = (
    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    + "/log/"
    + str(datetime.datetime.now().strftime("%Y-%m-%d"))
    + "_nezha.log"
)
logger = Logger(log_path, logging.DEBUG, __name__).getlog()


class Trace(object):
    """
    Trace class representing a collection of spans
    """

    def __init__(self, traceid):
        self.traceid = traceid
        self.spans = []

    def sort_spans(self):
        """Sort spans by their first event's timestamp"""
        self.spans.sort(key=lambda k: (k.events[0].timestamp, 0))

    def append_spans(self, span):
        """Add a span to this trace"""
        self.spans.append(span)

    def show_all_spans(self):
        """Display all spans in this trace"""
        print(self.traceid)
        for i in range(len(self.spans)):
            self.spans[i].show_all_events()


class Span(object):
    """
    Span class representing a span in a trace with multiple events
    """

    def __init__(self, spanid, parentid, service_name):
        self.spanid = spanid
        self.parentid = parentid
        self.service_name = service_name
        self.events = []

    def sort_events(self):
        """Sort events by timestamp"""
        self.events.sort(key=lambda k: (k.timestamp, 0))

    def append_event(self, event):
        """Add an event to this span"""
        self.events.append(event)

    def new_timestamp(self):
        """Generate a new timestamp for a new event"""
        return self.events[len(self.events) - 1].timestamp - 1

    def show_all_events(self):
        """Display all events in this span"""
        logger.info("%s,%s,%s", self.spanid, self.parentid, self.service_name)
        for i in range(len(self.events)):
            self.events[i].show_event()
        logger.info("")


class Event(object):
    """
    Event class representing a single event in a span
    """

    def __init__(
        self, event, service_name, ns, timestamp=None, spanid=None, parentid=None
    ):
        self.event = event
        self.service_name = service_name
        self.timestamp = timestamp
        self.spanid = spanid
        self.parentid = parentid
        self.ns = ns

    def show_event(self):
        """Display event information"""
        logger.info("%s, %s, %s", self.timestamp, self.spanid, self.event)


class EventGraph:
    """
    EventGraph class for building event graphs and analyzing relationships
    """

    def __init__(self):
        self.adjacency_list = {}
        self.node_list = set()
        self.pair_set = set()
        self.support_dict = {}

    def add_edge(self, node1, node2):
        """Add an edge between two event nodes"""
        if node1 not in self.adjacency_list.keys():
            self.adjacency_list[node1] = []
        self.adjacency_list[node1].append(node2)
        self.node_list.add(node1.event)
        self.node_list.add(node2.event)

    def remove_edge(self, node1, node2):
        """Remove an edge between two event nodes"""
        self.adjacency_list[node1].remove(node2)

    def print_adj_list(self):
        """Print the adjacency list representation of the graph"""
        for key in self.adjacency_list.keys():
            print(f"node {key}: {self.adjacency_list[key]}")

    def show_graph(self):
        """Display the graph's structure"""
        for key in self.adjacency_list.keys():
            logger.info("head:%s", key.event)
            for item in self.adjacency_list[key]:
                logger.info("tail:%s", item.event)
            logger.info("----")

    def get_deepth_pod(self, target_event):
        """Get the depth of a specific event in the graph and its service name"""
        service_name = ""
        depth = 0
        while True:
            flag = False
            for key in self.adjacency_list.keys():
                for item in self.adjacency_list[key]:
                    if target_event == item.event:
                        target_event = key.event
                        if depth == 0:
                            service_name = item.service_name
                        flag = True
                        if "start" in key.event and "TraceID" not in key.event:
                            depth = depth + 1
                        break
                if flag:
                    break
            if not flag:
                break
        return depth, service_name
    @timeit()
    def get_support(self):
        """Calculate support values for each edge in the graph"""
        for key in self.adjacency_list.keys():
            for item in self.adjacency_list[key]:
                supprot_key = str(key.event) + "_" + str(item.event)
                if supprot_key not in self.pair_set:
                    self.support_dict[supprot_key] = 1
                    self.pair_set.add(supprot_key)
                else:
                    self.support_dict[supprot_key] += 1
        return self.support_dict


# No need to import pandas in this module
