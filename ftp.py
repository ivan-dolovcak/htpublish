import ftplib
from datetime import datetime, timezone, tzinfo
from pathlib import Path, PurePath
from typing import Any

from logger import Logger


def getFileMTime(path: Path) -> datetime:
    """ Get local file's modtime as a datetime object.
    """

    return datetime \
        .fromtimestamp(path.stat().st_mtime, FTP.localTimezone) \
        .replace(microsecond=0) \
        .astimezone(timezone.utc)

class FTP:
    localTimezone: tzinfo = datetime.now().astimezone().tzinfo or timezone.utc 
    # MSLD uses an almost short ISO format (missing date/time separator):
    mlsdTSFormat: str = "%Y%m%d%H%M%S"
    # Path to last empty directory made in mirror():
    _lastMkd: PurePath|None = None

    def __init__(self, hostname: str, username: str, password: str, 
                 timeout: int):
        self.hostname: str = hostname
        self.username: str = username
        self.password: str = password
        self.timeout: int = timeout
    
    def connect(self) -> None:
        Logger.command(f"LOGIN {self.username}@{self.hostname}")
        
        self.ftpConn = ftplib.FTP(host=self.hostname, timeout=self.timeout)
        self.ftpConn.login(self.username, self.password)

        Logger.ok(f"Logged in {self.username}@{self.hostname}.")
    
    def closeConn(self) -> None:
        Logger.command("QUIT")
        self.ftpConn.close()
        Logger.ok("Closed connection to the server.")

    def mlsd(self, path: PurePath) -> dict[str, dict[str, Any]]:
        """ Convert complex object returned by FTP.mlsd() into a JSON-like
            object.
        """
        Logger.command(f"MLSD {path}")
        mlsdResult = self.ftpConn.mlsd(str(path))
        Logger.info(f"Successfully retrieved listing of directory '{path}'.")

        # Unpack generator and remove "." and ".." from results:
        mlsdResultList = list(mlsdResult)[2:]

        mlsdSimple = dict()
        for item in mlsdResultList:
            mlsdSimple[item[0]] = item[1]
        return mlsdSimple

    def rmdDeep(self, dir_: PurePath) -> None:
        """ FTP rm -r implementation.
        """

        flagRemoved = False
        try:
            Logger.command(f"RMD {dir_}")
            self.ftpConn.rmd(str(dir_))
            flagRemoved = True
            Logger.note(f"Removed empty directory '{dir_}'.")
        except ftplib.error_perm as e:
            ftpErrCode = int(e.args[0][:3]) 
            if ftpErrCode != 550: # dir not empty error
                Logger.error(f"FTP error: {e}")
                return
        
        # If dir not empty, delete files and recurse into other dirs
        mlsdList = self.mlsd(dir_)
        for childName, stats in mlsdList.items():
            if stats["type"] == "dir":
                self.rmdDeep(dir_ / childName)
            else:
                Logger.command(f"DELE {dir_ / childName}")
                self.ftpConn.delete(str(dir_ / childName))
                Logger.note(f"Deleted file '{dir_ / childName}'.")

        if not flagRemoved:
            Logger.command(f"RMD {dir_}")
            self.ftpConn.rmd(str(dir_))
            Logger.note(f"Deleted directory '{dir_}'.")

    def mirror(self, srcDir: Path, srcRoot: Path, destRoot: PurePath, 
               ignoredPatterns) -> None:
        """ Mirror command implementation.
        """

        # Translate local paths into remote paths (switch roots):
        destDir = destRoot / srcDir.relative_to(srcRoot)

        # lastMkd is guaranteed to be empty, so no need to check for files to
        # delete:
        if destDir != FTP._lastMkd:
            # Get standardized MLSD directory listing:
            mlsdList = self.mlsd(destDir)

            # Delete remote dirs and files which aren't present locally
            # (i.e. detect local deletion and do it remotely)
            srcDirs = [
                dir_.name for dir_ in srcDir.iterdir() if dir_.is_dir()]
            srcFiles = [
                file_.name for file_ in srcDir.iterdir() if file_.is_file()]

            for child, childStats in mlsdList.items():
                if childStats["type"] == "dir" and child not in srcDirs:
                    self.rmdDeep(destDir / child)
                elif childStats["type"] == "file" and child not in srcFiles:
                    Logger.command(f"DELE {destDir / child}")
                    self.ftpConn.delete(str(destDir / child))
                    Logger.note(f"Deleted file '{destDir / child}'.")

                
                # Save modtimes as datetime objects in a new key for later
                # comparing. MSLD should give timestamps in UTC.
                childStats["mtime"] = datetime.strptime(childStats["modify"],
                    FTP.mlsdTSFormat).replace(tzinfo=timezone.utc)
        else:
            mlsdList = {}
            Logger.info(f"Skipped checking empty directory '{destDir}'.")

        for srcChild in srcDir.iterdir():
            # Match against all ignore patterns
            if any([srcChild.match(pattern) for pattern in ignoredPatterns]):
                Logger.info(f"Ignore '{srcChild}'.")
                continue

            destChild: PurePath = destDir / srcChild.name

            # If source is directory, try to remotely create it and recurse into
            # it
            if srcChild.is_dir():
                if srcChild.name in mlsdList.keys():
                    Logger.info(f"Skipped making directory '{destChild}' (already exists).")
                else:
                    Logger.command(f"MKD {destChild}")
                    self.ftpConn.mkd(str(destChild))
                    _lastMkd = destChild
                    Logger.ok(f"Created directory '{destChild}.")

                self.mirror(srcChild, srcRoot, destRoot, ignoredPatterns)
                return

            srcMTime = getFileMTime(srcChild)
            if srcChild.name in mlsdList.keys():
                # Skip file if local modtime is smaller or equal to remote
                destMTime = mlsdList[srcChild.name]["mtime"]
                if srcMTime <= destMTime:
                    Logger.info(f"Skipped unmodified file '{srcChild}'.")
                    continue

            # Open in binary read mode since FTP.storbinary() is used
            Logger.command(f"STOR {srcChild}")
            self.ftpConn.storbinary(f"STOR {destChild}", srcChild.open("rb"))

            # Touch the remote file:
            msldTimestamp: str = datetime.strftime(srcMTime, FTP.mlsdTSFormat)
            Logger.command(f"MFMT {msldTimestamp} {destChild}")
            self.ftpConn.sendcmd(f"MFMT {msldTimestamp} {destChild}")

            Logger.ok(f"Uploaded file '{srcChild}'.")

