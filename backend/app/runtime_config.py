
import os

def get_runtime_name():
    return os.getenv("LLM_RUNTIME", "simulated")

