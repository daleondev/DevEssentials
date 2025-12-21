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
    POWERSHELL = PackageId(win="Microsoft.PowerShell", linux="powershell")
    ZSH = PackageId(win="None", linux="zsh")
    OHMYPOSH = PackageId(win="JanDeDobbeleer.OhMyPosh", linux="oh-my-posh")
    CASCADIA_CODE_NF = PackageId(win="Nerdfonts.CaskaydiaCove", linux="fonts-cascadia-code")
    GCC_TOOLCHAIN = PackageId(win="BrechtSanders.WinLibs", linux="build-essential")
    CMAKE = PackageId(win="Kitware.CMake", linux="cmake")
    NINJA = PackageId(win="Ninja-build.Ninja", linux="ninja-build")
    WGET = PackageId(win="JernejSimoncic.Wget", linux="wget")
    KEEPASS = PackageId(win="DominikReichl.KeePass", linux="keepass2")



