try:
    import colorama
    colorama.just_fix_windows_console()
except ModuleNotFoundError as e:
    # colorama is not an essential module:
    pass
from importlib.util import find_spec as findModule


class Logger:
    colorSupported: bool = findModule("colorama") is not None

    class Mode:
        error = {"color": "\033[31m", "prompt": "[ERROR]"} # red fg
        info  = {"color": "\033[34m", "prompt": "[INFO]"} # blue fg
        ok    = {"color": "\033[32m", "prompt": "[OK]"} # green fg
        note  = {"color": "\033[33m", "prompt": "[NOTE]"} # yellow fg

    @classmethod
    def colored(cls, text: str, color: str) -> str:
        if cls.colorSupported:
            return f"{color}{text}{colorama.Style.RESET_ALL}"
        else:
            return text

    @classmethod
    def log(cls, mode: dict[str, str], message: str) -> None:
        formatted = f"{mode['prompt'].ljust(8)} {message}"
        
        print(cls.colored(formatted, mode["color"]))
