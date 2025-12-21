from enum import Enum
from dataclasses import dataclass

@dataclass
class PackageId:
    win: str
    linux: str

class KnownPackage(Enum):
    GIT = PackageId(win="Git.Git", linux="git")
    NEOVIM = PackageId(win="Neovim.Neovim", linux="neovim")
    ZIP7 = PackageId(win="7zip.7zip", linux="p7zip-full")
    # Add more as needed
