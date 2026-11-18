# ConsumerGuard

Offline desktop app that drafts Indian consumer complaints under the Consumer Protection Act, 2019.
Uses a local Ollama LLM (`qwen2.5:1.5b`) with retrieval over a small law knowledge base (`nomic-embed-text`).
If Ollama is not running, drafts are filled from templates instead.

## Windows: install the app (end users)

1. Get `ConsumerGuard_Setup.exe` (see [Windows .exe from GitHub Actions](#windows-exe-from-github-actions)).
2. Run it. No admin rights are needed; it installs per-user. If SmartScreen shows
   "Windows protected your PC", click **More info → Run anyway** (the installer is not code-signed).
3. Install Ollama from https://ollama.com/download, then in PowerShell:
   ```powershell
   ollama pull qwen2.5:1.5b
   ollama pull nomic-embed-text
   ```
   Ollama runs in the background after install (tray icon). Without it, drafts fall back to templates.
4. Start **ConsumerGuard** from the Start menu and log in with the default admin (see [Run](#run)).

## Windows: run from source (developers)

Install Python 3.11 from https://www.python.org/downloads/ (tick **Add python.exe to PATH**; Tk is included).

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1      # cmd.exe: .venv\Scripts\activate.bat
pip install -r requirements.txt
python main.py
```

If PowerShell blocks the activate script, run once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## Windows: build the installer locally

```powershell
pyinstaller --noconfirm --clean --onedir --windowed --name ConsumerGuard `
  --add-data "kb_seed;kb_seed" --collect-data customtkinter main.py
```

Then install Inno Setup 6 (https://jrsoftware.org/isdl.php) and compile:

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

The installer is written to `Output\ConsumerGuard_Setup.exe`.
Do not copy a Linux `dist/` folder to Windows; it will not run there.

## Ubuntu setup

```bash
sudo apt install python3-tk python3-venv
python3 -m venv .venv          # Python 3.11 recommended
source .venv/bin/activate
pip install -r requirements.txt

curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:1.5b
ollama pull nomic-embed-text
```

## Run

```bash
python main.py
```

Default admin: `admin@cg.local` / `admin123`. Change this password before real use.

App data (database, PDFs, log):
- Linux: `~/.local/share/ConsumerGuard/`
- Windows: `%APPDATA%\ConsumerGuard\`

Optional environment variables: `CG_DATA_DIR`, `CG_OLLAMA_URL` (default `http://127.0.0.1:11434`),
`CG_LLM_MODEL`, `CG_EMBED_MODEL`.

Knowledge base chunks stored while Ollama was offline can be embedded later from
Admin → Knowledge Base → "Embed missing chunks". This also happens automatically at startup.

## Local Linux build

```bash
./build.sh
./dist/ConsumerGuard/ConsumerGuard
```

## Windows .exe from GitHub Actions

1. Push to the `main` branch. You can also run the `build-windows` workflow manually from the Actions tab.
2. Open the finished run in **Actions → build-windows**.
3. Download the `ConsumerGuard_Setup` artifact, unzip it and run `ConsumerGuard_Setup.exe`.

On Windows, install Ollama from https://ollama.com/download and pull the same two models.

## Troubleshooting

- **Drafts look like plain templates:** Ollama is not reachable. Check `ollama list` shows both models
  and that http://127.0.0.1:11434 responds. Then use Admin → Knowledge Base → "Embed missing chunks".
- **App closes or shows "Unexpected error":** details are in `consumerguard.log` in the app data folder above.
- **"Could not open database":** another copy of the app may be open, or the data folder is not writable.
  Set `CG_DATA_DIR` to a writable folder to test.
- **Ubuntu: `No module named tkinter`:** `sudo apt install python3-tk`, then recreate the venv.
- **Tiny or huge UI on Linux:** set `CG_UI_SCALE`, e.g. `CG_UI_SCALE=1.25 python main.py`.
