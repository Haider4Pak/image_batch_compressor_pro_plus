"""
image_batch_compressor_pro_plus.py

Features:
- Drag & Drop + Add files
- Batch compression with ThreadPoolExecutor
- Resize, Quality, Format conversion
- Preserve metadata (EXIF) toggle
- Progress bar
- Auto-rename on existing files
- Per-file thumbnail preview
- Per-file original & compressed size shown
- Safe GUI updates via queue
"""

import os
import queue
from concurrent.futures import ThreadPoolExecutor
from threading import Thread
from tkinter import *
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD
from PIL import Image, ImageTk

# --- Config ---
CONVERT_OPTIONS = ["Same as input", "jpg", "png", "webp", "jpeg", "bmp"]
THUMBNAIL_SIZE = (64, 48)  # width, height for thumbnails
WORKER_THREADS = 4

# --- GUI-safe queue for worker -> main thread messages ---
msg_q = queue.Queue()

# store PhotoImage refs to avoid garbage collection
thumb_refs = {}

# --- Utility functions ---
def human_kb(size_bytes):
    return f"{size_bytes/1024:.2f} KB" if size_bytes else "-"

def ensure_unique_path(path):
    """If path exists, append _1, _2, ... before extension."""
    base, ext = os.path.splitext(path)
    counter = 1
    candidate = path
    while os.path.exists(candidate):
        candidate = f"{base}_{counter}{ext}"
        counter += 1
    return candidate

def get_exif_bytes(img):
    """Return exif bytes if present in image info; else None"""
    return img.info.get("exif", None)

# --- Worker processing ---
def process_single_file_task(task_id, inp_path, out_dir, quality, resize_flag, new_w, new_h, out_format, preserve_meta):
    """
    Runs in worker thread. After finishing puts a dict into msg_q for GUI update.
    """
    try:
        before_size = os.path.getsize(inp_path)
        img = Image.open(inp_path)

        # store exif bytes if preserving
        exif_bytes = get_exif_bytes(img) if preserve_meta else None

        # Resize if requested
        if resize_flag != "Original" and (new_w or new_h):
            src_w, src_h = img.size
            tgt_w = new_w if new_w else src_w
            tgt_h = new_h if new_h else src_h
            img = img.resize((tgt_w, tgt_h), Image.LANCZOS)

        # Determine target format & extension
        base = os.path.basename(inp_path)
        name, ext = os.path.splitext(base)
        ext = ext.lower()

        if out_format != "Same as input":
            target_ext = "." + out_format.lower()
            target_format = out_format.upper()
            # pillow expects "JPEG" for "jpg"/"jpeg"
            if out_format.lower() in ("jpg", "jpeg"):
                target_format = "JPEG"
        else:
            target_ext = ext
            target_format = None  # let PIL infer from extension

        # Prepare save path & auto-rename if exists
        save_name = f"{name}{target_ext}"
        save_path = os.path.join(out_dir, save_name)
        save_path = ensure_unique_path(save_path)

        # Save kwargs
        save_kwargs = {"optimize": True}
        if target_format is not None:
            save_kwargs["format"] = target_format

        # JPEG/WebP quality applies; PNG does not use 'quality' in same way.
        if target_ext in (".jpg", ".jpeg", ".webp") or (target_format and target_format in ("JPEG", "WEBP")):
            save_kwargs["quality"] = quality

        # Preserve EXIF if requested and available
        if exif_bytes:
            save_kwargs["exif"] = exif_bytes

        # Ensure RGB when saving JPEG (avoid saving paletted PNG as JPEG)
        if save_kwargs.get("format", "").upper() in ("JPEG",) and img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Save
        img.save(save_path, **save_kwargs)
        after_size = os.path.getsize(save_path)


        # Generate thumbnail for GUI (small copy)
        try:
            thumb_img = Image.open(save_path)
            thumb_img.thumbnail(THUMBNAIL_SIZE, Image.LANCZOS)
        except Exception:
            # fallback to original blank thumbnail
            thumb_img = Image.new("RGB", THUMBNAIL_SIZE, (220, 220, 220))

        # Pack result
        msg_q.put({
            "task_id": task_id,
            "status": "done",
            "inp_path": inp_path,
            "out_path": save_path,
            "before_size": before_size,
            "after_size": after_size,
            "thumb": thumb_img,
            "error": None
        })

    except Exception as e:
        msg_q.put({
            "task_id": task_id,
            "status": "error",
            "inp_path": inp_path,
            "out_path": None,
            "before_size": None,
            "after_size": None,
            "thumb": None,
            "error": str(e)
        })


# --- GUI functions ---
def add_files(event=None):
    paths = []
    if event:
        # event.data may contain a Tcl list of filenames
        try:
            paths = root.tk.splitlist(event.data)
        except Exception:
            # fallback: treat as single path
            paths = [event.data]
    else:
        paths = filedialog.askopenfilenames(
            filetypes=[("Images", "*.jpg;*.jpeg;*.png;*.webp;*.bmp")]
        )

    for p in paths:
        # sometimes drag returns a string with surrounding { } or quotes - splitlist handles that above
        p = p.strip()
        if os.path.isfile(p):
            add_file_row(p)

