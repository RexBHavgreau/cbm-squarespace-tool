"""
CBM Article Converter
Version 1.5.1

A small window: choose an article, convert it, read what happened.
Works on Windows and macOS. Nothing to install beyond the app itself.
"""
import pathlib
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

import core


# ----------------------------------------------------------------- dialogs --

class GuideWindow(tk.Toplevel):
    """Read one of the bundled documents without leaving the app."""

    def __init__(self, parent, title, text):
        super().__init__(parent)
        self.title(title)
        self.minsize(640, 520)
        self.transient(parent)
        box = scrolledtext.ScrolledText(self, wrap="word", font="TkFixedFont",
                                        padx=14, pady=12)
        box.pack(fill="both", expand=True)
        box.insert("1.0", text)
        box.configure(state="disabled")
        tk.Button(self, text="Close", width=10, command=self.destroy).pack(pady=10)
        self.geometry(f"+{parent.winfo_rootx() + 50}+{parent.winfo_rooty() + 40}")


class CopyWindow(tk.Toplevel):
    """Show generated text with a button that puts it on the clipboard."""

    def __init__(self, parent, title, text):
        super().__init__(parent)
        self.title(title)
        self.minsize(680, 520)
        self.transient(parent)
        self.text = text
        box = scrolledtext.ScrolledText(self, wrap="none", font="TkFixedFont",
                                        padx=12, pady=10)
        box.pack(fill="both", expand=True)
        box.insert("1.0", text)
        box.configure(state="disabled")
        row = tk.Frame(self)
        row.pack(fill="x", pady=10)
        self.copied = tk.Label(row, text="", fg="#2a7")
        self.copied.pack(side="left", padx=18)
        tk.Button(row, text="Close", width=10, command=self.destroy).pack(side="right", padx=18)
        tk.Button(row, text="Copy all", width=12, command=self.copy).pack(side="right")
        self.geometry(f"+{parent.winfo_rootx() + 40}+{parent.winfo_rooty() + 30}")

    def copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.text)
        self.copied.configure(text="Copied.")


class PicturePlacer(tk.Toplevel):
    """
    Paste the address of each uploaded picture and put them into the article.

    An address cannot be known before the picture is uploaded, so this is a
    second pass rather than something the conversion can do.
    """

    def __init__(self, parent, path, text, waiting, say):
        super().__init__(parent)
        self.path, self.text, self.say = path, text, say
        self.title("Place the pictures")
        self.transient(parent)
        tk.Label(self, text=path.name, font=("Helvetica", 11, "bold"),
                 anchor="w").pack(fill="x", padx=18, pady=(16, 2))
        tk.Label(self, anchor="w", justify="left", fg="#666", wraplength=560,
                 text=("Upload each picture to the site, copy its address, and "
                       "paste it here. Leave one blank to keep its marker for "
                       "now.")).pack(fill="x", padx=18, pady=(0, 10))
        self.fields = {}
        for item in waiting:
            line = tk.Frame(self)
            line.pack(fill="x", padx=18, pady=3)
            label = item["file"] + ("" if item["alt"] else "   (no alt text)")
            tk.Label(line, text=label, width=28, anchor="w",
                     fg="#333" if item["alt"] else "#A8442A").pack(side="left")
            var = tk.StringVar()
            tk.Entry(line, textvariable=var, width=52).pack(side="left")
            self.fields[item["file"]] = var
        foot = tk.Frame(self)
        foot.pack(fill="x", padx=18, pady=14)
        tk.Button(foot, text="Close", width=9, command=self.destroy).pack(side="right")
        tk.Button(foot, text="Place them", width=12,
                  command=self.place).pack(side="right", padx=8)
        self.geometry(f"+{parent.winfo_rootx() + 40}+{parent.winfo_rooty() + 50}")

    def place(self):
        addresses = {name: var.get() for name, var in self.fields.items()}
        if not any(a.strip() for a in addresses.values()):
            messagebox.showwarning("Nothing to place",
                                   "No addresses have been pasted in.")
            return
        done, placed, left = core.place_pictures(self.text, addresses)
        target = self.path.with_name(self.path.stem + " (with pictures)"
                                     + self.path.suffix)
        target.write_bytes(done.replace("\r\n", "\n")
                           .replace("\n", "\r\n").encode("utf-8"))
        self.say("")
        self.say(f"Placed {placed} picture(s); {left} still waiting.")
        self.say(f"    wrote {target.name}")
        self.destroy()


