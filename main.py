#!/usr/bin/python3
import ftplib
from json import load as jsonLoad
from json.decoder import JSONDecodeError
from pathlib import Path, PurePath

from logger import Logger
from ftp import FTP


def loadConfig() -> dict[str, object]:
    # Load config if file exists
    configPath = Path("config.json")
    if not configPath.exists():
        Logger.log(Logger.Mode.error,
            f"Error: config file '{configPath}' not found.")
        exit(1)
    with configPath.open() as configFile:
        try:
            config = jsonLoad(configFile)
        except JSONDecodeError as e:
            Logger.log(Logger.Mode.error, f"Error: malformed JSON: {e}")
            exit(1)

    # Try parsing config
    try:
        _ = config["hostname"]
        _ = config["ignored"]
        config["srcDir"] = Path(config["srcDir"]).absolute()
        config["destDir"] = PurePath(config["destDir"])
    except KeyError as e:
        Logger.log(Logger.Mode.error, 
            f"Error: missing required key in config: '{e.args[0]}'")
        exit(1)
    
    if not config["destDir"].is_absolute():
        Logger.log(Logger.Mode.error,
            "Error: 'destDir' has to be an absolute path.")
        exit(1)
    
    if "timeout" in config.keys():
        if config["timeout"] not in range(1, 60):
            Logger.log(Logger.Mode.error,
                f"Error: bogus timeout value: {config['timeout']}")
            exit(1)
    else:
        config["timeout"] = 3

    if not config["srcDir"].exists():
        Logger.log(Logger.Mode.error,
            f"Error: source dir '{config['srcDir']}' not found.")
        exit(1)
    
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

            ftpObj.closeConn()
            break
        except ftplib.all_errors as e:
            Logger.log(Logger.Mode.error, f"FTP Error: {e}")

            if "timed out" in str(e):
                ftpObj.closeConn()
                Logger.log(Logger.Mode.note, "RETRYING...")
            else:
                exit(1)

if __name__ == "__main__":
    main()
