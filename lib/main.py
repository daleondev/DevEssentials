import argparse
import sys
import os
from lib.systems.windows import WindowsPlatform
from lib.systems.linux import LinuxPlatform
from lib.modules.default import Default
from lib.modules.neovim import Neovim
from lib.modules.terminal import Terminal
from lib.modules.build_tools import BuildTools
from lib.modules.utils import Utils
from lib.utils.logger import print_err

def get_platform():
    if sys.platform == "win32":
        return WindowsPlatform()
    elif sys.platform == "linux":
        return LinuxPlatform()
    else:
        raise NotImplementedError(f"OS {sys.platform} not supported")

def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
This script installs essential programs for the current user
Installs the following by default:
    - vscode (with initial configuration)
    - git
Use command line arguments to specify additional installations (use --help for help)
"""
    )
    parser.add_argument("--with-terminal", action="store_true", help="Install pretty terminal (shell, shell-scheme, oh-my-posh, vscode-integration)")
    parser.add_argument("--with-neovim", action="store_true", help="Install Neovim (neovim, vscode-integration)")
    parser.add_argument("--with-build-tools", action="store_true", help="Install posix build tools (gcc, gdb, make, cmake, ...)")
    parser.add_argument("--with-utils", action="store_true", help="Install utilities (7zip, winget, ...)")
    
    args = parser.parse_args()

    try:
        platform = get_platform()
    except NotImplementedError as e:
        print_err(str(e))
        sys.exit(1)

    # Always install default components (Git, VS Code config)
    Default(platform).install()

    if args.with_terminal:
        terminal_component = Terminal(platform)
        terminal_component.install()

    if args.with_build_tools:
        build_tools_component = BuildTools(platform)
        build_tools_component.install()

    if args.with_utils:
        utils_component = Utils(platform)
        utils_component.install()

    if args.with_neovim:
        neovim_component = Neovim(platform)
        neovim_component.install()


if __name__ == "__main__":
    main()