class CardBuilder(tk.Toplevel):
    """
    Build the HTML for one article link, for a profile page. The address is
    enough: the rest is read from the site, and can be edited before the
    card is made.
    """

    FIELDS = [("title", "Title"), ("date", "Date"), ("excerpt", "Excerpt"),
              ("image", "Image address")]

    def __init__(self, parent, say):
        super().__init__(parent)
        self.say = say
        self.title("Build an article card")
        self.resizable(False, False)
        self.transient(parent)
        tk.Label(self, text="Article address", anchor="w",
                 font=("Helvetica", 11, "bold")).pack(fill="x", padx=18, pady=(16, 2))
        self.url = tk.StringVar()
        row = tk.Frame(self)
        row.pack(fill="x", padx=18)
        tk.Entry(row, textvariable=self.url, width=52).pack(side="left")
        tk.Button(row, text="Look up", command=self.lookup).pack(side="left", padx=8)
        tk.Label(self, anchor="w", fg="#666", justify="left", wraplength=470,
                 text=("Looking it up fills in the rest. Anything can be edited "
                       "before the card is built, and a blank field is simply "
                       "left out.")).pack(fill="x", padx=18, pady=(4, 10))
        self.entries = {}
        for key, label in self.FIELDS:
            line = tk.Frame(self)
            line.pack(fill="x", padx=18, pady=2)
            tk.Label(line, text=label, width=14, anchor="w").pack(side="left")
            var = tk.StringVar()
            tk.Entry(line, textvariable=var, width=48).pack(side="left")
            self.entries[key] = var
        self.include_style = tk.BooleanVar(value=True)
        tk.Checkbutton(self, anchor="w", variable=self.include_style,
                       text="Include the styling (leave off when adding to an "
                            "existing list)").pack(fill="x", padx=18, pady=(8, 0))
        foot = tk.Frame(self)
        foot.pack(fill="x", padx=18, pady=14)
        tk.Button(foot, text="Close", width=9, command=self.destroy).pack(side="right")
        tk.Button(foot, text="Build", width=9, command=self.build).pack(side="right", padx=8)
        self.geometry(f"+{parent.winfo_rootx() + 50}+{parent.winfo_rooty() + 60}")

    def lookup(self):
        try:
            found = core.fetch_article(self.url.get())
        except core.UpdateError as exc:
            messagebox.showwarning("Could not look it up", str(exc))
            return
        for key, var in self.entries.items():
            var.set(found.get(key, ""))
        self.url.set(found.get("url", self.url.get()))

    def build(self):
        entry = {key: var.get().strip() for key, var in self.entries.items()}
        entry["url"] = self.url.get().strip()
        if not entry["url"] or not entry["title"]:
            messagebox.showwarning(
                "Not enough to build with",
                "An address and a title are the least it needs.")
            return
        CopyWindow(self, "Article card",
                   core.article_card(entry, with_style=self.include_style.get()))


class TemplateChoice(tk.Toplevel):
    """Use the remembered template, or pick a different one."""

    def __init__(self, parent, template):
        super().__init__(parent)
        self.result = None
        self.title("Which template?")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        tk.Label(self, text="Add the house styles from this template?",
                 font=("Helvetica", 12, "bold"), anchor="w").pack(
                 fill="x", padx=18, pady=(18, 6))
        tk.Label(self, text=template.name, anchor="w").pack(fill="x", padx=18)
        tk.Label(self, text=str(template.parent), anchor="w", fg="#777",
                 wraplength=420, justify="left").pack(fill="x", padx=18, pady=(0, 14))
        row = tk.Frame(self)
        row.pack(fill="x", padx=18, pady=(0, 18))
        tk.Button(row, text="Use this template", width=18,
                  command=lambda: self.done("use")).pack(side="left")
        tk.Button(row, text="Choose another…", width=16,
                  command=lambda: self.done("other")).pack(side="left", padx=8)
        tk.Button(row, text="Cancel", width=10,
                  command=lambda: self.done(None)).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", lambda: self.done(None))
        self.update_idletasks()
        self.geometry(f"+{parent.winfo_rootx() + 40}+{parent.winfo_rooty() + 60}")
        self.wait_window(self)

    def done(self, value):
        self.result = value
        self.destroy()


class DroppedFiles(tk.Toplevel):
    """
    Shown when an article is dropped onto the application. Converting
    straight away is convenient, but the settings may have moved since last
    time, so they are spelled out before anything happens.
    """

    def __init__(self, parent, names, settings_lines):
        super().__init__(parent)
        self.result = None
        self.title("Convert now?")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        heading = names[0] if len(names) == 1 else f"{len(names)} files"
        tk.Label(self, text=heading, font=("Helvetica", 12, "bold"),
                 anchor="w", wraplength=420, justify="left").pack(
                 fill="x", padx=18, pady=(18, 2))
        if len(names) > 1:
            tk.Label(self, text="\n".join(names[:6]) +
                     ("\n…" if len(names) > 6 else ""),
                     anchor="w", justify="left", fg="#666").pack(fill="x", padx=18)

        tk.Label(self, text="Settings in use", anchor="w", fg="#444",
                 font=("Helvetica", 10, "bold")).pack(fill="x", padx=18, pady=(14, 2))
        if settings_lines:
            body = "\n".join("\u2022  " + line for line in settings_lines)
        else:
            body = "\u2022  everything at its default"
        tk.Label(self, text=body, anchor="w", justify="left", fg="#666",
                 wraplength=420).pack(fill="x", padx=18)

        row = tk.Frame(self)
        row.pack(fill="x", padx=18, pady=18)
        tk.Button(row, text="Convert now", width=14,
                  command=lambda: self.done("convert")).pack(side="left")
        tk.Button(row, text="Open, don\u2019t convert yet", width=22,
                  command=lambda: self.done("open")).pack(side="left", padx=8)
        tk.Button(row, text="Cancel", width=9,
                  command=lambda: self.done(None)).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", lambda: self.done(None))
        self.update_idletasks()
        self.geometry(f"+{parent.winfo_rootx() + 40}+{parent.winfo_rooty() + 60}")
        self.wait_window(self)

    def done(self, value):
        self.result = value
        self.destroy()