def add_file_row(path):
    # Avoid duplicates: check if path already in tree (hidden 'path' column)
    for child in tree.get_children():
        try:
            if tree.set(child, "path") == path:
                return
        except Exception:
            # if 'path' column missing for some reason, skip check (shouldn't happen)
            pass

    idx = len(tree.get_children()) + 1
    # Insert placeholder row: values correspond to visible columns (#, name, before, after, status, out)
    item = tree.insert("", "end", values=(idx, os.path.basename(path), human_kb(os.path.getsize(path)), "-", "Queued", "-"), tags=("row",))
    # store full path in hidden column 'path'
    tree.set(item, "path", path)

    # placeholder thumbnail
    blank = Image.new("RGB", THUMBNAIL_SIZE, (240, 240, 240))
    photo = ImageTk.PhotoImage(blank)
    thumb_refs[item] = photo
    # set thumbnail as the 'image' for the item; Treeview may show it in the first non-heading column depending on platform
    tree.item(item, image=photo)

def clear_files():
    for child in tree.get_children():
        thumb_refs.pop(child, None)
    tree.delete(*tree.get_children())
    size_label.config(text="")
    progress["value"] = 0

def start_compression():
    rows = tree.get_children()
    if not rows:
        messagebox.showwarning("No files", "Please add image files first.")
        return

    # Validate quality
    try:
        quality = int(quality_input.get())
        if not (1 <= quality <= 100):
            raise ValueError

    except:
        messagebox.showerror("Error", "Quality must be integer 1–100.")
        return

    # resize params
    resize_flag = resize_var.get()
    new_w = new_h = None
    if resize_flag != "Original":
        try:
            new_w = int(width_input.get()) if width_input.get().strip() else None
            new_h = int(height_input.get()) if height_input.get().strip() else None
        except:
            messagebox.showerror("Error", "Width/Height must be integers.")
            return

    out_format = format_var.get()
    preserve_meta = meta_var.get()
    out_dir = filedialog.askdirectory(title="Choose output directory")
    if not out_dir:
        return

    # Prepare list of tasks
    files = []
    for idx, item in enumerate(rows):
        try:
            path = tree.set(item, "path")
        except Exception:
            # If somehow path missing, skip this item
            continue
        files.append((idx, item, path))

    if not files:
        messagebox.showerror("Error", "No valid files to process.")
        return

    # Setup progress
    progress["maximum"] = len(files)
    progress["value"] = 0

    # Mark rows as "Queued"
    for _, item, _ in files:
        tree.set(item, "after", "-")
        tree.set(item, "status", "Queued")

    # Start worker thread to submit tasks
    def worker_submit():
        with ThreadPoolExecutor(max_workers=WORKER_THREADS) as exe:
            futures = []
            for idx, item, path in files:
                # submit
                futures.append(exe.submit(
                    process_single_file_task,
                    idx, path, out_dir, quality, resize_flag, new_w, new_h, out_format, preserve_meta
                ))
            # Wait for all to finish (workers will push updates into msg_q)
            for f in futures:
                f.result()
        # notify completion
        msg_q.put({"control": "all_done"})

    Thread(target=worker_submit, daemon=True).start()
    root.after(100, poll_queue)

def poll_queue():
    """Poll the queue and update GUI. Called on main thread via after()."""
    try:
        while True:
            msg = msg_q.get_nowait()
            # control message
            if msg.get("control") == "all_done":
                progress["value"] = progress["maximum"]
                messagebox.showinfo("Done", "Batch compression completed!")
                continue

            # normal message
            inp_path = msg.get("inp_path")
            # find tree item by path
            target_item = None
            for item in tree.get_children():
                try:
                    if tree.set(item, "path") == inp_path:
                        target_item = item
                        break
                except Exception:
                    continue

            if not target_item:
                continue

            if msg.get("status") == "done":
                before = msg.get("before_size", 0)
                after = msg.get("after_size", 0)
                out_path = msg.get("out_path")
                thumb_img = msg.get("thumb")

                # update thumbnail PhotoImage and set image
                try:
                    photo = ImageTk.PhotoImage(thumb_img)
                    thumb_refs[target_item] = photo
                    tree.item(target_item, image=photo)
                except Exception:
                    pass

                tree.set(target_item, "before", human_kb(before))
                tree.set(target_item, "after", human_kb(after))
                tree.set(target_item, "status", "Done")
                tree.set(target_item, "out", os.path.basename(out_path) if out_path else "-")

                progress["value"] += 1

            elif msg.get("status") == "error":
                err = msg.get("error")
                tree.set(target_item, "status", f"Error: {err}")
                progress["value"] += 1

    except queue.Empty:
        pass

    # continue polling until progress reaches maximum
    if progress["value"] < progress["maximum"]:
        root.after(150, poll_queue)
    else:
        # final GUI refresh: calculate totals
        total_before = 0
        total_after = 0
        for item in tree.get_children():
            b = tree.set(item, "before")
            a = tree.set(item, "after")
            try:
                total_before += float(b.replace(" KB", "")) * 1024
            except:
                pass
            try:
                total_after += float(a.replace(" KB", "")) * 1024
            except:
                pass
        size_label.config(text=f"Total Before: {total_before/1024:.2f} KB   |   Total After: {total_after/1024:.2f} KB")

