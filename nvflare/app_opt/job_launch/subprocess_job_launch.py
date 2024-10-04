import time

from job_launch_spec import JobLaunchSpec, JobHandleSpec, JobState
from kubernetes import config
from kubernetes.client import Configuration
from kubernetes.client.api import core_v1_api
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream

class SubprocessJobHandle(JobHandleSpec):
    pod_manifest = {
        'apiVersion': 'v1',
        'kind': 'Pod',
        'metadata': { 'name': 'ERROR' },
        'spec': {
            'containers': [{
                'image': 'localhost:32000/k2k:0.0.2',
                'name': 'job-container',
                "args": [
                    "/usr/bin/bash",
                    "/workspace/job_pod.sh"
                ],
            "imagePullPolicy": "Always"
            }]
        }
    }
    def __init__(self, id: str, api_instance: core_v1_api):
        super.__init__(id)
        self.api_instance = api_instance
    
    def make_manifest(self, job_config):
        self.manifest = K8sJobHandle.pod_manifest.copy()

    def get_manifest(self):
        return self.manifest

    def abort(self, timeout=None):
        starting_time = time.time()
        resp = self.api_instance.delete_namespaced_pod(name=self.id, namespace='default', grace_period_seconds=0)
        while True:
            job_state = self.get_state()
            if job_state == JobState.ABORTED:
                return True
            elif timeout is not None and time.time()-starting_time>timeout:
                return False
            time.sleep(1)
    
    def enter_state(self, job_state, timeout=None):
        starting_time = time.time()
        while True:
            job_state = self.get_state()
            if job_state == job_state:
                return True
            elif timeout is not None and time.time()-starting_time>timeout:
                return False
            time.sleep(1)
    
    def get_state(self):
        resp = self.api_instance.read_namespaced_pod(name=self.id, namespace='default')
        return JobState.POD_STATE_MAPPING[resp.status.phase]


class SubprocessJobLaunch(JobLaunchSpec):
    def __init__(self, config_file_path):
        config.load_kube_config(config_file_path)
        try:
            c = Configuration().get_default_copy()
        except AttributeError:
            c = Configuration()
            c.assert_hostname = False
        Configuration.set_default(c)
        self.core_v1 = core_v1_api.CoreV1Api()

    def launch(self, job_name, job_config, timeout=None):
        job_handle = K8sJobHandle(job_name, self.core_v1, job_config)
        self.core_v1.create_namespaced_pod(body=job_handle.get_manifest(),  namespace='default')
        if job_handle.enter_state(JobState.RUNNING, timeout=timeout):
            return job_handle
        else:
            False

