#!/usr/bin/python3
try:
    import colorama
    colorama.just_fix_windows_console()
except ModuleNotFoundError as e:
    # colorama is not an essential module:
    pass
from datetime import datetime, timezone
import ftplib
from importlib.util import find_spec as findModule
from json import load as jsonLoad
from json.decoder import JSONDecodeError
from pathlib import Path, PurePath
from typing import Any


localTimezone = datetime.now().astimezone().tzinfo
# MSLD uses an almost short ISO format (missing date/time separator):
mlsdTSFormat = "%Y%m%d%H%M%S"

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

def loadConfig() -> dict[str, Any]:
    # Load config if file exists
    configPath = Path("config.json")
    if not configPath.exists():
        Logger.log(f"Error: config file '{configPath}' not found.", "error")
        exit(1)
    with configPath.open() as configFile:
        try:
            config = jsonLoad(configFile)
        except JSONDecodeError as e:
            Logger.log(f"Error: malformed JSON: {e}", "error")
            exit(1)

    # Try parsing config
    try:
        _ = config["hostname"]
        _ = config["ignored"]
        config["srcDir"] = Path(config["srcDir"]).absolute()
        config["destDir"] = PurePath(config["destDir"])
    except KeyError as e:
        Logger.log(f"Error: missing required key in config: '{e.args[0]}'", "error")
        exit(1)
    
    if "timeout" in config.keys():
        if config["timeout"] not in range(1, 60):
            Logger.log(f"Error: bogus timeout value: {config['timeout']}", "error")
            exit(1)
    else:
        config["timeout"] = 3

    if not config["srcDir"].exists():
        Logger.log(f"Error: source dir '{config['srcDir']}' not found.", "error")
        exit(1)
    
    return config

def makeFtpConn(config: dict[str, Any]) -> ftplib.FTP:
    ftpConn = ftplib.FTP(host=config["hostname"], timeout=config["timeout"])
    ftpConn.login(config["username"], config["password"])
    Logger.log(f"LOGIN {config['username']}@{config['hostname']}", "ok")

    return ftpConn

def mlsd(ftpConn: ftplib.FTP, path: PurePath) -> dict[str, dict[str, Any]]:
    """Convert complex object returned by FTP.mlsd() into a JSON-like object."""

    mlsdResult = ftpConn.mlsd(str(path))
    # Remove "." and ".." from results:
    mlsdResultList = list(mlsdResult)[2:]

    mlsdSimple = dict()
    for item in mlsdResultList:
        mlsdSimple[item[0]] = item[1]
    return mlsdSimple

def getPathMTime(path: Path) -> datetime:
    """Get local file/directory modtime as a datetime object."""

    return datetime \
        .fromtimestamp(path.stat().st_mtime, localTimezone) \
        .replace(microsecond=0) \
        .astimezone(timezone.utc)

def rmdDeep(ftpConn: ftplib.FTP, dir_: PurePath) -> None:
    """FTP rm -r implementation."""

    flagRemoved = False
    try:
        ftpConn.rmd(str(dir_))
        flagRemoved = True
        Logger.log(f"RMD {dir_}", "note")
    except ftplib.error_perm as e:
        ftpErrCode = int(e.args[0][:3]) 
        if ftpErrCode != 550: # dir not empty error
            Logger.log(f"FTP error: {e}", "error")
            return
    
    # If dir not empty, delete files and recurse into other dirs
    mlsdList = mlsd(ftpConn, dir_)
    for childName, stats in mlsdList.items():
        if stats["type"] == "dir":
            rmdDeep(ftpConn, dir_ / childName)
        else:
            ftpConn.delete(str(dir_ / childName))
            Logger.log(f"DELE {dir_ / childName}", "note")

    if not flagRemoved:
        ftpConn.rmd(str(dir_))
        Logger.log(f"RMD {dir_}", "note")

# Path to last empty directory made in ftpMirror():
lastMkd: PurePath|None = None

