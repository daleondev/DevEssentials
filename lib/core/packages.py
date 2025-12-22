from enum import Enum
from dataclasses import dataclass

@dataclass
class PackageId:
    win: str
    linux: str

class KnownPackage(Enum):
    GIT = PackageId(win="Microsoft.Git", linux="git")
    NEOVIM = PackageId(win="Neovim.Neovim", linux="neovim")
    POWERSHELL = PackageId(win="Microsoft.PowerShell", linux="powershell")
    ZSH = PackageId(win="None", linux="zsh")
    OHMYPOSH = PackageId(win="JanDeDobbeleer.OhMyPosh", linux="oh-my-posh")
    CASCADIA_CODE_NF = PackageId(win="Nerdfonts.CaskaydiaCove", linux="fonts-cascadia-code")
    GCC_TOOLCHAIN = PackageId(win="BrechtSanders.WinLibs.POSIX.UCRT", linux="build-essential")
    CMAKE = PackageId(win="None", linux="cmake")
    NINJA = PackageId(win="None", linux="ninja-build")
    WGET = PackageId(win="JernejSimoncic.Wget", linux="wget")
    KEEPASS = PackageId(win="DominikReichl.KeePass", linux="keepass2")



