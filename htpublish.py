#!/usr/bin/python3
from datetime import datetime, timezone
import ftplib
from json import load as jsonLoad
from pathlib import Path
from typing import Any, NoReturn
import socket

localTimezone = datetime.now().astimezone().tzinfo
ftpConn: ftplib.FTP
config: dict[str, Any]
srcRoot: Path
destRoot: Path
ignoredPatterns: list[str]

def loadConfig() -> NoReturn:
    global config, srcRoot, destRoot, ignoredPatterns

    # Load config if file exists
    configPath: Path = Path("config.json")
    if not configPath.exists():
        print(f"Error: config file '{configPath}' not found.")
        exit(1)
    with open(configPath) as configFile:
        config = jsonLoad(configFile)

    # Try loading config into globals
    try:
        _ = config["hostname"]
        srcRoot = Path(config["srcDir"]).absolute()
        destRoot = Path(config["destDir"])
        ignoredPatterns = config["ignored"]
    except KeyError as e:
        print(f"Error: missing required key in config: '{e.args[0]}'")
        exit(1)

    if not srcRoot.exists():
        print(f"Error: source dir '{srcRoot}' not found.")
        exit(1)

def setFtpConn() -> NoReturn:
    global config, ftpConn

    ftpConn = ftplib.FTP(host=config["hostname"], timeout=10)

    ftpConn.login(config["username"], config["password"])
    print(f"LOGIN {config['username']}@{config['hostname']}")

def translateSrcToDestDir(srcDir: Path) -> Path:
    """Convert local paths into remote paths."""

    global srcRoot, destRoot
    rootlessDir: str = str(srcDir).removeprefix(str(srcRoot)).removeprefix("/")
    return destRoot / rootlessDir

def msldToDatetime(msld: str) -> datetime:
    """ Convert MSLD (almost ISO) time into a datetime object.

        MSLD time should be in UTC.
    """

    return datetime.strptime(msld, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)

def dateTimeToMsld(dateTime: datetime) -> str:
    """Inverse of msldToDatetime()."""

    return datetime.strftime(dateTime, "%Y%m%d%H%M%S")

def mlsd(path: Path) -> dict[str, dict[str, Any]]:
    global ftpConn

    # try:
    mlsdResult = ftpConn.mlsd(str(path))
    mlsdResult = list(mlsdResult)[2:] # Remove "." and ".." from results

    mlsdSimple = dict()
    for item in mlsdResult:
        mlsdSimple[item[0]] = item[1]
    return mlsdSimple
    # except ftplib.all_errors as e:
        # print("MLSD error:", e)
        # exit(1)

def getPathMTime(path: Path) -> datetime:
    """Get local file/directory modtime as a datetime object."""

    return datetime \
        .fromtimestamp(path.stat().st_mtime, localTimezone) \
        .replace(microsecond=0) \
        .astimezone(timezone.utc)

def rmdDeep(dir_: Path) -> NoReturn:
    """rm -r implementation."""

    global ftpConn

    flagRemoved = False
    try:
        ftpConn.rmd(str(dir_))
        flagRemoved = True
        print(f"RMD {dir_}")
    except ftplib.error_perm as e:
        ftpErrCode: int = int(e.args[0][:3]) 
        if ftpErrCode != 550: # dir not empty error
            print("FTP error:", e)
            return
    
    # If directory not empty, delete files and recurse into dirs
    destMlsdList = mlsd(dir_)
    for childName, stats in destMlsdList.items():
        if stats["type"] == "dir":
            rmdDeep(dir_ / childName)
        else:
            ftpConn.delete(str(dir_ / childName))
            print(f"DELE {dir_ / childName}")

    if not flagRemoved:
        ftpConn.rmd(str(dir_))
        print(f"RMD {dir_}")

lastMkd: Path = None
def ftpMirror(srcDir: Path) -> NoReturn:
    """Mirror command implementation."""

    global ftpConn, srcRoot, destRoot, lastMkd, ignoredPatterns
    destDir: Path = translateSrcToDestDir(srcDir)

    # Get standardized MLSD directory listing
    try:
        destMlsdList = mlsd(destDir)
    except ftplib.all_errors as e:
        print(e, "RETRY")
        setFtpConn()
        ftpMirror(srcDir)
        return
    print(f"MLSD {destDir}")

    # lastMkd is the path of the last created empty directory.
    # It's guaranteed to be empty, so no need to check for files to delete:
    if destDir != lastMkd:
        # Delete remote dirs and files which aren't present locally
        # (i.e. detect local deletion and do it remotely )
        srcDirs = [dir_.name for dir_ in srcDir.iterdir() if dir_.is_dir()]
        destDirs = [child for child, stats in destMlsdList.items() 
            if stats["type"] == "dir"]

        for deletedDir in filter(lambda dir_: dir_ not in srcDirs, destDirs):
            rmdDeep(destDir / deletedDir)
        
        srcFiles = [file_.name for file_ in srcDir.iterdir() if file_.is_file()]
        destFiles = [child for child, stats in destMlsdList.items()
            if stats["type"] == "file"]

        for deletedFile in filter(lambda file_: file_ not in srcFiles, destFiles):
            ftpConn.delete(str(destDir / deletedFile))
            print(f"DELE {deletedFile}")

        # Save modtimes as datetime objects in a new key for later comparing
        for destFilename, destStats in destMlsdList.items():
            destStats["mtime"] = msldToDatetime(destStats["modify"])
    else:
        print(f"SKIP (rm -r) {destDir}")

    for srcChild in srcDir.iterdir():
        # Match against all ignore patterns
        if any([srcChild.match(pattern) for pattern in ignoredPatterns]):
            print(f"SKIP (ignore) {srcChild}")
            continue

        destChild: Path = destDir / srcChild.name

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
                ftpMirror(srcChild)
        else:
            srcMTime = getPathMTime(srcChild)
            if srcChild.name in destMlsdList.keys():
                # Skip file if local modtime is smaller or equal to remote
                destMTime = destMlsdList[srcChild.name]["mtime"]
                if srcMTime <= destMTime:
                    print(f"SKIP (mtime) {srcChild}")
                    continue

            # Upload file:
            ftpConn.storbinary(f"STOR {destChild}", open(srcChild, "rb"))
            print(f"STOR {srcChild}")
            # Update file mtime:
            ftpConn.sendcmd(f"MFMT {dateTimeToMsld(srcMTime)} {destChild}")

def ftpLoop() -> NoReturn:
    global srcRoot
    ftpMirror(srcRoot)
    ftpConn.close()

def main() -> NoReturn:
    loadConfig()
    setFtpConn()

if __name__ == "__main__":
    main()
    try:
        ftpLoop()
    except Exception as e:
        print("Error: ", e)
        print(f"{'=' * 30}RETRYING{'=' * 30}")
        ftpConn.close()
        setFtpConn()
        ftpLoop()
