import time

from kubernetes import config
from kubernetes.client import Configuration
from kubernetes.client.api import core_v1_api
from kubernetes.client.rest import ApiException

from nvflare.app_opt.job_launch.job_launch_spec import JobLaunchSingleton, JobLaunchSpec, JobHandleSpec, JobState

POD_STATE_MAPPING = {
    "Pending": JobState.STARTING,
    "Running": JobState.RUNNING,
    "Succeeded": JobState.SUCCEEDED,
    "Failed": JobState.TERMINATED,
    "Unknown": JobState.UNKNOWN
    }

class K8sJobHandle(JobHandleSpec):
    def __init__(self, id: str, api_instance: core_v1_api, job_config: dict, namespace='default'):
        super().__init__(id)
        self.api_instance = api_instance
        self.namespace = namespace
        self.pod_manifest = {
            'apiVersion': 'v1',
            'kind': 'Pod',
            'metadata': {
                'name': None         # set by job_config['name']
            },
            'spec': {
                'containers': None,  # link to container_list
                'volumes': None      # link to volume_list
            }
        }
        self.volume_list = [
            {
                'name': None,
                'hostPath': {
                    'path': None,
                    'type': 'Directory'
                    }
            }
        ]
        self.container_list = [
            {
                'image': None,
                'name': None,
                'command': ['/usr/local/bin/python'],
                'args': None,                # args_list + args_dict + args_sets
                'volumeMounts': None,        # volume_mount_list
                'imagePullPolicy': 'Always'
            }
        ]
        self.container_args_python_args_list = [
            '-u', '-m', 'nvflare.private.fed.app.client.worker_process'
        ]
        self.container_args_module_args_dict = {
            '-m': None,
            '-w': None,
            '-t': None,
            '-d': None,
            '-n': None,
            '-c': None,
            '-p': None,
            '-g': None,
            '-scheme': None,
            '-s': None,
        }
        self.container_volume_mount_list = [
            {
                'name': None,
                'mountPath': None,
            }
        ]
        self._make_manifest(job_config)

    def _make_manifest(self, job_config):
        self.container_volume_mount_list =\
            job_config.get('volume_mount_list',
                [{'name':'workspace-nvflare', 'mountPath': '/workspace/nvflare'}]
            )
        set_list = job_config.get('set_list')
        if set_list is None:
            self.container_args_module_args_sets = list()
        else:
            self.container_args_module_args_sets = ['--set'] + set_list
        self.container_args_module_args_dict =\
            job_config.get('module_args',
                {
                    '-m': None,
                    '-w': None,
                    '-t': None,
                    '-d': None,
                    '-n': None,
                    '-c': None,
                    '-p': None,
                    '-g': None,
                    '-scheme': None,
                    '-s': None
                }
            )
        self.container_args_module_args_dict_as_list = list()
        for k, v in self.container_args_module_args_dict.items():
            self.container_args_module_args_dict_as_list.append(k)
            self.container_args_module_args_dict_as_list.append(v)
        self.volume_list =\
            job_config.get('volume_list',
                [{
                    'name': None,
                    'hostPath': {
                        'path': None,
                        'type': 'Directory'
                        }
                }]
            )

        self.pod_manifest['metadata']['name'] = job_config.get('name')
        self.pod_manifest['spec']['containers'] = self.container_list
        self.pod_manifest['spec']['volumes'] = self.volume_list

        self.container_list[0]['image'] = job_config.get('image', 'nvflare/nvflare:2.5.0')
        self.container_list[0]['name'] = job_config.get('container_name', 'nvflare_job')
        self.container_list[0]['args'] =\
            self.container_args_python_args_list + \
            self.container_args_module_args_dict_as_list + \
            self.container_args_module_args_sets
        self.container_list[0]['volumeMounts'] = self.container_volume_mount_list

    def get_manifest(self):
        return self.pod_manifest

    def abort(self, timeout=None):
        resp = self.api_instance.delete_namespaced_pod(name=self.id, namespace=self.namespace, grace_period_seconds=0)
        return self.enter_states([JobState.TERMINATED], timeout=timeout)
    
    def get_state(self):
        try:
            resp = self.api_instance.read_namespaced_pod(name=self.id, namespace=self.namespace)
        except ApiException as e:
            return JobState.UNKNOWN
        return POD_STATE_MAPPING.get(resp.status.phase, JobState.UNKNOWN)


class K8sJobLaunch(JobLaunchSpec, metaclass=JobLaunchSingleton):
    def __init__(self, config_file_path, namespace='default'):
        config.load_kube_config(config_file_path)
        try:
            c = Configuration().get_default_copy()
        except AttributeError:
            c = Configuration()
            c.assert_hostname = False
        Configuration.set_default(c)
        self.core_v1 = core_v1_api.CoreV1Api()
        self.namespace = namespace

    def launch(self, job_name: str, job_config: dict, timeout=None):
        job_handle = K8sJobHandle(job_name, self.core_v1, job_config, namespace=self.namespace)
        try:
            self.core_v1.create_namespaced_pod(body=job_handle.get_manifest(),  namespace=self.namespace)
            if job_handle.enter_states([JobState.RUNNING], timeout=timeout):
                return job_handle
            else:
                return False
        except ApiException as e:
            return False