class Preferences(tk.Toplevel):
    """What goes into an article, in what order, and how it is written."""

    def __init__(self, parent, opts, on_save):
        super().__init__(parent)
        self.opts = opts
        self.on_save = on_save
        self.title("Preferences")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        pad = {"padx": 18}

        # --- the blocks, in order ---
        tk.Label(self, text="What goes into an article", anchor="w",
                 font=("Helvetica", 12, "bold")).pack(fill="x", pady=(18, 2), **pad)
        tk.Label(self, anchor="w", justify="left", fg="#666",
                 text=("Tick to include. Select one and move it to change the order.\n"
                       "The article body is always included; footnotes always come last.")
                 ).pack(fill="x", **pad)

        body = tk.Frame(self)
        body.pack(fill="x", pady=(8, 0), **pad)
        self.listbox = tk.Listbox(body, height=6, exportselection=False,
                                  activestyle="none", width=34)
        self.listbox.pack(side="left")
        buttons = tk.Frame(body)
        buttons.pack(side="left", padx=10)
        tk.Button(buttons, text="Move up", width=11,
                  command=lambda: self.move(-1)).pack(pady=2)
        tk.Button(buttons, text="Move down", width=11,
                  command=lambda: self.move(1)).pack(pady=2)
        tk.Button(buttons, text="Include / omit", width=13,
                  command=self.toggle).pack(pady=(12, 2))

        self.order = list(opts["order"])
        self.include = dict(opts["include"])
        self.refresh()

        tk.Label(self, anchor="w", justify="left", fg="#666", wraplength=430,
                 text=("How an article LOOKS \u2014 headings, blurb, pull quotes and "
                       "the rest \u2014 is set under Designer \u203a Article styles.")
                 ).pack(fill="x", pady=(16, 0), **pad)

        # --- reading time ---
        tk.Label(self, text="Reading time", anchor="w",
                 font=("Helvetica", 12, "bold")).pack(fill="x", pady=(18, 2), **pad)
        wpm_row = tk.Frame(self)
        wpm_row.pack(fill="x", **pad)
        self.wpm = tk.StringVar(value=str(opts["words_per_minute"]))
        tk.Spinbox(wpm_row, from_=80, to=400, increment=10, width=6,
                   textvariable=self.wpm).pack(side="left")
        tk.Label(wpm_row, fg="#666",
                 text="  words a minute. Lower for a heavier read.").pack(side="left")

        # --- where files go ---
        tk.Label(self, text="Where finished files go", anchor="w",
                 font=("Helvetica", 12, "bold")).pack(fill="x", pady=(18, 2), **pad)
        self.output = tk.StringVar(value=opts["output"])
        tk.Radiobutton(self, text="Beside the original", value="beside",
                       variable=self.output, anchor="w", command=self.sync
                       ).pack(fill="x", **pad)
        folder_row = tk.Frame(self)
        folder_row.pack(fill="x", **pad)
        tk.Radiobutton(folder_row, text="This folder:", value="folder",
                       variable=self.output, command=self.sync).pack(side="left")
        self.folder = tk.StringVar(value=opts["output_folder"])
        self.folder_label = tk.Label(folder_row, textvariable=self.folder, fg="#666",
                                     anchor="w", wraplength=240)
        self.folder_label.pack(side="left", fill="x", expand=True)
        tk.Button(folder_row, text="Choose…", command=self.pick_folder).pack(side="right")

        # --- buttons ---
        foot = tk.Frame(self)
        foot.pack(fill="x", pady=18, **pad)
        tk.Button(foot, text="Reset to defaults", width=16,
                  command=self.reset).pack(side="left")
        tk.Button(foot, text="Cancel", width=10, command=self.destroy).pack(side="right")
        tk.Button(foot, text="Save", width=10,
                  command=self.save).pack(side="right", padx=8)

        self.sync()
        self.update_idletasks()
        self.geometry(f"+{parent.winfo_rootx() + 30}+{parent.winfo_rooty() + 30}")

    # -- the block list --
    def refresh(self, select=None):
        self.listbox.delete(0, "end")
        for name in self.order:
            mark = "x" if self.include.get(name) else " "
            label = core.BLOCK_LABELS[name]
            if name == core.FIXED_BLOCK:
                label += "   (always included)"
            self.listbox.insert("end", f" [{mark}]  {label}")
        self.listbox.insert("end", "       Footnotes   (always last)")
        self.listbox.itemconfigure(len(self.order), foreground="#999")
        if select is not None:
            self.listbox.selection_set(select)
            self.listbox.activate(select)

    def selected(self):
        choice = self.listbox.curselection()
        if not choice or choice[0] >= len(self.order):
            return None
        return choice[0]

    def move(self, step):
        index = self.selected()
        if index is None:
            return
        target = index + step
        if not 0 <= target < len(self.order):
            return
        self.order[index], self.order[target] = self.order[target], self.order[index]
        self.refresh(select=target)

    def toggle(self):
        index = self.selected()
        if index is None:
            return
        name = self.order[index]
        if name == core.FIXED_BLOCK:
            messagebox.showinfo("Always included",
                                "The article body cannot be left out, though it "
                                "can be moved.")
            return
        self.include[name] = not self.include.get(name)
        self.refresh(select=index)

    # -- the rest --
    def pick_folder(self):
        chosen = filedialog.askdirectory(title="Where should finished files go?")
        if chosen:
            self.folder.set(chosen)
            self.output.set("folder")
            self.sync()

    def sync(self):
        """Keep the dialog honest about what depends on what."""
        state = "normal" if self.output.get() == "folder" else "disabled"
        self.folder_label.configure(fg="#333" if state == "normal" else "#999")

    def reset(self):
        if not messagebox.askyesno(
                "Reset to defaults",
                "Put every setting back to the way it comes out of the box?"):
            return
        self.order = list(core.DEFAULTS["order"])
        self.include = dict(core.DEFAULTS["include"])
        self.wpm.set(str(core.DEFAULTS["words_per_minute"]))
        self.output.set(core.DEFAULTS["output"])
        self.folder.set(core.DEFAULTS["output_folder"])
        self.refresh()
        self.sync()

    def save(self):
        try:
            words = int(self.wpm.get())
        except ValueError:
            words = core.DEFAULTS["words_per_minute"]
        data = core.load_settings()
        data.update({
            "order": self.order,
            "include": self.include,
            "words_per_minute": max(80, min(400, words)),
            "output": self.output.get(),
            "output_folder": self.folder.get(),
        })
        core.save_settings(data)
        self.destroy()
        self.on_save()


