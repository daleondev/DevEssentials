from rich.console import Console

class Logger:
    _stdout = Console(stderr=False)
    _stderr = Console(stderr=True)

    @staticmethod
    def info(msg: str):
        Logger._stdout.print(f"[INFO] {msg}", style="default")

    @staticmethod
    def ok(msg: str):
        Logger._stdout.print(f"[OK] {msg}", style="green")

    @staticmethod
    def warn(msg: str):
        Logger._stdout.print(f"[WARNING] {msg}", style="yellow")

    @staticmethod
    def err(msg: str):
        Logger._stderr.print(f"[ERROR] {msg}", style="red")