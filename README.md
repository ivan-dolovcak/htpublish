# htpublish - script for uploading a website


## About

htpublish is a basic Python script for recursively uploading a directory using
the FTP protocol. It synchronizes the local directory with the specified remote
server directory.


## Get started

1. Clone this repo:

    `git clone https://github.com/ivan-dolovcak/htpublish.git`

1. Install / update to the latest Python 3 version.

1. Install the `colorama` Python module for optional colored output support:

    `pip3 install colorama`

1. Rename `config.template.json` to `config.json` and enter your configuration.
   Here's an example of what a config file might look like:

    ```json
    {
        "hostname": "files.ftp-clean.com",
        "username": "anon123",
        "password": "supersecretpassword",
        "srcDir": "/home/archie/projects/website/app",
        "destDir": "/public_html",
        "ignored": [
            "*.ts",
            "*.scss"
        ]
    }
    ```

    All fields are required except for `"ignored"`. `"ignored"` may contain
    regex patterns, filenames, or specific paths.

1. Run the script from your terminal emulator:

    `cd htpublish && python3 main.py`


## Behavior / flags

The script recursively scans the specified local `srcDir` for new directories
and modified files. If they are found, the script uploads them, given that they
aren't in any of the `ignored` patterns.

If you don't want your specified ignore patterns to apply, pass the `-I` flag
when running the script.

If any local files or directories are deleted, the script detects that and also
deletes their copies on the server. To disable this behavior, pass the `-D` flag
when running the script.

While the script is running, an FTP timeout error may occur, in which case the
script automatically reconnects to the server and starts over. If you want the
script to terminate when a timeout error occurs, pass the `-R` flag. If you are
getting timeout errors often, try tweaking the timeout amount with the `-t`
argument.


## License

All source code is available under the [MIT License](LICENSE.txt).
