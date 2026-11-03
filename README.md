<img width="1911" height="961" alt="Capture d&#39;écran 2026-11-03 201742" src="https://github.com/user-attachments/assets/4ebd4820-7de7-4642-b3d6-d0faba8b03a4" />

PortSentry Mini
A terminal dashboard that hunts down stale listeners and kills the process holding your port, in one keystroke.

Ever had a dev server stay alive in the background after you closed the terminal, and now localhost:3000 refuses to start? PortSentry Mini lists every TCP port currently in use, shows which process owns it (Node, Python, Docker, or other), and lets you kill it with a single key press.

PortSentry Mini screenshot

Features
Live view of all listening TCP ports, refreshed every 2 seconds
Process identification: name, full command line, owner, and a colored type tag (Node, Python, Docker, Other)
One-key kill: graceful SIGTERM first, escalating to SIGKILL if the process doesn't exit within ~1.5 s
Visual feedback: a red flashing banner with a progress bar while the process is being terminated
Instant filter: search by port, process name, type, or command line
Selection persists across refreshes, so the cursor never jumps under you
Requirements
Python 3.9+
textual and psutil
Linux, macOS, or Windows (see Permissions for caveats)
Installation
bash
git clone https://github.com/<your-username>/PortSentry.py.git
cd PortSentry.py
pip install textual psutil
Or with a virtual environment:

bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install textual psutil
Usage
bash
python PortSentry.py
To see processes owned by other users (including root and most Docker containers), run with elevated privileges:

bash
sudo python PortSentry.py
Keybindings
Key	Action
k / Enter	Kill the process on the selected row
/	Open the filter
Escape	Close the filter and clear it
r	Refresh immediately
q	Quit
Permissions
PortSentry relies on psutil to read the system's socket table. What you can see depends on your privileges:

Without sudo you see your own processes. Listeners owned by other users appear with PID: -, and the header warns you how many are hidden.
With sudo you see everything. Killing a process still requires permission over it, so the banner reports access denied, re-run with sudo when it's not allowed.
Windows may require an administrator terminal to read all listeners.
Notes on Docker
Docker publishes ports through docker-proxy (or a containerd shim), not through the container itself. Killing docker-proxy may leave the container running, and it will sometimes be restarted by Docker. For containers, prefer:

bash
docker ps --filter "publish=3000"
docker stop <container>
PortSentry shows a hint when it detects docker-proxy as the owner.

How it works
psutil.net_connections(kind="tcp") returns sockets in the LISTEN state.
Duplicate entries (the same port on IPv4 and IPv6) are merged into a single row.
Each PID is resolved to its name, command line, and owner. The process type is inferred from those strings.
Kill requests run in a background thread so the UI never freezes. The process gets SIGTERM, then SIGKILL if it's still alive.
Project structure
portsentry-mini/
├── portsentry.py   # the whole application (single file)
├── README.md
└── docs/
    └── screenshot.png
Roadmap
 Optional confirmation before killing
 UDP listeners
 Container-aware kill (docker stop on Docker-owned ports)
 Export the current list to JSON
 Configurable refresh interval and color theme
 Packaging as a standalone binary (pipx install portsentry-mini)
Contributing
Contributions are welcome. Please open an issue first for significant changes. For small fixes, a pull request is fine.

Fork the repository
Create a branch (git checkout -b feature/my-change)
Commit your work and open a pull request
License
MIT. See LICENSE for details.

Acknowledgements
Built with Textual and psutil.
