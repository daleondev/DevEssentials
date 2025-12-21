from rich.console import Console

stdout = Console(stderr=False)
stderr = Console(stderr=True)

def print_info(msg):
    stdout.print(f"[INFO] {msg}", style="default")

def print_ok(msg):
    stdout.print(f"[OK] {msg}", style="green")

def print_warn(msg):
    stdout.print(f"[WARNING] {msg}", style="yellow")

def print_err(msg):
    stderr.print(f"[ERROR] {msg}", style="red")
