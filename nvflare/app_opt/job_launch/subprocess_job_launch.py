import os
import subprocess
import sys
import time

from job_launch_spec import JobLaunchSpec, JobHandleSpec, JobState, JobLaunchSingleton

def process_state_mapping(return_code):
    if return_code is None:
        return JobState.RUNNING
    elif return_code == 0:
        return JobState.SUCCEEDED
    elif return_code < 0:
        return JobState.TERMINATED
    else:
        return JobState.UNKNOWN

class SubprocessJobHandle(JobHandleSpec):
    def __init__(self, id: str, job_config: dict):
        super().__init__(id)
        self.subprocess_args = [
            f"{sys.executable}",
            "-m",
            "nvflare.private.fed.app.client.worker_process"]
        self.subprocess_args += self._make_subprocess_args(job_config)
        self.env = job_config.get("job_env", new_env = os.environ.copy())
        self.proceess = None
    def _make_subprocess_args(self, job_config):
        subprocess_args = list()
        for k, v in job_config.get("module_args", {}).items():
            subprocess_args.append(k)
            subprocess_args.append(v)
        set_list = job_config.get('set_list')
        if set_list is None:
            subprocess_args.append('--set')
            subprocess_args += set_list
        return subprocess_args

    def abort(self, timeout=None):
        if self.process:
            try:
                os.killpg(os.getpgid(self.process.pid), 9)
            except:
                pass
            self.process.terminate()
  
    def launch(self):
        self.proceess = subprocess.Popen(self.subprocess_args, preexec_fn=os.setsid, env=self.env)
    
    def get_state(self):
        if self.process:
            return_code = self.process.poll()
            return process_state_mapping(return_code)
        else:
            return JobState.UNKNOWN


class SubprocessJobLaunch(JobLaunchSpec, metaclass=JobLaunchSingleton):
    def launch(self, job_name, job_config, timeout=None):
        job_handle = SubprocessJobHandle(job_name, job_config)
        job_handle.launch()
        if job_handle.enter_states([JobState.RUNNING], timeout=timeout):
            return job_handle
        else:
            False
