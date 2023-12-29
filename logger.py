try:
    import colorama
    colorama.just_fix_windows_console()
except ModuleNotFoundError as e:
    # colorama is not an essential module:
    pass
from importlib.util import find_spec as findModule


class Logger:
    colorSupported: bool = findModule("colorama") is not None

    @classmethod
    def log(cls, message: str, colorName: str, prompt: str = "") -> None:
        """ Print a colored log message.

            Example: [ERR]    FTP error: timeout
        """
        output = f"{prompt.ljust(6)} {message}"
        
        if cls.colorSupported:
            color = f"{getattr(colorama.Fore, colorName)}"
            output = f"{color}{output}{colorama.Style.RESET_ALL}"
        
        print(output)

        if prompt == "ERR":
            exit(1)
    
    @classmethod
    def error(cls, message: str):
        cls.log(message, "RED", "[ERR]")
    
    @classmethod
    def info(cls, message: str):
        cls.log(message, "BLUE", "[INFO]")
    
    @classmethod
    def ok(cls, message: str):
        cls.log(message, "GREEN", "[OK]")

    @classmethod
    def note(cls, message: str):
        cls.log(message, "YELLOW", "[NOTE]")

    @classmethod
    def command(cls, message: str):
        cls.log(message, "MAGENTA", "[CMD]")