def ftpMirror(ftpConn: ftplib.FTP, config: dict[str, Any], srcDir: Path) -> None:
    """Mirror command implementation."""

    global lastMkd
    # Translate local paths into remote paths (switch roots):
    destDir = config["destDir"] / srcDir.relative_to(config["srcDir"])

    # lastMkd is guaranteed to be empty, so no need to check for files to
    # delete:
    if destDir != lastMkd:
        # Get standardized MLSD directory listing:
        mlsdList = mlsd(ftpConn, destDir)
        Logger.log(f"MLSD {destDir}", "ok")

        # Delete remote dirs and files which aren't present locally
        # (i.e. detect local deletion and do it remotely)
        srcDirs = [dir_.name for dir_ in srcDir.iterdir() if dir_.is_dir()]
        destDirs = [child for child, stats in mlsdList.items() 
            if stats["type"] == "dir"]

        for deletedDir in filter(lambda dir_: dir_ not in srcDirs, destDirs):
            rmdDeep(ftpConn, destDir / deletedDir)
        
        srcFiles = [file_.name for file_ in srcDir.iterdir() if file_.is_file()]
        destFiles = [child for child, stats in mlsdList.items()
            if stats["type"] == "file"]

        for deletedFile in filter(lambda file_: file_ not in srcFiles, destFiles):
            ftpConn.delete(str(destDir / deletedFile))
            Logger.log(f"DELE {deletedFile}", "note")

        # Save modtimes as datetime objects in a new key for later comparing
        for destFilename, destStats in mlsdList.items():
            # MSLD should give timestamps in UTC
            destStats["mtime"] = datetime.strptime(destStats["modify"],
                mlsdTSFormat).replace(tzinfo=timezone.utc)
    else:
        mlsdList = {}
        Logger.log(f"SKIP (rmcheck) {destDir}", "info")

    for srcChild in srcDir.iterdir():
        # Match against all ignore patterns
        if any([srcChild.match(pattern) for pattern in config["ignored"]]):
            Logger.log(f"SKIP (ignore) {srcChild}", "info")
            continue

        destChild: PurePath = destDir / srcChild.name

        # If source is directory, try to remotely create it and recurse into it
        if srcChild.is_dir():
            try:
                ftpConn.mkd(str(destChild))
            # If dir already exists, catch error gracefully
            except ftplib.error_perm as e:
                Logger.log(f"SKIP MKD (already exists) {destChild}", "info")
            else:
                lastMkd = destChild
                Logger.log(f"MKD {destChild}", "ok")
            finally:
                ftpMirror(ftpConn, config, srcChild)
        else:
            srcMTime = getPathMTime(srcChild)
            if srcChild.name in mlsdList.keys():
                # Skip file if local modtime is smaller or equal to remote
                destMTime = mlsdList[srcChild.name]["mtime"]
                if srcMTime <= destMTime:
                    Logger.log(f"SKIP (mtime) {srcChild}", "info")
                    continue

            # Upload file
            # Open in binary read mode since FTP.storbinary() is used
            ftpConn.storbinary(f"STOR {destChild}", srcChild.open("rb"))
            Logger.log(f"STOR {srcChild}", "ok")

            msldTimestamp: str = datetime.strftime(srcMTime, mlsdTSFormat)
            # Touch the remote file:
            ftpConn.sendcmd(f"MFMT {msldTimestamp} {destChild}")
            Logger.log(f"MFMT {destChild}", "ok")

def main() -> None:
    config = loadConfig()

    # Infinite loop to retry in case of timeout errors
    while True:
        try:
            ftpConn = makeFtpConn(config)

            ftpMirror(ftpConn, config, config["srcDir"])

            ftpConn.close()
            Logger.log("BYE", "ok")
            break
        except ftplib.all_errors as e:
            Logger.log(f"FTP Error: {e}", "error")
            if "timed out" in str(e):
                Logger.log("RETRYING...", "note")
            else:
                exit(1)

if __name__ == "__main__":
    main()