class StylePanel(tk.Toplevel):
    """
    Every style an article uses, laid out by element. The controls are built
    from core.STYLE_SCHEMA, so adding one there is enough.
    """

    def __init__(self, parent, on_save):
        super().__init__(parent)
        self.on_save = on_save
        self.title("Article styles")
        self.minsize(560, 620)
        self.transient(parent)
        self.values = core.style_values()
        self.vars = {}

        top = tk.Frame(self)
        top.pack(fill="x", padx=18, pady=(16, 6))
        tk.Label(top, text="Article styles", font=("Helvetica", 13, "bold"),
                 anchor="w").pack(fill="x")
        tk.Label(top, anchor="w", justify="left", fg="#666", wraplength=500,
                 text=("These produce the stylesheet that goes into Squarespace's "
                       "Custom CSS. Once it is there, a change here and a fresh "
                       "paste restyles every article on the site, including ones "
                       "published long ago.")).pack(fill="x")

        # a scrolling area, since there are a lot of controls
        canvas = tk.Canvas(self, highlightthickness=0, height=420)
        bar = tk.Scrollbar(self, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(18, 0), pady=8)
        bar.pack(side="right", fill="y", pady=8)

        for group, items in core.STYLE_SCHEMA:
            tk.Label(inner, text=group, font=("Helvetica", 11, "bold"),
                     anchor="w").pack(fill="x", pady=(12, 2))
            for key, label, kind, _default in items:
                self.add_control(inner, key, label, kind)

        foot = tk.Frame(self)
        foot.pack(fill="x", padx=18, pady=14)
        tk.Button(foot, text="Reset to defaults", width=16,
                  command=self.reset).pack(side="left")
        tk.Button(foot, text="Preview in browser", width=17,
                  command=self.preview).pack(side="left", padx=8)
        tk.Button(foot, text="Close", width=9, command=self.destroy).pack(side="right")
        tk.Button(foot, text="Save", width=9,
                  command=self.save).pack(side="right", padx=8)

    def add_control(self, parent, key, label, kind):
        row = tk.Frame(parent)
        row.pack(fill="x", pady=1)
        value = self.values.get(key)
        if kind == "bool":
            var = tk.BooleanVar(value=bool(value))
            tk.Checkbutton(row, text=label, variable=var, anchor="w").pack(
                side="left", fill="x", expand=True)
        elif kind in ("align", "align_none"):
            var = tk.StringVar(value=str(value))
            tk.Label(row, text=label, width=22, anchor="w").pack(side="left")
            choices = [("left", "Left"), ("center", "Centred"), ("right", "Right")]
            if kind == "align_none":
                choices.append(("none", "Site decides"))
            for val, text in choices:
                tk.Radiobutton(row, text=text, value=val, variable=var).pack(side="left")
        elif kind == "text":
            var = tk.StringVar(value=str(value))
            tk.Label(row, text=label, width=22, anchor="w").pack(side="left")
            tk.Entry(row, textvariable=var, width=26).pack(side="left")
        else:
            var = tk.StringVar(value=str(value))
            tk.Label(row, text=label, width=22, anchor="w").pack(side="left")
            step = {"em": 0.05, "num": 0.1, "pct": 1, "px": 1, "in": 0.05,
                    "weight": 100}.get(kind, 1)
            tk.Spinbox(row, from_=0, to=2000, increment=step, width=8,
                       textvariable=var).pack(side="left")
            tk.Label(row, text={"em": "em", "pct": "%", "px": "px", "in": "in",
                                "num": "", "weight": ""}.get(kind, ""),
                     fg="#888").pack(side="left", padx=4)
        self.vars[key] = (var, kind)

    def collect(self):
        out = {}
        for key, (var, kind) in self.vars.items():
            raw = var.get()
            if kind == "bool":
                out[key] = bool(raw)
            elif kind in ("align", "align_none", "text"):
                out[key] = str(raw)
            else:
                try:
                    number = float(raw)
                except (TypeError, ValueError):
                    number = float(core.STYLE_DEFAULTS[key])
                out[key] = int(number) if number == int(number) else number
        return out

    def reset(self):
        if not messagebox.askyesno("Reset styles",
                                   "Put every style back to the way it comes "
                                   "out of the box?"):
            return
        for key, (var, kind) in self.vars.items():
            var.set(core.STYLE_DEFAULTS[key])

    def preview(self):
        """Write a sample article with these settings and open it."""
        import tempfile
        import webbrowser
        opts = core.options()
        opts["style"] = self.collect()
        opts["heading_align"] = opts["style"].get("heading_align", "none")
        page = core.sample_article(opts)
        target = pathlib.Path(tempfile.gettempdir()) / "cbm-style-preview.html"
        target.write_text(page, encoding="utf-8")
        webbrowser.open(target.as_uri())

    def save(self):
        data = core.load_settings()
        style = self.collect()
        data["style"] = style
        data["heading_align"] = style.get("heading_align", "none")
        core.save_settings(data)
        self.destroy()
        self.on_save()


