
from backend.app.inference_runtime import SimulatedRuntime
# placeholder import
# from backend.app.vllm_runtime import VLLMRuntime

from backend.app.runtime_config import get_runtime_name


def create_runtime():

    runtime_name = get_runtime_name()

    if runtime_name == "vllm":
        # return VLLMRuntime()
        return SimulatedRuntime()

    return SimulatedRuntime()

