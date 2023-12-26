#!/usr/bin/python3
from datetime import datetime, timezone
import ftplib
from json import load as jsonLoad
from json.decoder import JSONDecodeError
from pathlib import Path, PurePath
from typing import Any


localTimezone = datetime.now().astimezone().tzinfo
# MSLD uses an almost short ISO format (missing date/time separator):
mlsdTSFormat = "%Y%m%d%H%M%S"

def loadConfig() -> dict[str, Any]:
    # Load config if file exists
    configPath = Path("config.json")
    if not configPath.exists():
        print(f"Error: config file '{configPath}' not found.")
        exit(1)
    with configPath.open() as configFile:
        try:
            config = jsonLoad(configFile)
        except JSONDecodeError as e:
            print("Error: malformed JSON:", e)
            exit(1)

    # Try parsing config
    try:
        _ = config["hostname"]
        _ = config["ignored"]
        config["srcDir"] = Path(config["srcDir"]).absolute()
        config["destDir"] = PurePath(config["destDir"])
    except KeyError as e:
        print(f"Error: missing required key in config: '{e.args[0]}'")
        exit(1)
    
    if "timeout" in config.keys():
        if config["timeout"] not in range(1, 60):
            print(f"Error: bogus timeout value: {config['timeout']}")
            exit(1)
    else:
        config["timeout"] = 3

    if not config["srcDir"].exists():
        print(f"Error: source dir '{config['srcDir']}' not found.")
        exit(1)
    
    return config

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
        print(f"RMD {dir_}")
    except ftplib.error_perm as e:
        ftpErrCode = int(e.args[0][:3]) 
        if ftpErrCode != 550: # dir not empty error
            print("FTP error:", e)
            return
    
    # If dir not empty, delete files and recurse into other dirs
    mlsdList = mlsd(ftpConn, dir_)
    for childName, stats in mlsdList.items():
        if stats["type"] == "dir":
            rmdDeep(ftpConn, dir_ / childName)
        else:
            ftpConn.delete(str(dir_ / childName))
            print(f"DELE {dir_ / childName}")

    if not flagRemoved:
        ftpConn.rmd(str(dir_))
        print(f"RMD {dir_}")

# Path to last empty directory made in ftpMirror():
lastMkd: PurePath|None = None

def ftpMirror(ftpConn: ftplib.FTP, srcDir: Path, srcRoot: Path, 
              destRoot: PurePath, ignoreRegex: list) -> None:
    """Mirror command implementation."""

    global lastMkd
    # Translate local paths into remote paths (switch roots):
    destDir = destRoot / srcDir.relative_to(srcRoot)

    # lastMkd is guaranteed to be empty, so no need to check for files to
    # delete:
    if destDir != lastMkd:
        # Get standardized MLSD directory listing:
        mlsdList = mlsd(ftpConn, destDir)
        print(f"MLSD {destDir}")

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
            print(f"DELE {deletedFile}")

        # Save modtimes as datetime objects in a new key for later comparing
        for destFilename, destStats in mlsdList.items():
            # MSLD should give timestamps in UTC
            destStats["mtime"] = datetime.strptime(destStats["modify"],
                mlsdTSFormat).replace(tzinfo=timezone.utc)
    else:
        mlsdList = {}
        print(f"SKIP (rmcheck) {destDir}")

    for srcChild in srcDir.iterdir():
        # Match against all ignore patterns
        if any([srcChild.match(pattern) for pattern in ignoreRegex]):
            print(f"SKIP (ignore) {srcChild}")
            continue

        destChild: PurePath = destDir / srcChild.name

        # If source is directory, try to remotely create it and recurse into it
        if srcChild.is_dir():
            try:
                ftpConn.mkd(str(destChild))
            # If dir already exists, catch error gracefully
            except ftplib.error_perm as e:
                print(f"SKIP MKD (already exists) {destChild}")
            else:
                lastMkd = destChild
                print(f"MKD {destChild}")
            finally:
                ftpMirror(ftpConn, srcChild, srcRoot, destRoot, ignoreRegex)
        else:
            srcMTime = getPathMTime(srcChild)
            if srcChild.name in mlsdList.keys():
                # Skip file if local modtime is smaller or equal to remote
                destMTime = mlsdList[srcChild.name]["mtime"]
                if srcMTime <= destMTime:
                    print(f"SKIP (mtime) {srcChild}")
                    continue

            # Upload file
            # Open in binary read mode since FTP.storbinary() is used
            ftpConn.storbinary(f"STOR {destChild}", srcChild.open("rb"))
            print(f"STOR {srcChild}")

            msldTimestamp: str = datetime.strftime(srcMTime, mlsdTSFormat)
            # Touch the remote file:
            ftpConn.sendcmd(f"MFMT {msldTimestamp} {destChild}")

def makeFtpConn(hostname: str, username: str, password: str, timeout: int
        ) -> ftplib.FTP:
    ftpConn = ftplib.FTP(host=hostname, timeout=timeout)
    ftpConn.login(username, password)
    print(f"LOGIN {username}@{hostname}")

    return ftpConn

def main() -> None:
    config = loadConfig()

    # Infinite loop to retry in case of timeout errors
    while True:
        try:
            ftpConn = makeFtpConn(config["hostname"], config["username"], 
                config["password"], config["timeout"])

            ftpMirror(ftpConn, config["srcDir"], config["srcDir"], 
                config["destDir"], config["ignored"])

            ftpConn.close()
            print("BYE")
            break
        except ftplib.all_errors as e:
            print("FTP Error:", e)
            if "timed out" in str(e):
                print("RETRYING...")
            else:
                exit(1)

if __name__ == "__main__":
    main()
