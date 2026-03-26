"""Shared mock objects for hip-cargo tests."""


class FakeJobDetails:
    """Mimics ray.job_submission.JobDetails attributes."""

    def __init__(self, **kwargs):
        self.job_id = kwargs.get("job_id", "")
        self.submission_id = kwargs.get("submission_id", "")
        self.status = kwargs.get("status", "RUNNING")
        self.entrypoint = kwargs.get("entrypoint", "")
        self.message = kwargs.get("message", "")
        self.error_type = kwargs.get("error_type", None)
        self.start_time = kwargs.get("start_time", None)
        self.end_time = kwargs.get("end_time", None)
        self.metadata = kwargs.get("metadata", {})
        self.runtime_env = kwargs.get("runtime_env", {})


class FakeJobClient:
    """Mock JobSubmissionClient that returns canned data without Ray."""

    def __init__(self, jobs=None):
        self._jobs = jobs or {}

    def list_jobs(self):
        return [FakeJobDetails(**j) for j in self._jobs.values()]

    def get_job_info(self, job_id):
        if job_id not in self._jobs:
            raise RuntimeError(f"Job {job_id} not found")
        return FakeJobDetails(**self._jobs[job_id])

    def get_job_logs(self, job_id):
        if job_id not in self._jobs:
            raise RuntimeError(f"Job {job_id} not found")
        return self._jobs[job_id].get("logs", "")

    def stop_job(self, job_id):
        if job_id not in self._jobs:
            raise RuntimeError(f"Job {job_id} not found")
        return True

    def submit_job(self, entrypoint, runtime_env=None, metadata=None):
        return "raysubmit_test_123"


class FailingJobClient:
    """Mock JobSubmissionClient that always raises ConnectionError."""

    def list_jobs(self):
        raise ConnectionError("Ray cluster unreachable")

    def get_job_info(self, job_id):
        raise ConnectionError("Ray cluster unreachable")

    def get_job_logs(self, job_id):
        raise ConnectionError("Ray cluster unreachable")

    def stop_job(self, job_id):
        raise ConnectionError("Ray cluster unreachable")

    def submit_job(self, entrypoint, runtime_env=None, metadata=None):
        raise ConnectionError("Ray cluster unreachable")
