![FTS Banner](https://github.com/Terabase-Studios/fts/blob/main/assets/icons/banner.png)  

# FTS (File Transfer System)

**FTS** is a lightweight CLI tool and TUI application for fast local-network file transfers and communication. Key features include:

* LAN chat
* Contacts & online users
* Intuitive file transfers with progress display
* Transfer history tracking
* Encrypted file transfers

FTS is designed for local networks and **should never be used on public networks without permission**.  

Check out the [Documentation](https://github.com/Terabase-Studios/fts/wiki) for installation and usage guides.

---

## FTS Aesthetic

FTS leverages [Textual](https://textual.textualize.io/) for a sleek, intuitive TUI and uses a custom logger for clean CLI output.

![FTS App TUI](https://github.com/Terabase-Studios/fts/blob/main/assets/fts_app_overview.png)  
![FTS CLI receiving a file](https://github.com/Terabase-Studios/fts/blob/main/assets/fts_cli_overview.png)

---

## Requirements

* Python 3.9 or higher
* Network access for LAN transfers

> \[!WARNING]
> Python must be installed and correctly added to your system PATH to run `fts` directly from the terminal.  

---

## Installation

Install FTS globally using pip:

```bash
python -m pip install fts-tool
```

## Basic CLI Usage

### Start a server

Start a server to receive files in `Downloads/fts` with a progress bar:

```bash
fts open Downloads/fts --progress
```

### Send a file

Send a file to a running server (replace `127.0.0.1` with the target IP):

```bash
fts send "C:\Users\You\Desktop\project.zip" 127.0.0.1 --progress
```

> \[!NOTE]
> The server must be running and discoverable on the LAN to receive files.

---

## Basic App Usage

Run the FTS App interface (TUI) without any arguments:

```bash
fts
```

From here you can:

* Chat with other users on the local network
* Send and receive files through an intuitive visual interface
* View online users and manage contacts
* Review past transfers in the history panel

> \[!Note]
> A machine must have the App running to be discoverable by other users on the LAN.

---

## Project State

FTS development remains active, and future updates will be released. All issues and pull requests will be addressed promptly.

---

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss your proposed modifications.

* Submit PRs against the `main` branch.
* Follow existing code style and conventions.
* Include tests or examples when possible.
* Respect the [Code of Conduct](https://github.com/Terabase-Studios/fts/blob/main/CODE_OF_CONDUCT.md).

---

## Safety and Usage Notes

* **Please do not run FTS on public networks** without proper authorization.
* FTS is intended for **LAN environments only**.
