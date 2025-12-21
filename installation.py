import os
import sys
import shutil
import argparse
import subprocess
import zipfile
from rich.console import Console
import urllib.request
import winreg

stdout = Console(stderr=False)
stderr = Console(stderr=True)

print_info = lambda msg : stdout.print(f"[INFO] {msg}", style="default")
print_ok = lambda msg : stdout.print(f"[OK] {msg}", style="green")
print_warn = lambda msg : stdout.print(f"[WARNING] {msg}", style="yellow")
print_err = lambda msg : stderr.print(f"[ERROR] {msg}", style="red")

def add_to_user_path_windows(folder_path):
    key_path = r"Environment"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, 
                             winreg.KEY_ALL_ACCESS)
    except FileNotFoundError:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)

    try:
        try:
            current_path_value, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current_path_value = ""

        if folder_path in current_path_value:
            print_warn(f"'{folder_path}' is already in the PATH.")
            return

        new_path_value = current_path_value + (";" if current_path_value else "") + folder_path

        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path_value)
        print_ok(f"Successfully added '{folder_path}' to User PATH.")
        
    except Exception as e:
        print_err(f"Failed to add path variable: {e}")
        raise
    
    finally:
        winreg.CloseKey(key)
        
def add_to_path_linux(folder_path):
    home = os.path.expanduser("~")
    shell_config = os.path.join(home, ".bashrc") 
    line_to_add = f'\nexport PATH="$PATH:{folder_path}"\n'

    try:
        with open(shell_config, "r") as f:
            content = f.read()
            if f"export PATH=\"$PATH:{folder_path}\"" in content:
                print_warn(f"'{folder_path}' is already in the PATH.")
                return
        
        with open(shell_config, "a") as f:
            f.write(line_to_add)
        
        print_ok(f"Added to {shell_config}. Run 'source {shell_config}' or restart terminal.")
        
    except Exception as e:
        print_err(f"Failed to add path variable: {e}")
        raise

def vscode():
    try:
        print_info("Installing VS-Code extensions...")
        subprocess.run(["code", "--install-extension", "tomphilbin.gruvbox-themes"], shell=True, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["code", "--install-extension", "s-nlf-fh.glassit"], shell=True, check=True, stdout=subprocess.DEVNULL)
        print_ok("Successfully installed VS-Code extensions")
        
    except Exception as e:
        print_err(f"Failed to install VS-Code extensions: {e}")
        sys.exit(1)
        
def nvim():
    try:
        print_info("Installing Neovim...")
        
        download_path = "tmp"
        download_file = os.path.join(download_path, "nvim.zip")
        os.makedirs(download_path, exist_ok=True)
        urllib.request.urlretrieve("https://github.com/neovim/neovim/releases/download/v0.11.5/nvim-win64.zip", download_file)
        
        install_path = os.path.join(os.path.expanduser("~"), "nvim")
        if os.path.exists(install_path):
            shutil.rmtree(install_path)
        os.mkdir(install_path)
        with zipfile.ZipFile(download_file, 'r') as zip_ref:
            zip_ref.extractall(install_path)
            
        print_ok("Successfully installed Neovim")
        
        print_info("Installing VSCode Neovim...")
        
        subprocess.run(["code", "--install-extension", "asvetliakov.vscode-neovim"], shell=True, check=True, stdout=subprocess.DEVNULL)
        
        print_ok("Successfully installed VSCode Neovim")
        
    except Exception as e:
        print_err("Failed to install Neovim: {e}")
        sys.exit(1)

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

    # vscode()
    
    if args.with_neovim:
        nvim()
    
    sys.exit(0)

if __name__ == "__main__":
    main()