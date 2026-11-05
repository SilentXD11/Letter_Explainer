# 📬 Letter Explainer

![CI](https://github.com/SilentXD11/Letter_Explainer/actions/workflows/ci.yml/badge.svg)

**Take a photo of a confusing official letter and get it explained in plain language.**

Letters from HMRC, councils, the NHS, DWP, energy companies, landlords and courts are often hard to understand, especially for elderly people and non-native English speakers. Letter Explainer reads the letter (photo or PDF) and gives back:

- a **simple summary** (optionally in Hindi, Polish, Urdu, etc.)
- **what you need to do and by when**
- an **urgency level** (low / medium / high)
- **money amounts** and **reference numbers**
- **jargon explained** ("liability order", "arrears" and similar terms)
- a **scam warning** if the letter looks suspicious
- a **draft reply** you can copy

Built with **Python · FastAPI · OpenCV · Tesseract OCR · Claude / OpenAI (optional)**.

### The app people come back to
| Feature | Why it matters |
|---|---|
| 📬 **My letters** inbox | Every explained letter is saved (on the device only), searchable and filterable |
| ⏰ **Deadline countdowns** | "8 days left" on the home screen, so nothing gets missed |
| ✅ **To-do checklist** | Actions become tickable tasks with a progress bar (and a small celebration when everything's done) |
| 📅 **Add to calendar** | One tap downloads an `.ics` file with a reminder 2 days before each deadline |
| 🔊 **Listen** | Reads the explanation aloud in the chosen language, for low-vision or low-literacy users |
| 🚨 **Scam mode** | Suspicious letters get a warning, and the to-do list is hidden so nobody "pays the gift card" |
| ✍️ **Editable reply** | Draft reply is saved as you type, with Copy and Open-in-email buttons |
| 🧪 **Try an example** | First-time visitors see results instantly without needing a letter to hand |
| 🌗 **Dark mode · A+ large text** | Comfortable for everyone; preferences are remembered |
| 📱 **Installable app (PWA)** | "Add to Home screen" on a phone; opens offline with your saved letters |

---

## 1. The big problem: "What if the text in the photo isn't visible?"

Phone photos of letters are often tilted, shadowed, dark, blurry or have glare. Plain OCR fails on them. This project handles it in **5 layers** (see `app/pipeline.py`):

| # | Layer | What it does | File |
|---|-------|--------------|------|
| 1 | **Quality check** | Measures blur (variance of Laplacian), brightness, contrast, glare and resolution. If the photo is bad, the user gets *specific* tips ("too dark, move near a window") instead of garbage. | `app/image_quality.py` |
| 2 | **Pre-processing** | Fixes phone rotation (EXIF) → finds the paper and flattens it (perspective warp) → resizes → **removes shadows** (divides out the background) → **deskews** the text → boosts contrast (CLAHE) → binarises (adaptive / Otsu threshold). | `app/preprocess.py` |
| 3 | **Best-of-N OCR** | Runs Tesseract on several cleaned versions and keeps the one with the highest word confidence. Also detects sideways or upside-down pages and rotates them. | `app/ocr.py` |
| 4 | **Vision AI fallback** | If OCR confidence is still below 70%, the cleaned page is sent to a vision LLM (Claude or GPT), which can read text that OCR can't. | `app/llm.py` |
| 5 | **Human check** | The extracted text is always shown and **editable**. The user fixes mistakes and presses "Explain again". If the text is unreadable, the app **refuses to explain it** and asks for a retake, because a wrong explanation of an official letter is worse than none. | `app/static/index.html` |

**Measured on the test photos** (tilted 11°, heavy shadow, slightly blurred, dark):

| | Plain Tesseract | This pipeline |
|---|---|---|
| Word confidence | 0% (nothing read) | **95%** |
| Key facts found (date, amount, reference, "liability order") | 0 / 4 | **4 / 4** |

This result is checked automatically in `tests/test_ocr.py::test_preprocessing_rescues_hard_photo`.

---

## 2. How it works (architecture)

```
 Photo / PDF
     │
     ├── PDF with text layer ──► pypdf extracts text
     ├── Scanned PDF ──────────► render pages (pypdfium2) ──► OCR
     └── Photo ──► quality check ──► pre-process ──► best-of-N Tesseract
                                                      │
                                     confidence < 70%?├──yes──► Vision LLM reads the page
                                                      │           (or ask for a retake)
                                                      ▼
                             Rule-based extractors (dates, £ amounts, refs, urgency, scam signs)
                                                      │  (passed to the LLM as "facts")
                                                      ▼
                         LLM explanation (Claude / OpenAI) ──fails?──► offline rule-based explanation
                                                      │
                                                      ▼
                                 JSON response ──► web page
```

Why use **rules + LLM** together? The regex extractors are deterministic, so dates and amounts are never invented. They're given to the LLM as anchors, they power **offline mode** (no API key needed), and they make the project **fully testable in CI**.

---

## 3. Project structure

```
letter-explainer/
├── app/
│   ├── main.py            # FastAPI routes: /, /health, /api/extract, /api/explain, /api/explain-text
│   ├── pipeline.py        # End-to-end flow + the 5-layer photo strategy
│   ├── image_quality.py   # Blur / dark / glare / resolution checks + retake tips
│   ├── preprocess.py      # OpenCV: flatten page, shadows, deskew, thresholds
│   ├── ocr.py             # Tesseract best-of-N, orientation fix
│   ├── pdf_reader.py      # Digital + scanned PDFs
│   ├── extractors.py      # Regex: dates, deadlines, £, references, urgency, scams
│   ├── llm.py             # Claude / OpenAI / offline providers + prompt
│   ├── schemas.py         # Pydantic models (auto docs at /docs)
│   ├── config.py          # Settings from environment / .env
│   └── static/            # Web app: index.html, app.js, styles.css, PWA (sw.js, manifest, icons)
├── samples/make_sample_letter.py  # Generates realistic test letters & bad photos
├── tests/                 # 33 automated tests (pytest)
├── .github/workflows/ci.yml       # GitHub Actions: lint + tests + Docker check
├── Dockerfile
├── requirements.txt / requirements-dev.txt
└── .env.example
```

---

## 4. Run it on your computer (step by step)

### Step 1: Install Python 3.10+ and Git
- Python: https://www.python.org/downloads/ (on Windows, tick **"Add Python to PATH"**)
- Git: https://git-scm.com/downloads

### Step 2: Install Tesseract OCR (the OCR engine)
| OS | Command |
|----|---------|
| **Windows** | Download the installer from https://github.com/UB-Mannheim/tesseract/wiki, install it, then add `C:\Program Files\Tesseract-OCR` to your PATH |
| **macOS** | `brew install tesseract` |
| **Ubuntu/Debian** | `sudo apt install tesseract-ocr` |

Check that it worked: `tesseract --version`

For letters in other languages, install extra packs (e.g. `sudo apt install tesseract-ocr-hin`) and set `OCR_LANG=eng+hin`.

### Step 3: Set up the project
```bash
cd letter-explainer
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
```

### Step 4: (Optional) Add an AI key
```bash
cp .env.example .env      # Windows: copy .env.example .env
```
Open `.env` and paste **one** key: `ANTHROPIC_API_KEY=...` or `OPENAI_API_KEY=...`.
With **no key** the app still works in **offline mode**, using rule-based explanations with no vision fallback and English only.

### Step 5: Run the tests
```bash
python -m pytest -v
```
You should see `33 passed`.

### Step 6: Start the app
```bash
python -m samples.make_sample_letter   # creates test letters in samples/
uvicorn app.main:app --reload
```
- Web app: http://localhost:8000 (upload `samples/letter_photo.jpg`, then `samples/letter_bad_photo.jpg`)
- API docs: http://localhost:8000/docs
- On your phone (same Wi-Fi): run `uvicorn app.main:app --host 0.0.0.0` and open `http://<your-PC-IP>:8000`

### API example
```bash
curl -F "file=@samples/letter_photo.jpg" -F "language=Hindi" http://localhost:8000/api/explain
```

---

## 5. Put it on GitHub and watch it run (step by step)

### Step 1: Create the repository
1. Go to https://github.com/new
2. Name: `Letter_Explainer`, Public, and **don't** tick "Add a README" (we already have one).
3. Click **Create repository**.

### Step 2: Push the code
From inside the `letter-explainer` folder:
```bash
git init
git add .
git commit -m "Letter Explainer: OCR + AI explanation of official letters"
git branch -M main
git remote add origin https://github.com/SilentXD11/Letter_Explainer.git
git push -u origin main
```
When asked for a password, use a **Personal Access Token** (GitHub → Settings → Developer settings → Personal access tokens), not your account password.

> `.env` is in `.gitignore`, so your API key is **never** uploaded. Double-check with `git status` before committing.

### Step 3: Watch the tests run
1. Open your repo on GitHub → **Actions** tab.
2. You'll see the **CI** workflow running. It:
   - installs Tesseract on a fresh Ubuntu machine,
   - runs `ruff` (code style) and all 33 tests on Python 3.11 and 3.12,
   - builds the Docker image, starts it, and checks `/health`.
3. A **green ✓** means everything works. Click a run to see the logs for each step.
4. Under **Artifacts** at the bottom of a run, download `sample-letters` to see the generated test photos.
5. To re-run manually: Actions → CI → **Run workflow**.

The badge at the top of this README turns green as well.

### Step 4: Run the website on GitHub (Codespaces, nothing to install)
1. On the repo page click **Code → Codespaces → Create codespace on main**.
2. Wait 2–3 minutes. The `.devcontainer` config installs Tesseract and all packages, creates sample letters, and starts the server.
3. A browser tab opens with the website. If it doesn't, open the **Ports** tab and click the globe icon next to port 8000.
4. Upload `samples/letter_photo.jpg` (right-click it in the file explorer → Download first) or a photo of a real letter.
5. Optional: add `ANTHROPIC_API_KEY` under GitHub → Settings → Codespaces → Secrets to turn on AI explanations.
6. When you've finished, stop the codespace (Codespaces → ⋯ → Stop) to save your free hours.

### Step 5 (optional): Deploy a permanent live demo on Render (free)
1. https://render.com → New → **Web Service** → connect your GitHub repo.
2. Render detects the `Dockerfile`, so select **Docker**.
3. Under Environment, add `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`).
4. Deploy. You'll get a public URL like `https://letter-explainer.onrender.com`.

---

## 6. Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | – | Enables AI explanations and the vision fallback |
| `LLM_PROVIDER` | auto | `anthropic`, `openai` or `offline` |
| `ANTHROPIC_MODEL` | `claude-sonnet-5` | Claude model name |
| `OPENAI_MODEL` | `gpt-4.1-mini` | OpenAI model name |
| `OCR_MIN_CONFIDENCE` | `70` | Below this, use vision AI or ask for a retake |
| `OCR_LANG` | `eng` | Tesseract language(s) |
| `MAX_UPLOAD_MB` | `10` | Upload size limit |

## 7. Ideas to extend it
- Add a calendar (.ics) download for deadlines
- Text-to-speech for the explanation
- Multi-page photo upload
- Evaluation set of real (anonymised) letters to measure accuracy
- A RAG step over GOV.UK and Citizens Advice pages for "what are my options?"

## Disclaimer
This tool gives automated explanations, **not legal or financial advice**. Always check the original letter, and contact the sender or [Citizens Advice](https://www.citizensadvice.org.uk/) if you're unsure. Letters contain personal data: when an AI key is set, the letter text/image is sent to that AI provider.
