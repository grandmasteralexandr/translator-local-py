# Local FB2 Book Translator

A powerful, context-aware, command-line tool written in Python to translate **FictionBook 2 (FB2)** e-books. It translates books paragraph-by-paragraph using any local or remote LLM (Large Language Model) running an OpenAI-compatible API endpoint (such as `llama.cpp` server, `Ollama`, `LM Studio`, `vLLM`, or `LiteLLM`).

---

## 🌟 Key Features

- **Context-Aware Sliding Window**: Uses a sliding history context containing previous source text and target translations, ensuring consistent terminology, style continuity, and narrative flow across chapters.
- **Two-Pass Translation & Editing**:
  - **Pass 1 (Translation)**: Focuses on an accurate translation of the text inside paragraph tags while respecting the story context.
  - **Pass 2 (Refinement)**: A second pass acting as a master literary editor. It refines style, phrasing, and flow so that the final text reads naturally and idiomatically in the target language.
- **Strict Paragraph Alignment (ID Tagging)**: Wraps paragraphs in `<p id="...">` tags during translation. It maps output back to the FB2 structure by ID, completely preventing issues where LLMs skip paragraphs or combine lines.
- **Robust Fallback Safety**: If the LLM generates empty strings, produces fewer lines than required, or returns invalid XML syntax, the translator safely falls back to the original text for those paragraphs rather than losing content or crashing.
- **Autosave Protection**: Automatically updates and saves progress every 10 chunks, so you never lose your progress during long translation sessions.

---

## 📋 Requirements

- **Python 3.8+**
- An OpenAI-compatible LLM server running locally or remotely.
- Python dependencies:
  - `requests` — for communicating with the LLM API.
  - `lxml` — for parsing and manipulating FB2 XML structures.
  - `tqdm` — for showing progress bars during translation.

---

## ⚙️ Installation

1. Clone or download this repository.
2. Create and activate a Python virtual environment (recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```
3. Install the required dependencies:
   ```bash
   pip install requests lxml tqdm
   ```

---

## 🛠️ Configuration

Before running the translator, open `translate.py` and configure the settings at the top of the file under `# === НАСТРОЙКИ ===`:

```python
# === НАСТРОЙКИ ===
API_URL = "http://localhost:8085/v1/chat/completions"                  # Your LLM server URL
MODEL_NAME = "Qwen3.6-35B-A3B-uncensored-heretic-Q4_K_M.gguf"          # The name of the model loaded in your server
SRC_LANG = "Ukrainian"                                                 # Source language
TARGET_LANG = "French"                                                 # Target language

# Character-count limits (approx. 1 Cyrillic character ~ 3-4 bytes/tokens)
CHUNK_SIZE_CHARS = 5000     # Group size of paragraphs sent at once for translation
CONTEXT_SIZE_CHARS = 1800   # Size of the previous text history sent as context
```

---

## 🚀 Usage

Execute the script from your terminal, passing the input FB2 file path and the target output FB2 file path:

```bash
python translate.py "path/to/input_book.fb2" "path/to/output_book.fb2"
```

### Example:
```bash
python translate.py books-src/iskry_nadezhdy.fb2 books-src/iskry_nadezhdy_en.fb2
```

---

## 🔍 How It Works under the Hood

1. **XML Parsing**: Uses `lxml` to load the FB2 document and extract translateable tags (`<p>`, `<v>`, `<subtitle>`).
2. **Chunking**: Groups contiguous elements into "chunks" up to `CHUNK_SIZE_CHARS` in size, keeping memory and context usage balanced.
3. **Pass 1 - Translation**:
   - Sends the current chunk's paragraphs wrapped in ID tags (e.g. `<p id="0">Paragraph text</p>`).
   - Prepends the previous chunk's source and translation context if available.
4. **Pass 2 - Style Editing**:
   - Takes the rough translation from Pass 1 and passes it through an editor prompt.
   - Provides style-continuity context from previous target text, original source paragraphs, and rough translation.
5. **Reconstruction & Fallbacks**:
   - Parses the ID attributes using regular expressions (e.g., `<p id="(\d+)">`) to rebuild original paragraphs.
   - Cleans the XML fragments safely.
   - Saves progress regularly (every 10 chunks).
