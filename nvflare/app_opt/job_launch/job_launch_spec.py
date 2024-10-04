import time

from kubernetes import config
from kubernetes.client import Configuration
from kubernetes.client.api import core_v1_api
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream

from enum import Enum

class JobState(Enum):
    STARTING = "starting"
    RUNNING = "running"
    TERMINATED = "terminated"
    SUCCEEDED = "succeeded"
    UNKNOWN = "unknown"

    POD_STATE_MAPPING = \
        {"Pending": STARTING,
         "Running": RUNNING,
         "Succeeded": SUCCEEDED,
         "Failed": TERMINATED,
         "Unknown": UNKNOWN
         }

class JobHandleSpec:
    def __init__(self, id: str):
        self.id = id
    
    def abort(self, timeout=None):
        raise NotImplemented
    
    def get_state(self):
        raise NotImplemented

class JobLaunchSpec:
    def launch(self, job_config: dict) -> JobHandleSpec:
        raise NotImplemented

class JobLaunchSingleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(JobLaunchSingleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

