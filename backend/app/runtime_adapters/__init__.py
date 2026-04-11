"""GPU runtime adapters for the inference control plane."""

from .amd_vllm_rocm import AMDROCmVLLMBackend
from .nvidia_dynamo_triton import NVIDIADynamoTritonBackend

__all__ = ["AMDROCmVLLMBackend", "NVIDIADynamoTritonBackend"]
