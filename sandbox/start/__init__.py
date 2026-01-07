import os
import platform
import tempfile
from pathlib import Path

# import torch

from sandbox.common import util
from sandbox.common.registry import registry
from sandbox.start.core import Speaker, WebSpeaker

__all__ = [
    "Speaker",
    "WebSpeaker",
]

root_dir = os.getcwd()
registry.register_path("library_root", root_dir)

tempdir = Path("/tmp" if platform.system() == "Darwin" else tempfile.gettempdir())
registry.register_path("tmp_root", str(tempdir))


# device = (
#     'cuda:0' if torch.cuda.is_available()
#     else (
#         'mps' if util.has_mps()
#         else 'cpu'
#     )
# )
device = "cpu"

registry.register("device", device)
