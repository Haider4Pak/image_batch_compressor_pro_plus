# Image Compressor Pro Plus

A **drag & drop batch image compressor** with preview, resize, format conversion, and metadata preservation.

---

## ✅ Features

- Drag & drop + Add Files
- Batch compression using `ThreadPoolExecutor`
- Resize images
- Quality + format conversion (`JPG`, `PNG`, `WEBP`, `BMP`)
- Preserve metadata (EXIF)
- Per-file progress bar + status
- Auto-rename if file exists
- Thumbnail preview
- Shows original vs compressed size

---

## ✅ Requirements

**Python 3.10+** (tested on Windows)

### Python Modules

```

Pillow
tkinterdnd2
tkinter (usually included)

````

> ✅ If using the **prebuilt EXE**, no Python installation is required.

---

## 📦 Installation (From Source)

### 1) Clone repository
```bash
git clone https://github.com/<username>/ImageCompressorProPlus.git
cd ImageCompressorProPlus
````

### 2) Install dependencies

```bash
pip install Pillow tkinterdnd2
```

> If `pip` fails, ensure Python is added to PATH.

### 3) Run the script

```bash
python image_batch_compressor_pro_plus.py
```

---

## 🚀 Usage

1. Open the app
2. Drag + drop image files OR click **Add Files**
3. Optional:

   * Set Quality (1–100)
   * Resize images (custom size)
   * Select output format (JPG/PNG/WEBP/etc.)
   * Preserve EXIF
4. Click **Start Compression**
5. Choose output folder
6. Observe progress + before/after file sizes

---

## 🏁 Prebuilt Executable (Windows)

You can run the already-built EXE:

```
ImageCompressorProPlus.exe
```

### Build Command (already done)

```bash
pyinstaller --noconfirm --onefile --windowed --icon=compress.ico --name ImageCompressorProPlus image_batch_compressor_pro_plus.py
```

Resulting file location:

```
dist/ImageCompressorProPlus.exe
```

> ✅ No Python required

---

## 🔍 Notes

* PNG recompression uses built-in Pillow optimization.
* **Optional:** You may integrate **Zopfli PNG recompression** for even smaller PNG output.
* If compressed file > original size, original file is kept.

---
