# DevEssentials

DevEssentials is a utility for setting up a development environment on Windows and Linux. The goal is to automate the installation and configuration of tools I use daily, ensuring a consistent setup across different machines with a single command.

## Features

The installer is modular. You can run it with no arguments for a basic setup or use flags to include specific components.

### Default Installation
By default, the script installs:
* Visual Studio Code: Includes a stable build, the Gruvbox Dark theme, and Python support extensions. It also applies custom settings like relative line numbers and a hidden activity bar.
* Git: Standard installation for version control.

### Terminal Setup
Running with `--with-terminal` configures the shell and terminal emulator.
* Font: Installs Cascadia Mono NF (a Nerd Font) to ensure icons and symbols render correctly.
* Windows: Installs PowerShell 7 and Windows Terminal. It uses Oh-My-Posh with a rainbow theme and sets up the terminal with transparency and Gruvbox colors.
* Linux: Installs Zsh and Tmux. It sets up Oh-My-Zsh with the Powerlevel10k theme and common plugins like syntax highlighting and autosuggestions.

### Neovim
The `--with-neovim` flag sets up a Neovim environment.
* On Windows, it downloads the v0.11.5 binary and adds it to the user PATH.
* On Linux, it uses the system package manager.
* It installs the VS Code Neovim extension and copies a custom init.lua to the local config directory.

### Build Tools
The `--with-build-tools` flag installs compilers and build systems.
* Windows: Installs WinLibs (GCC and LLVM/Clang).
* Linux: Installs the build-essential package along with CMake and Ninja.

### Utilities
The `--with-utils` flag adds a few extra tools like Wget and KeePass.

## Installation

You will need an active internet connection and permissions to install software (sudo on Linux or administrator on Windows).

### Windows
1. Open a terminal in this directory.
2. Run: `.\setup.bat`
The script will check for Python 3.12 and install it via Winget if it isn't found.

### Linux
1. Open a terminal in this directory.
2. Ensure the script is executable: `chmod +x setup.sh`
3. Run: `./setup.sh`
Note that you should have Python 3 installed before running the script.

## Usage

The setup scripts pass any arguments directly to the underlying Python installer.

| Argument | Result |
| :--- | :--- |
| (none) | Installs VS Code and Git. |
| --full | Installs everything listed above. |
| --with-terminal | Adds the shell, themes, and font setup. |
| --with-neovim | Adds Neovim and the VS Code integration. |
| --with-build-tools | Adds compilers and build utilities. |
| --with-utils | Adds extra utilities like Wget. |

Example command to install everything:
`./setup.sh --full`

## Project Structure

* main.py: The main entry point for the installation logic.
* setup.bat / setup.sh: Bootstrap scripts that handle Python environment setup.
* lib/: The core logic, split into platform-specific implementations and modular components.
* files/: Contains configuration files like init.lua and VS Code keybindings.