# -------------------------------------------------------------- the window --

class App:
    def __init__(self, root, opening=()):
        self.root = root
        self.paths = [pathlib.Path(p) for p in opening]
        self.template = core.remembered_template()
        self.opts = core.options()
        self.last_output = None
        root.title(f"CBM Article Converter  -  {core.VERSION}")
        root.minsize(680, 520)

        self.build_menu()

        tk.Label(root, text="Article to Squarespace HTML",
                 font=("Helvetica", 16, "bold"), anchor="w").pack(
                 fill="x", padx=16, pady=(16, 2))
        tk.Label(root, anchor="w", justify="left", fg="#555",
                 text=("Choose a Word document (.docx) or an InDesign export (.html),\n"
                       "or drop one onto this application.")
                 ).pack(fill="x", padx=16)

        row = tk.Frame(root)
        row.pack(fill="x", padx=16, pady=10)
        self.choose_btn = tk.Button(row, text="Choose Article…", width=17,
                                    command=self.choose)
        self.choose_btn.pack(side="left")
        self.convert_btn = tk.Button(row, text="Convert", width=12,
                                     state="disabled", command=self.start)
        self.convert_btn.pack(side="left", padx=8)
        self.styles_btn = tk.Button(row, text="Apply Styles to DOCX", width=20,
                                    command=self.add_styles)
        self.styles_btn.pack(side="left", padx=(0, 8))

        self.chosen = tk.Label(root, text="Nothing chosen yet", anchor="w", fg="#555")
        self.chosen.pack(fill="x", padx=16)

        trow = tk.Frame(root)
        trow.pack(fill="x", padx=16, pady=(8, 0))
        self.template_label = tk.Label(trow, anchor="w", fg="#555")
        self.template_label.pack(side="left", fill="x", expand=True)
        tk.Button(trow, text="Change…", command=self.pick_template).pack(side="right")
        self.show_template()

        self.log = scrolledtext.ScrolledText(root, height=15, wrap="word",
                                             state="disabled", font="TkFixedFont")
        self.log.pack(fill="both", expand=True, padx=16, pady=(10, 16))

        self.say(f"Version {core.VERSION}. Ready.")
        if self.paths:
            self.accept(self.paths)
            self.root.after(250, self.ask_about_dropped)
        if self.opts.get("check_at_startup", True):
            self.root.after(800, self.check_updates_quietly)

    def ask_about_dropped(self):
        """An article arrived by being dropped on the app. Confirm first."""
        names = [p.name for p in self.paths]
        choice = DroppedFiles(self.root, names, core.non_default(self.opts)).result
        if choice == "convert":
            self.start()
        elif choice is None:
            self.paths = []
            self.chosen.config(text="Nothing chosen yet", fg="#555")
            self.convert_btn.config(state="disabled")
            self.say("Cancelled. Nothing was converted.")
        else:
            self.say("Ready when you are. Press Convert.")

    # ---------------------------------------------------------------- menu --
    def build_menu(self):
        bar = tk.Menu(self.root)

        prefs = tk.Menu(bar, tearoff=0)
        prefs.add_command(label="Preferences…", command=self.open_preferences)
        prefs.add_separator()
        self.auto_check = tk.BooleanVar(
            value=self.opts.get("check_at_startup", True))
        prefs.add_checkbutton(label="Check for updates at startup",
                              variable=self.auto_check,
                              command=self.save_auto_check)
        prefs.add_separator()
        prefs.add_command(label="Desktop shortcut\u2026",
                          command=self.desktop_shortcut)
        prefs.add_separator()
        prefs.add_command(label="Reset everything to defaults",
                          command=self.reset_defaults)
        bar.add_cascade(label="Preferences", menu=prefs)

        designer = tk.Menu(bar, tearoff=0)
        designer.add_command(label="Article styles\u2026", command=self.open_styles)
        designer.add_command(label="Copy the article stylesheet\u2026",
                             command=self.show_stylesheet)
        designer.add_separator()
        designer.add_command(label="Place the pictures\u2026", command=self.place_pictures)
        designer.add_command(label="Build an article card\u2026", command=self.build_card)
        bar.add_cascade(label="Designer", menu=designer)

        helpmenu = tk.Menu(bar, tearoff=0)
        for label, filename in core.DOCUMENTS:
            helpmenu.add_command(label=label,
                                 command=lambda f=filename, l=label: self.open_guide(f, l))
        helpmenu.add_separator()
        helpmenu.add_command(label="Check for updates", command=self.check_updates)
        helpmenu.add_command(label="About", command=self.about)
        bar.add_cascade(label="Help", menu=helpmenu)

        self.root.config(menu=bar)

    def open_preferences(self):
        Preferences(self.root, self.opts, self.preferences_saved)

    def preferences_saved(self):
        self.opts = core.options()
        self.say("")
        self.say("Preferences saved.")
        self.describe_settings()

    def describe_settings(self):
        changed = core.non_default(self.opts)
        if changed:
            for item in changed:
                self.say(f"    {item}")
        else:
            self.say("    everything at its default")

    def reset_defaults(self):
        if not messagebox.askyesno(
                "Reset everything",
                "Put every setting back to the way it comes out of the box?\n\n"
                "The house template is remembered separately and is not affected."):
            return
        data = core.load_settings()
        template = data.get("template")
        core.save_settings({"template": template} if template else {})
        self.opts = core.options()
        self.auto_check.set(self.opts.get("check_at_startup", True))
        self.say("")
        self.say("Everything reset to defaults.")

    def open_styles(self):
        StylePanel(self.root, self.styles_saved)

    def styles_saved(self):
        self.opts = core.options()
        self.say("")
        self.say("Article styles saved. Copy the stylesheet into Custom CSS "
                 "for the change to reach the site.")

    def show_stylesheet(self):
        """The stylesheet to paste into Squarespace's Custom CSS."""
        css = core.article_css(self.opts, wrap=False)
        note = (f"Paste this into Design \u203a Custom CSS on the site.\n"
                f"Generated by version {core.VERSION}.\n"
                f"Anything you write outside the BEGIN and END lines is yours "
                f"and survives a fresh paste.\n\n")
        CopyWindow(self.root, "Article stylesheet", note + css)

    def place_pictures(self):
        """Put uploaded pictures into a converted article."""
        start = str(self.last_output) if self.last_output else ""
        chosen = filedialog.askopenfilename(
            title="Choose the converted article (.txt)",
            initialfile=pathlib.Path(start).name if start else "",
            initialdir=str(pathlib.Path(start).parent) if start else "",
            filetypes=[("Converted article", "*.txt *.html"), ("All files", "*.*")])
        if not chosen:
            return
        text = pathlib.Path(chosen).read_text(encoding="utf-8", errors="replace")
        waiting = core.pictures_awaiting(text)
        if not waiting:
            messagebox.showinfo(
                "Nothing waiting",
                "That article has no picture markers in it. Either it has no "
                "pictures, or they have already been placed.")
            return
        PicturePlacer(self.root, pathlib.Path(chosen), text, waiting, self.say)

    def build_card(self):
        """A link card for an article, to paste onto a profile page."""
        CardBuilder(self.root, self.say)

    def open_guide(self, filename, label):
        path = core.document_path(filename)
        if path is None:
            messagebox.showinfo(
                "Not included",
                "That document did not come with this copy of the app. "
                f"It is in the repository: {core.RELEASES_PAGE}")
            return
        GuideWindow(self.root, label,
                    path.read_text(encoding="utf-8", errors="replace"))

    def about(self):
        messagebox.showinfo(
            "CBM Article Converter",
            f"Version {core.VERSION}\n\n"
            "Turns a finished article into HTML for a Squarespace Code Block.\n\n"
            f"{core.RELEASES_PAGE}")

    def save_auto_check(self):
        data = core.load_settings()
        data["check_at_startup"] = bool(self.auto_check.get())
        core.save_settings(data)
        self.opts = core.options()

    # ------------------------------------------------------------------ ui --
    def say(self, text):
        self.root.after(0, self._say, text)

    def _say(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def show_template(self):
        if self.template:
            self.template_label.config(text=f"House template: {self.template.name}",
                                       fg="#333")
        else:
            self.template_label.config(text="House template: none chosen yet", fg="#999")

    def pick_template(self):
        path = filedialog.askopenfilename(
            title="Choose the house template",
            filetypes=[("Word templates", "*.dotx *.docx"), ("All files", "*.*")])
        if not path:
            return None
        self.template = pathlib.Path(path)
        core.remember_template(self.template)
        self.show_template()
        self.say(f"House template set to {self.template.name}. It will be remembered.")
        return self.template

    def accept(self, paths):
        self.paths = [pathlib.Path(p) for p in paths]
        self.chosen.config(
            text=self.paths[0].name if len(self.paths) == 1
            else f"{len(self.paths)} files chosen", fg="#000")
        self.convert_btn.config(state="normal")

    def choose(self):
        paths = filedialog.askopenfilenames(
            title="Choose one or more articles",
            filetypes=[("Articles", "*.docx *.html *.htm"),
                       ("Word documents", "*.docx"),
                       ("InDesign exports", "*.html *.htm"),
                       ("All files", "*.*")])
        if paths:
            self.accept(paths)

    # --------------------------------------------------------- house styles --
    def resolve_template(self):
        if self.template:
            choice = TemplateChoice(self.root, self.template).result
            if choice is None:
                return None
            if choice == "use":
                return self.template
        return self.pick_template()

    def add_styles(self):
        """Put the house styles into whichever Word documents are chosen."""
        if not self.paths:
            messagebox.showinfo(
                "Nothing chosen",
                "Choose an article first. Styles are applied to the Word "
                "documents among whatever is selected.")
            return
        word = [p for p in self.paths if p.suffix.lower() == ".docx"]
        other = [p for p in self.paths if p.suffix.lower() != ".docx"]
        if not word:
            messagebox.showwarning(
                "No Word documents",
                "Styles can only be applied to .docx files. Nothing chosen is "
                "one, so nothing has been done.")
            return
        if other:
            messagebox.showwarning(
                "Skipping some files",
                f"{len(other)} of the chosen files are not Word documents and "
                "will be skipped:\n\n"
                + "\n".join("  " + p.name for p in other[:6])
                + ("\n  …" if len(other) > 6 else ""))
        template = self.resolve_template()      # asked once, for the batch
        if not template:
            self.say("No template chosen; nothing done.")
            return
        for path in word:
            self.say("")
            self.say(f"--- {path.name}")
            try:
                out, added, already = core.add_house_styles(path, template)
            except Exception as exc:                      # noqa: BLE001
                self.say(f"    FAILED  {exc}")
                continue
            for name in already:
                self.say(f"    already there: {name}")
            if not out:
                self.say("    every house style is already in this document;")
                self.say("    no copy was made")
                continue
            for name in added:
                self.say(f"    added: {name}")
            self.say(f"    wrote {pathlib.Path(out).name}")
            self.say("    Open THAT file in Word and apply the styles. When the")
            self.say("    editing is done, choose it here and Convert.")

    # ------------------------------------------------------------- updates --
    def check_updates_quietly(self):
        threading.Thread(target=self._check_updates, args=(True,), daemon=True).start()

    def check_updates(self):
        threading.Thread(target=self._check_updates, daemon=True).start()

    def _check_updates(self, quiet=False):
        try:
            newer = core.check_for_update()
        except core.UpdateError as exc:
            self.say("")
            self.say(f"Update check: {exc}")
            return
        if not newer:
            if quiet:
                self.say(f"Checked for updates: {core.VERSION} is the newest.")
            else:
                self.say("")
                self.say(f"Version {core.VERSION} is the newest there is.")
            return
        self.root.after(0, self.offer_update, newer)

    def offer_update(self, newer):
        notes = newer["notes"]
        if len(notes) > 700:
            notes = notes[:700].rstrip() + "…"
        size = newer.get("asset_size") or 0
        size_text = f"  ({size / 1048576:.1f} MB)" if size else ""
        message = (f"Version {newer['version']} is available. "
                   f"You are running {core.VERSION}.\n\n"
                   + (notes + "\n\n" if notes else "")
                   + (f"Download {newer['asset_name']}{size_text}?\n\n"
                      if newer.get("asset_url") else
                      "That release has no download for this kind of machine.\n\n")
                   + "It is saved alongside this one rather than replacing it, "
                     "so you can go back if you need to. The folder this app is "
                     "in is offered first; anywhere else is fine.")
        if not newer.get("asset_url"):
            messagebox.showinfo("A newer version exists", message)
            self.say(f"Version {newer['version']} is available: {newer['page']}")
            return
        if not messagebox.askyesno("A newer version is available", message):
            self.say(f"Update declined. It remains at {newer['page']}")
            return
        folder = filedialog.askdirectory(
            title="Where should it be saved?",
            initialdir=str(core.app_folder()))
        if not folder:
            return
        self.say("")
        self.say(f"Downloading {newer['asset_name']}…")
        threading.Thread(target=self._download, args=(newer, folder),
                         daemon=True).start()

    def _download(self, newer, folder):
        try:
            saved = core.download_update(newer["asset_url"], folder,
                                         newer["asset_name"])
        except core.UpdateError as exc:
            self.say(f"    {exc}")
            return
        self.say(f"    saved to {saved}")
        self.say("    Close this window and open the new version.")
        self.root.after(0, self.offer_shortcut, saved)

    def offer_shortcut(self, target):
        """After a download, offer to point the Desktop shortcut at it."""
        target = pathlib.Path(target)
        if target.suffix.lower() == ".zip":
            self.say("    Expand the zip, then use Preferences \u203a Desktop "
                     "shortcut to point at the app.")
            return
        # Only offered when a shortcut to an older version is already there.
        # Someone who does not use shortcuts is never asked; one can still be
        # made deliberately from Preferences > Desktop shortcut.
        old = core.existing_shortcuts()
        if not old:
            return
        question = (f"Replace the Desktop shortcut with one to "
                    f"{target.name}?\n\nThese would be removed:\n"
                    + "\n".join("  " + o.name for o in old))
        if not messagebox.askyesno("Desktop shortcut", question):
            return
        self.make_shortcut(target, old)

    def make_shortcut(self, target, old=()):
        try:
            link = core.make_shortcut(target, replace=old)
        except core.ShortcutError as exc:
            self.say(f"    Shortcut not made: {exc}")
            return
        self.say(f"    Desktop shortcut now points at {pathlib.Path(target).name}")
        for item in old:
            self.say(f"    removed the old shortcut {item.name}")
        return link

    def desktop_shortcut(self):
        """Point the Desktop shortcut at a chosen copy of the app."""
        if sys.platform == "darwin":
            chosen = filedialog.askdirectory(
                title="Choose the app (the .app bundle)")
        else:
            chosen = filedialog.askopenfilename(
                title="Choose the app",
                filetypes=[("Application", "*.exe"), ("All files", "*.*")])
        if not chosen:
            return
        old = [o for o in core.existing_shortcuts()]
        if old and not messagebox.askyesno(
                "Desktop shortcut",
                "Replace the shortcut already on the Desktop?\n\n"
                + "\n".join("  " + o.name for o in old)):
            old = []
        self.say("")
        self.make_shortcut(chosen, old)

    # ------------------------------------------------------------- working --
    def start(self):
        if not self.paths:
            return
        self.choose_btn.config(state="disabled")
        self.convert_btn.config(state="disabled", text="Working…")
        threading.Thread(target=self.run, daemon=True).start()

    def ask_orphans(self, texts):
        answer = {}
        done = threading.Event()

        def ask():
            answer["value"] = self._ask_orphans(texts)
            done.set()

        self.root.after(0, ask)
        done.wait()
        return answer.get("value", False)

    def _ask_orphans(self, texts):
        lines = "\n\n".join(f"{i}.  {t}" for i, t in enumerate(texts, 1))
        return messagebox.askyesno(
            "Pull quotes that do not match",
            f"{len(texts)} pull quote(s) match no paragraph in this article:\n\n"
            f"{lines}\n\n"
            "Usually the sentence was tidied when it was copied into the side bar. "
            "Mark additions with [brackets] and cuts with an ellipsis and they will "
            "still match.\n\n"
            "Leave these quotes out and carry on?\n"
            "Choosing No abandons this file and writes nothing.")

    def run(self):
        done = failed = 0
        for path in self.paths:
            self.say("")
            self.say(f"--- {path.name}")
            try:
                html, meta, log = core.convert(
                    path, decide_orphans=lambda t: self.ask_orphans(t),
                    opts=self.opts)
                for line in log:
                    self.say("    " + line)
                if html is None:
                    self.say("    nothing written")
                    failed += 1
                    continue
                out_html, out_txt, pictures = core.write_outputs(
                    path, html, self.opts, meta.get("pictures") or [])
                self.say(f"    wrote {out_html.name}")
                self.say(f"    wrote {out_txt.name}")
                if pictures:
                    self.say(f"    saved {len(pictures)} picture(s) to "
                             f"{pictures[0].parent.name}")
                    self.say("    Upload those, then use Designer \u203a Place "
                             "the pictures to put them into the article.")
                    self.last_output = out_txt
                if out_html.parent != path.parent:
                    self.say(f"    in {out_html.parent}")
                done += 1
            except Exception as exc:                      # noqa: BLE001
                self.say(f"    FAILED  {exc}")
                failed += 1
        self.say("")
        self.say(f"Finished: {done}    Failed or abandoned: {failed}")
        self.say("Open the .html to check the article; copy the code from the .txt.")
        self.root.after(0, self.finished)

    def finished(self):
        self.choose_btn.config(state="normal")
        self.convert_btn.config(state="normal", text="Convert")


def main():
    # Files dropped onto the application arrive as arguments.
    opening = [a for a in sys.argv[1:]
               if pathlib.Path(a).suffix.lower() in (".docx", ".html", ".htm")]
    root = tk.Tk()
    App(root, opening)
    root.mainloop()


if __name__ == "__main__":
    main()
