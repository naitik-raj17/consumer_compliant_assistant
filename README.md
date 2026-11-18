# ConsumerGuard

Offline desktop app that drafts Indian consumer complaints under the Consumer Protection Act, 2019.
Uses a local Ollama LLM (`qwen2.5:1.5b`) with retrieval over a small law knowledge base (`nomic-embed-text`).
If Ollama is not running, drafts are filled from templates instead.

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
