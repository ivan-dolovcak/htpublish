try:
    import colorama
    colorama.just_fix_windows_console()
except ModuleNotFoundError as e:
    # colorama is not an essential module:
    pass
from importlib.util import find_spec as findModule


class Logger:
    """ Class for printing pretty log messages.
    """

    colorSupported: bool = findModule("colorama") is not None

    @classmethod
    def log(cls, message: str, colorName: str, prompt: str = "") -> None:
        """ Print a colored log message.

            Example: [ERR]    FTP error: timeout
        """

        # Add padding spaces:
        output = f"{prompt.ljust(6)} {message}"
        
        if cls.colorSupported:
            colorCode = f"{getattr(colorama.Fore, colorName)}"

            output = f"{colorCode}{output}{colorama.Style.RESET_ALL}"
        
        print(output)

        if prompt == "[ERR]":
            exit(1)
    
    error   = lambda message: Logger.log(message, "RED", "[ERR]")
    info    = lambda message: Logger.log(message, "BLUE", "[INFO]")
    ok      = lambda message: Logger.log(message, "GREEN", "[OK]")
    note    = lambda message: Logger.log(message, "YELLOW", "[NOTE]")
    command = lambda message: Logger.log(message, "MAGENTA", "[CMD]")
