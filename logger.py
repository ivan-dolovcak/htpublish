try:
    import colorama
    colorama.just_fix_windows_console()
except ModuleNotFoundError as e:
    # colorama is not an essential module:
    pass
from importlib.util import find_spec as findModule


class Logger:
    colorSupported: bool = findModule("colorama") is not None
    padAmt: int = 4

    loggerModes = {
        "error": {
            "color": "\033[31m", # red fg
            "prompt": "ERR"
        },
        "info": {
            "color": "\033[34m", # blue fg
            "prompt": "INFO"
        },
        "ok": {
            "color": "\033[32m", # green fg
            "prompt": "OK"
        },
        "note": {
            "color": "\033[33m", # yellow fg
            "prompt": "NOTE"
        },
    }
    
    @classmethod
    def log(cls, message: str, modeName: str) -> None:
        mode = cls.loggerModes[modeName]
        if cls.colorSupported:
            print(mode["color"], end="")
        
        print(f"[ {mode['prompt'].center(cls.padAmt)} ] {message}", end="")

        if cls.colorSupported:
            print("\033[39m") # reset fg
        else:
            print()
