#!/usr/bin/python3
from datetime import datetime, timezone
import ftplib
from json import load as jsonLoad
from pathlib import Path
from typing import Iterator, Dict, Tuple, List

localTimezone = datetime.now().astimezone().tzinfo
# Load config
config: Dict = jsonLoad(open("config.json"))
srcRoot: Path = Path(config["srcDir"]).absolute()
destRoot: Path = Path(config["destDir"])
ignored: List[str] = config["ignored"]

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

def simplifyMlsd(mlsdResult) -> Dict:
    """ Transform the MLSD result into a JSON-like object.

        Iterator[Tuple[str, Dict[str, str]]] -> Dict[str, Dict[str, str]]
    """

    mlsdResult = list(mlsdResult)[2:] # Remove "." and ".." from results
    mlsdSimple = dict()
    for item in mlsdResult:
        mlsdSimple[item[0]] = item[1]

    return mlsdSimple

def getPathMTime(path: Path) -> datetime:
    """Get local file/directory modtime as a datetime object."""

    return datetime \
        .fromtimestamp(path.stat().st_mtime, localTimezone) \
        .replace(microsecond=0) \
        .astimezone(timezone.utc)

def rmdDeep(ftpConn: ftplib.FTP, dir_: Path) -> None:
    """rm -r implementation."""

    try:
        ftpConn.rmd(str(dir_))
        print(f"RMD {dir_}")
    except ftplib.error_perm as e:
        if int(e.args[0][:3]) != 550: # dir not empty error
            print("FTP error:", e)
            return
    
    # If directory not empty, delete files and recurse into dirs
    destMlsdList = simplifyMlsd(ftpConn.mlsd(str(dir_)))
    for childName, stats in destMlsdList.items():
        if stats["type"] == "dir":
            rmdDeep(ftpConn, dir_ / childName)
        else:
            ftpConn.delete(str(dir_ / childName))
            print(f"DELE {dir_ / childName}")

def ftpMirror(ftpConn: ftplib.FTP, srcDir: Path) -> None:
    """Mirror command implementation."""

    print("directory:", srcDir)
    global srcRoot, destRoot
    destDir: Path = translateSrcToDestDir(srcDir)

    # Get standardized MLSD directory listing:
    destMlsdList = simplifyMlsd(ftpConn.mlsd(str(destDir)))
    print(f"MLSD {destDir}")

    # Delete remote dirs and files which aren't present locally
    # (i.e. detect local deletion and do it remotely )
    srcDirs = [dir_.name for dir_ in srcDir.iterdir() if dir_.is_dir()]
    destDirs = [child for child, stats in destMlsdList.items() 
        if stats["type"] == "dir"]

    for deletedDir in filter(lambda dir_: dir_ not in srcDirs, destDirs):
        rmdDeep(ftpConn, destDir / deletedDir)
        ftpConn.rmd(str(destDir / deletedDir))
    
    srcFiles = [file_.name for file_ in srcDir.iterdir() if file_.is_file()]
    destFiles = [child for child, stats in destMlsdList.items()
        if stats["type"] == "file"]

    for deletedFile in filter(lambda file_: file_ not in srcFiles, destFiles):
        ftpConn.delete(str(destDir / deletedFile))
        print(f"DELETE1 {deletedFile}")

    # Save modtimes as datetime objects in a new key for later comparing
    for destFilename, destStats in destMlsdList.items():
        destStats["mtime"] = msldToDatetime(destStats["modify"])

    for srcChild in srcDir.iterdir():
        # Match against all ignore patterns
        if any([srcChild.match(pattern) for pattern in ignored]):
            print(f"ignore {srcChild}")
            continue

        destChild: Path = destDir / srcChild.name

        # If source is directory, try to remotely create it and recurse into it
        if srcChild.is_dir():
            try:
                ftpConn.mkd(str(destChild))
            # If dir already exists, catch error gracefully
            except ftplib.error_perm as e:
                print(f"SKIP MKD {destChild}")
            else:
                print(f"MKD {destChild}")
            finally:
                ftpMirror(ftpConn, srcChild)
        else:
            if srcChild.name in destMlsdList.keys():
                # Skip file if local modtime is smaller or equal to remote
                srcMTime = getPathMTime(srcChild)
                destMTime = destMlsdList[srcChild.name]["mtime"]
                if srcMTime <= destMTime:
                    print(f"SKIP MTIME {srcChild}")
                    continue

            # Upload file:
            ftpConn.storbinary(f"STOR {destChild}", open(srcChild, "rb"))
            print(f"STOR {srcChild}")


with ftplib.FTP(host=config["hostname"], timeout=1) as ftpConn:
    ftpConn.login(config["username"], config["password"])
    print(f"LOGIN {config['username']}@{config['hostname']}")

    # Start recursive uploading from specified local root dir:
    ftpMirror(ftpConn, srcRoot)
