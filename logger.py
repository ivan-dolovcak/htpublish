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
    doLogCommands: bool = False

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
    
    @classmethod
    def info(cls, message: str) -> None:
        Logger.log(message, "BLUE", "[INFO]")

    @classmethod
    def ok(cls, message: str) -> None:
        Logger.log(message, "GREEN", "[OK]")

    @classmethod
    def note(cls, message: str) -> None:
        Logger.log(message, "YELLOW", "[NOTE]")

    @classmethod
    def error(cls, message: str, isErrorFatal: bool = True) -> None:
        Logger.log(message, "RED", "[ERR]")
        if isErrorFatal:
            exit(1)

    @classmethod
    def command(cls, message: str) -> None:
        if cls.doLogCommands:
            Logger.log(message, "CYAN", "[CMD]")
