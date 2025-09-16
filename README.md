# FTS

**FTS** (File Transfer System) is a lightweight CLI tool for file transfers, chatrooms, and more.
It’s designed for fast local-network sharing, simple chat creation, and utility management in a single binary.

> \[!CAUTION]
> FTS should NEVER be run on a public network without permission from the **proper authorities**; there are safeguards in place to prevent fts from running on public networks

---

## Features

* Fast local-network file transfers (files or directories)
* Lightweight chatrooms for easy communication
* Discover and manage libraries for easy file sharing
* Aliases and default settings for quick operations
* Progress bars, rate limiting, and background servers
* Security via trusted connections and public-network safeguards

> [!IMPORTANT]
> FTS has currently only been tested on Windows. Other operating systems may not be supported.
---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Example use](#example-use)
- [Project State](#project-state)
- [Contributing](#contributing)
- [License](#license)
- [Commands](#commands)
  - [`open`](#open)
  - [`send`](#send)
  - [`send-dir`](#send-dir)
  - [`close`](#close)
  - [`version`](#version)
  - [`trust`](#trust)
  - [`chat-create`](#chat-create)
  - [`chat-join`](#chat-join)
  - [`library`](#library)
  - [`alias`](#alias)
  - [`defaults`](#defaults)

---

## Installation

Install FTS globally using pip:

```bash
pip install fts-tool
````

To uninstall:

```bash
pip uninstall fts-tool
```

> \[!WARNING]
> Python must be installed and added to your system PATH to run `fts` from the terminal.

---

## Usage

```bash
fts  [--logfile FILE] [-q] [-v] COMMAND [OPTIONS]
```

Run `fts -h` to see all global options.
Each command has its own `-h/--help` flag.

> \[!CAUTION]
> FTS is executed as `fts` in the terminal, but the pip package is named `fts-tool`.

---

## Example Use

```bash
# Start server
fts open downloads --progress

# Send a file
fts send C:\Users\Public\Pictures\family_photo.png 192.168.1.42 --progress
```
One computer opens the sever and the other sends the file

---

## Project State

FTS development is temporarily slowed but will resume in 2–4 weeks. The project is very much alive.

### Upcoming Features

* Address any remaining issues in the current Windows build.
* Include troubleshooting tips (e.g., firewall or network issues).
* Support for common Linux systems.
* Limit FTS usage on public networks instead of disabling it entirely.
* Improve support for directory aliases in the GUI.
* Implement file checksums to detect corrupted transfers.
* Add scheduled or automated file transfers.
* Enable transfer resuming for interrupted downloads.
* Allow third-party extensions (e.g., custom compressors, encryption layers, notifications).

---

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you’d like to change.

---

## License

[MIT](LICENSE)

&#8203;

&#8203;
<hr style="height:10px; border:none; background-color:#333;">
&#8203;

&#8203;

## Commands

### `open`

Start a server and listen for incoming transfers.

```bash
fts open OUTPUT_PATH [OPTIONS]
```

**Arguments:**

* `OUTPUT_PATH` — Directory to save incoming transfers (required)

**Options:**

* `-d, --detached` — Run server in the background
* `-l, --limit SIZE` — Transfer rate limit (e.g. `500KB`, `2MB`, `1GB`)
* `-x, --extract` — Automatically extract transferred archives
* `--progress` — Show progress bars during operations
* `-p, --port PORT` — Override port used (0-65535)
* `--ip ADDR` — Restrict requests to IP or hostname

---

### `send`

Send a file to a target host.

```bash
fts send PATH IP [OPTIONS]
```

**Arguments:**

* `PATH` — File to send (required)
* `IP` — Target IP or hostname (required)

**Options:**

* `-n, --name NAME` — Send file under a different name
* `-p, --port PORT` — Override port used (0-65535)
* `-l, --limit SIZE` — Transfer rate limit Transfer rate limit (e.g. `500KB`, `2MB`, `1GB`)
* `--nocompress` — Skip compression (faster, larger transfers)
* `--progress` — Show progress bars

> \[!NOTE]
> FTS automatically skips compression for files that are already compressed. Enable this option only if FTS still attempts to compress such files.
---

### `send-dir`

Send a directory recursively.

```bash
fts send-dir PATH IP [OPTIONS]
```

**Arguments:**

* `PATH` — Directory to send (required)
* `IP` — Target IP or hostname (required)

**Options:**

* `-n, --name NAME` — Send directory under a different name
* `-p, --port PORT` — Override port used (0-65535)
* `-l, --limit SIZE` — Transfer rate limit Transfer rate limit (e.g. `500KB`, `2MB`, `1GB`)
* `--pyzip` — Use Python’s built-in compression instead of OS-level compression
* `--progress` — Show progress bars

> [!WARNING]
> The target directory will rezip after every send request;
> If this becomes a problem, it is recommended to **pre-zip** directories.

---

### `close`

Close a detached server.

```bash
fts close PROCESS
```

**Arguments:**

* `PROCESS` — One of `all`, `receiving`, or `library`

---

### `version`

Displays the FTS version

```bash
fts version
```

---

### `trust`

Trust an IP certificate, if a certificate has changed.

```bash
fts trust IP
```

**Arguments:**

* `IP` — IP address whose certificate should be trusted

---

### `chat-create`

Create a new chatroom.

```bash
fts chat-create NAME [OPTIONS]
```

**Arguments:**

* `NAME` — Your username (required)

**Options:**

* `-p, --port PORT` — Override port

---

### `chat-join`

Join an existing chatroom.

```bash
fts chat-join NAME IP [OPTIONS]
```

**Arguments:**

* `NAME` — Your username (required)
* `IP` — IP to join (required)

**Options:**

* `-p, --port PORT` — Override port

---

### `library`

Download and manage local file directories.

```bash
fts library TASK [OPTIONS]
```

**Arguments:**

* `TASK` — One of `find`, `open`, `manage`
* `OUTPUT_PATH` — Directory for incoming transfers (required for `find`)

**Options:**

* `-d, --detached` — Run library server in the background (`open` only)

> [!TIP]
> The find command will automatically find open libraries on your local network

---

### `alias`

Manage aliases.

```bash
fts alias ACTION [ARGS]
```

**Arguments:**

* `ACTION` — One of `add`, `remove`, `list`
* `NAME` — Alias name (required for `add/remove`)
* `VALUE` — Alias value (required for `add`)
* `TYPE` — One of `ip` or `dir` (required for `add`)

> [!NOTE]  
> Directory aliases are not supported when selecting commands in the gui

---

### `defaults`

Manage default settings.


```bash
fts defaults [OUTPUT_PATH]
```

**Arguments:**

* `OUTPUT_PATH` — Directory to save incoming transfers

> [!NOTE]  
> Saved defaults exist even if they don’t appear in the GUI. Leaving the argument blank will use your default values.

---
