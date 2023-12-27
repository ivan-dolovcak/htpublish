import ftplib
from datetime import datetime, timezone
from pathlib import Path, PurePath

from logger import Logger


def getPathMTime(path: Path) -> datetime:
    """Get local file/directory modtime as a datetime object."""

    return datetime \
        .fromtimestamp(path.stat().st_mtime, FTP.localTimezone) \
        .replace(microsecond=0) \
        .astimezone(timezone.utc)

class FTP:
    localTimezone = datetime.now().astimezone().tzinfo
    # MSLD uses an almost short ISO format (missing date/time separator):
    mlsdTSFormat = "%Y%m%d%H%M%S"
    # Path to last empty directory made in mirror():
    _lastMkd: PurePath|None = None

    def __init__(self, hostname: str, username: str, password: str, 
                 timeout: int):
        self.hostname: str = hostname
        self.username: str = username
        self.password: str = password
        self.timeout: int = timeout
    
    def connect(self) -> None:
        self.ftpConn = ftplib.FTP(host=self.hostname, timeout=self.timeout)
        self.ftpConn.login(self.username, self.password)
        Logger.log(Logger.Mode.ok, f"LOGIN {self.username}@{self.hostname}")
    
    def closeConn(self) -> None:
        self.ftpConn.close()
        Logger.log(Logger.Mode.ok, "BYE")

    def mlsd(self, path: PurePath) -> dict[str, dict[str, object]]:
        """Convert complex object returned by FTP.mlsd() into a JSON-like
        object."""

        mlsdResult = self.ftpConn.mlsd(str(path))
        Logger.log(Logger.Mode.ok, f"MLSD {path}")

        # Remove "." and ".." from results:
        mlsdResultList = list(mlsdResult)[2:]

        mlsdSimple = dict()
        for item in mlsdResultList:
            mlsdSimple[item[0]] = item[1]
        return mlsdSimple

    def rmdDeep(self, dir_: PurePath) -> None:
        """FTP rm -r implementation."""

        flagRemoved = False
        try:
            self.ftpConn.rmd(str(dir_))
            flagRemoved = True
            Logger.log(Logger.Mode.note, f"RMD {dir_}")
        except ftplib.error_perm as e:
            ftpErrCode = int(e.args[0][:3]) 
            if ftpErrCode != 550: # dir not empty error
                Logger.log(Logger.Mode.error, f"FTP error: {e}")
                return
        
        # If dir not empty, delete files and recurse into other dirs
        mlsdList = self.mlsd(dir_)
        for childName, stats in mlsdList.items():
            if stats["type"] == "dir":
                self.rmdDeep(dir_ / childName)
            else:
                self.ftpConn.delete(str(dir_ / childName))
                Logger.log(Logger.Mode.note, f"DELE {dir_ / childName}")

        if not flagRemoved:
            self.ftpConn.rmd(str(dir_))
            Logger.log(Logger.Mode.note, f"RMD {dir_}")

    def mirror(self, srcDir: Path, srcRoot: Path, destRoot: PurePath, 
               ignoredPatterns) -> None:
        """Mirror command implementation."""

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
                    self.ftpConn.delete(str(destDir / child))
                
                # Save modtimes as datetime objects in a new key for later
                # comparing. MSLD should give timestamps in UTC.
                childStats["mtime"] = datetime.strptime(childStats["modify"],
                    FTP.mlsdTSFormat).replace(tzinfo=timezone.utc)
        else:
            mlsdList = {}
            Logger.log(Logger.Mode.info, f"SKIP (rmcheck) {destDir}")

        for srcChild in srcDir.iterdir():
            # Match against all ignore patterns
            if any([srcChild.match(pattern) for pattern in ignoredPatterns]):
                Logger.log(Logger.Mode.info, f"SKIP (ignore) {srcChild}")
                continue

            destChild: PurePath = destDir / srcChild.name

            # If source is directory, try to remotely create it and recurse into
            # it
            if srcChild.is_dir():
                if srcChild.name in mlsdList.keys():
                    Logger.log(Logger.Mode.info,
                        f"SKIP MKD (already exists) {destChild}")
                else:
                    self.ftpConn.mkd(str(destChild))
                    _lastMkd = destChild
                    Logger.log(Logger.Mode.ok, f"MKD {destChild}")

                self.mirror(srcChild, srcRoot, destRoot, ignoredPatterns)
                return

            srcMTime = getPathMTime(srcChild)
            if srcChild.name in mlsdList.keys():
                # Skip file if local modtime is smaller or equal to remote
                destMTime = mlsdList[srcChild.name]["mtime"]
                if srcMTime <= destMTime:
                    Logger.log(Logger.Mode.info, f"SKIP (mtime) {srcChild}")
                    continue

            # Open in binary read mode since FTP.storbinary() is used
            self.ftpConn.storbinary(f"STOR {destChild}", srcChild.open("rb"))
            Logger.log(Logger.Mode.ok, f"STOR {srcChild}")

            msldTimestamp: str = datetime.strftime(srcMTime, FTP.mlsdTSFormat)
            # Touch the remote file:
            self.ftpConn.sendcmd(f"MFMT {msldTimestamp} {destChild}")
            Logger.log(Logger.Mode.ok, f"MFMT {destChild}")
