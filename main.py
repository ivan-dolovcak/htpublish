#!/usr/bin/python3
import argparse
import ftplib
from json import load as jsonLoad
from json.decoder import JSONDecodeError
from pathlib import Path, PurePath
from typing import Any

from logger import Logger
from ftp import FTP
from _version import __version__


def readCmdArgs() -> argparse.Namespace:
    cliParser = argparse.ArgumentParser(
        prog="htpublish",
        description="Python script for uploading a website to FTP server",
        epilog="""Copyright (c) 2023 Ivan Dolovčak. Source code is available
                  under the MIT License."""
    )
    cliParser.add_argument("-D", "--no-delete",
        help="don't delete anything on the server",
        action="store_true")
    cliParser.add_argument("-I", "--no-ignore",
        help="don't read ignore patterns from config",
        action="store_true")
    cliParser.add_argument("-C", "--no-color",
        help="disable colored output",
        action="store_true")
    cliParser.add_argument("-R", "--no-reconnect",
        help="don't reconnect to server after timeout error",
        action="store_true")
    cliParser.add_argument("-c", "--log-commands",
        help="show commands before they are sent to the server (debug)",
        action="store_true")
    cliParser.add_argument("-t", "--timeout",
        help="set timeout value",
        metavar="seconds",
        default=3,
        type=int)
    cliParser.add_argument("-v", "--version",
        action="version",
        version=f"%(prog)s {__version__}")

    cmdArgs = cliParser.parse_args()

    if cmdArgs.timeout not in range(1, 61):
        Logger.error(f"Error: bogus timeout value ({cmdArgs.timeout}).")

    return cmdArgs

def loadConfig() -> dict[str, Any]:
    """ Load, parse and return JSON config from "config.json".
    """

    # Load config if file exists
    configPath = Path("config.json")
    if not configPath.exists():
        Logger.error(f"Error: config file '{configPath}' not found.")
    
    with configPath.open() as configFile:
        try:
            config = jsonLoad(configFile)
        except JSONDecodeError as e:
            Logger.error(f"Error: malformed JSON: {e}")

    # Try parsing config
    try:
        _ = config["hostname"]
        _ = config["ignored"]
        config["srcDir"] = Path(config["srcDir"]).absolute()
        config["destDir"] = PurePath(config["destDir"])
    except KeyError as e:
        Logger.error(f"Error: missing required key in config: '{e.args[0]}'")
    
    if not config["srcDir"].is_absolute():
        Logger.error("Error: 'srcDir' has to be an absolute path.")

    if not config["srcDir"].exists():
        Logger.error(f"Error: source dir '{config['srcDir']}' not found.")

    if not config["destDir"].is_absolute():
        Logger.error("Error: 'destDir' has to be an absolute path.")
    
    return config

def main() -> None:
    config = loadConfig()
    cmdArgs = readCmdArgs()


    wantColor = not cmdArgs.no_color
    if wantColor and (not Logger.colorSupported):
        Logger.error("Install the colorama module for colored output to work \
(pip install colorama) or run the program with the -C flag.")

    Logger.doLogCommands = cmdArgs.log_commands

    ftpObj = FTP(config["hostname"], config["username"], config["password"],
        cmdArgs.timeout)

    ftpObj.deleteDisabled = cmdArgs.no_delete
    ftpObj.ignoreDisabled = cmdArgs.no_ignore

    # Infinite loop to reconnect in case of timeout errors
    while True:
        try:
            ftpObj.connect()

            ftpObj.mirror(config["srcDir"], config["srcDir"], config["destDir"],
                config["ignored"])

            break
        except ftplib.all_errors as e:
            if "timed out" in str(e):
                Logger.error(f"FTP error: {e}", isErrorFatal=False)

                if cmdArgs.no_reconnect:
                    break

                Logger.note("Reconnecting to server...")
            else:
                Logger.error(f"FTP error: {e}")
        finally:
            ftpObj.closeConn()

if __name__ == "__main__":
    main()
