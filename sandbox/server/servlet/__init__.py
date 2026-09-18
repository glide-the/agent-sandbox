__all__ = [
    "RunnerBootstrapBaseWeb"
]


def __getattr__(name):
    if name == "RunnerBootstrapBaseWeb":
        from sandbox.server.servlet.boot.runner_bootstrap import RunnerBootstrapBaseWeb

        return RunnerBootstrapBaseWeb
    raise AttributeError(name)