# --- Build GUI ---
root = TkinterDnD.Tk()
root.title("Image Compressor — PRO+")
root.geometry("900x680")
root.minsize(800, 600)

top_frame = Frame(root)
top_frame.pack(fill=X, padx=8, pady=6)

Label(top_frame, text="Drag & Drop Images or Click Add", font=("Arial", 13, "bold")).pack(side=LEFT)
btn_add = Button(top_frame, text="Add Files", command=add_files)
btn_add.pack(side=RIGHT, padx=4)
btn_clear = Button(top_frame, text="Clear List", command=clear_files)
btn_clear.pack(side=RIGHT)

# Treeview with thumbnail and columns
# IMPORTANT: include hidden "path" column to store the real file path (fixes the TclError)
cols = ("#", "name", "before", "after", "status", "out", "path")
tree_frame = Frame(root)
tree_frame.pack(fill=BOTH, expand=True, padx=8, pady=4)

tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
# We'll use the tree 'image' slot for thumbnails; show a small column for that visually by adding a separate column at left.
tree.heading("#1", text="#")
tree.column("#1", width=36, anchor=CENTER)
tree.heading("name", text="Filename")
tree.column("name", width=360)
tree.heading("before", text="Before")
tree.column("before", width=90, anchor=CENTER)
tree.heading("after", text="After")
tree.column("after", width=90, anchor=CENTER)
tree.heading("status", text="Status")
tree.column("status", width=180)
tree.heading("out", text="Output filename")
tree.column("out", width=220)
# hidden path column (stores full path)
tree.heading("path", text="Path")
tree.column("path", width=0, stretch=False)   # keep hidden but available via tree.set/get

# Vertical scrollbar
vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
tree.configure(yscrollcommand=vsb.set)
vsb.pack(side=RIGHT, fill=Y)
tree.pack(fill=BOTH, expand=True, side=LEFT)

# Drag&Drop binding on the tree area
tree.drop_target_register(DND_FILES)
tree.dnd_bind("<<Drop>>", add_files)

# Options frame
opts = Frame(root)
opts.pack(fill=X, padx=8, pady=6)

Label(opts, text="Quality (1-100):").grid(row=0, column=0,  pady=10, sticky=W)

quality_input = Entry(opts, width=6)
quality_input.insert(0, "70")
quality_input.grid(row=0, column=3, padx=6, pady=10)

# move slider below
def on_slider(val):
    quality_input.delete(0, END)
    quality_input.insert(0, str(int(float(val))))

quality_slider = Scale(opts, from_=1, to=100, orient=HORIZONTAL, command=on_slider)
quality_slider.set(70)
quality_slider.grid(row=0, column=1, columnspan=2, pady=6, sticky="we")





resize_var = StringVar(value="Original")
Label(opts, text="Resize:").grid(row=2, column=0, sticky=W)
OptionMenu(opts, resize_var, "Original", "Custom Size").grid(row=2, column=1, sticky=W)

Label(opts, text="Width:").grid(row=2, column=2, sticky=E)
width_input = Entry(opts, width=8)
width_input.grid(row=2, column=3, padx=4)
Label(opts, text="Height:").grid(row=2, column=4, sticky=E)
height_input = Entry(opts, width=8)
height_input.grid(row=2, column=5, padx=4)

Label(opts, text="Convert to:").grid(row=4, column=0, sticky=W, pady=10)
format_var = StringVar(value="Same as input")
OptionMenu(opts, format_var, *CONVERT_OPTIONS).grid(row=4, column=1, sticky=W)

meta_var = BooleanVar(value=True)
Checkbutton(opts, text="Preserve Metadata (EXIF)", variable=meta_var).grid(row=4, column=2, columnspan=2, sticky=W)

# Progress & control
control_frame = Frame(root)
control_frame.pack(fill=X, padx=8, pady=6)
progress = ttk.Progressbar(control_frame, orient=HORIZONTAL, length=620, mode="determinate")
progress.pack(side=LEFT, padx=6)

btn_start = Button(control_frame, text="Start Compression", bg="green", fg="white", command=start_compression)
btn_start.pack(side=LEFT, padx=6)

size_label = Label(root, text="", font=("Arial", 10))
size_label.pack(pady=4)

# --- Run ---
root.mainloop()
