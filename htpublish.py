#!/usr/bin/python3
import ftplib
from json import load as jsonLoad
from pathlib import Path

# Load config
config: dict = jsonLoad(open("config.json"))
srcRoot: Path = Path(config["srcDir"]).absolute()
destRoot: Path = Path(config["destDir"])

# Convert local paths into remote paths
def translateSrcToDestDir(srcDir: Path) -> Path:
    global srcRoot, destRoot
    rootlessDir: str = str(srcDir).removeprefix(str(srcRoot)).removeprefix("/")
    return destRoot / rootlessDir

# Mirror command implementation
def ftpMirror(ftpConn: ftplib.FTP, srcDir: Path) -> None:
    global srcRoot, destRoot
    destDir: Path = translateSrcToDestDir(srcDir)

    for srcChild in srcDir.iterdir():
        if srcChild.is_dir():
            try:
                ftpConn.mkd(str(destDir))
            except ftplib.error_perm as e:
                print(f"SKIP MKD {destDir}")
            else:
                print(f"MKD {destDir}")
            finally:
                ftpMirror(ftpConn, srcChild)
        else:
            print(f"STOR {srcChild}")
            destChild: Path = destDir / srcChild.name
            ftpConn.storbinary(f"STOR {destChild}", open(srcChild, "rb"))


with ftplib.FTP(host=config["hostname"], timeout=3) as ftpConn:
    ftpConn.login(config["username"], config["password"])

    # Start recursive uploading from specified local root dir:
    ftpMirror(ftpConn, srcRoot)
