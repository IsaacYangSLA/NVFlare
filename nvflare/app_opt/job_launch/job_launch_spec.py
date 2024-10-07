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
        starting_time = time.time()
        if not isinstance(job_states_to_enter, (list, tuple)):
            job_states_to_enter = [job_states_to_enter]
        if not all([isinstance(js, JobState)] for js in job_states_to_enter):
            raise ValueError(f"expect job_states_to_enter with valid values, but get {job_states_to_enter}")
        while True:
            job_state = self.get_state()
            if job_state in job_states_to_enter:
                return True
            elif timeout is not None and time.time()-starting_time>timeout:
                return False
            time.sleep(1)
    
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

