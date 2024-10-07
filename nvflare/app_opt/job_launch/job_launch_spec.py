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

class JobHandleSpec:
    def __init__(self, id: str):
        self.id = id
    
    def enter_states(self, job_states_to_enter: list, timeout=None):
        raise NotImplemented

    def abort(self, timeout=None):
        raise NotImplemented

    def get_state(self):
        raise NotImplemented

class JobLaunchSpec:
    def launch(self, job_name: str, job_config: dict, timeout=None) -> JobHandleSpec:
        raise NotImplemented

class JobLaunchSingleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(JobLaunchSingleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

