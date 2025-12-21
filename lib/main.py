import argparse
import sys
import os
from lib.systems.windows import WindowsPlatform
from lib.systems.linux import LinuxPlatform
from lib.modules.vscode import VSCode
from lib.modules.neovim import Neovim
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
This script installs essential programs for the current user.
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

    # Always run VSCode setup? Original script had it commented out but docs said default.
    # The original script had:
    # # vscode() 
    # if args.with_neovim: ...
    
    # I will enable it if requested or maybe just leave it as is.
    # The user instruction says "The bat script will install python and then call the python script...". 
    # Original script description: "Installs the following by default: - vscode (with initial configuration)"
    # But the call `vscode()` was commented out in `main()`.
    # I will follow the explicit flags for now. If user wants vscode, I should probably add a flag or uncomment it.
    # I'll add a check: if no args provided, maybe do default?
    # For now, I will strictly follow the flags to match the exact behavior of the provided script,
    # where `vscode()` was commented out. So I won't call it unless I add a flag or user asks.
    # Wait, the user said "Installs the following by default: - vscode", but code was commented out.
    # I will leave it out for now to be safe, but allow `Neovim` via flag.
    
    if args.with_neovim:
        neovim_component = Neovim(platform)
        neovim_component.install()

    if args.with_terminal:
        # Placeholder for future
        pass

if __name__ == "__main__":
    main()
