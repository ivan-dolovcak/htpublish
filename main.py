#!/usr/bin/python3
import ftplib
from json import load as jsonLoad
from json.decoder import JSONDecodeError
from pathlib import Path, PurePath
from typing import Any

from logger import Logger
from ftp import FTP


def loadConfig() -> dict[str, Any]:
    """ Load, parse and return JSON config from "config.json".
    """

    # Load config if file exists
    configPath = Path("config.json")
    if not configPath.exists():
        Logger.log(Logger.Mode.error,
            f"Error: config file '{configPath}' not found.")
    
    with configPath.open() as configFile:
        try:
            config = jsonLoad(configFile)
        except JSONDecodeError as e:
            Logger.log(Logger.Mode.error, f"Error: malformed JSON: {e}")

    # Try parsing config
    try:
        _ = config["hostname"]
        _ = config["ignored"]
        config["srcDir"] = Path(config["srcDir"]).absolute()
        config["destDir"] = PurePath(config["destDir"])
    except KeyError as e:
        Logger.log(Logger.Mode.error, 
            f"Error: missing required key in config: '{e.args[0]}'")
    
    if not config["srcDir"].is_absolute():
        Logger.log(Logger.Mode.error,
            "Error: 'srcDir' has to be an absolute path.")

    if not config["srcDir"].exists():
        Logger.log(Logger.Mode.error,
            f"Error: source dir '{config['srcDir']}' not found.")

    if not config["destDir"].is_absolute():
        Logger.log(Logger.Mode.error,
            "Error: 'destDir' has to be an absolute path.")
    
    if "timeout" in config.keys():
        if config["timeout"] not in range(1, 60):
            Logger.log(Logger.Mode.error,
                f"Error: bogus timeout value: {config['timeout']}")
    else:
        config["timeout"] = 3
    
    return config

def main() -> None:
    config = loadConfig()

    ftpObj = FTP(config["hostname"], config["username"], config["password"],
        config["timeout"])

    # Infinite loop to reconnect in case of timeout errors
    while True:
        try:
            ftpObj.connect()

            ftpObj.mirror(config["srcDir"], config["srcDir"], config["destDir"],
                config["ignored"])

            break
        except ftplib.all_errors as e:
            if "timed out" in str(e):
                Logger.log(Logger.Mode.note, f"FTP Error: {e}")
                Logger.log(Logger.Mode.note, "RETRYING...")
            else:
                Logger.log(Logger.Mode.error, f"FTP Error: {e}")
        finally:
            ftpObj.closeConn()

if __name__ == "__main__":
    main()
