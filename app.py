"""
CBM Article Converter
Build 48

A small window: choose an article, convert it, read what happened.
Works on Windows and macOS. Nothing to install beyond the app itself.
"""
import pathlib
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

import core


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
        tk.Label(self, text=template.name, anchor="w", fg="#000").pack(
                 fill="x", padx=18)
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
        x = parent.winfo_rootx() + 40
        y = parent.winfo_rooty() + 60
        self.geometry(f"+{x}+{y}")
        self.wait_window(self)

    def done(self, value):
        self.result = value
        self.destroy()


class GuideChoice(tk.Toplevel):
    """Pick which of the bundled documents to read."""

    def __init__(self, parent, documents, on_choose):
        super().__init__(parent)
        self.title("Which guide?")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        tk.Label(self, text="Open which document?",
                 font=("Helvetica", 12, "bold"), anchor="w").pack(
                 fill="x", padx=18, pady=(18, 10))
        for label, name in documents:
            tk.Button(self, text=label, width=30, anchor="w",
                      command=lambda n=name: self.choose(n, on_choose)).pack(
                      fill="x", padx=18, pady=2)
        tk.Button(self, text="Cancel", width=10,
                  command=self.destroy).pack(pady=(12, 18))
        self.update_idletasks()
        self.geometry(f"+{parent.winfo_rootx() + 60}+{parent.winfo_rooty() + 80}")

    def choose(self, name, on_choose):
        self.destroy()
        on_choose(name)


class App:
    def __init__(self, root):
        self.root = root
        self.paths = []
        self.template = core.remembered_template()
        settings = core.load_settings()
        self.auto_check = tk.BooleanVar(value=settings.get("check_at_startup", True))
        root.title(f"CBM Article Converter  -  {core.VERSION}")
        root.minsize(660, 500)

        tk.Label(root, text="Article to Squarespace HTML",
                 font=("Helvetica", 16, "bold"), anchor="w").pack(
                 fill="x", padx=16, pady=(16, 2))
        tk.Label(root, anchor="w", justify="left", fg="#555",
                 text=("Choose a Word document (.docx) or an InDesign export (.html).\n"
                       "The finished files are written beside the original.")
                 ).pack(fill="x", padx=16)

        row = tk.Frame(root)
        row.pack(fill="x", padx=16, pady=10)
        self.choose_btn = tk.Button(row, text="Choose article…", width=17,
                                    command=self.choose)
        self.choose_btn.pack(side="left")
        self.convert_btn = tk.Button(row, text="Convert", width=12,
                                     state="disabled", command=self.start)
        self.convert_btn.pack(side="left", padx=8)
        self.styles_btn = tk.Button(row, text="Add house styles…", width=18,
                                    command=self.add_styles)
        self.styles_btn.pack(side="right")
        self.update_btn = tk.Button(row, text="Check for updates", width=17,
                                    command=self.check_updates)
        self.update_btn.pack(side="right", padx=8)
        self.guide_btn = tk.Button(row, text="Guide", width=8, command=self.open_guide)
        self.guide_btn.pack(side="right")

        self.chosen = tk.Label(root, text="Nothing chosen yet", anchor="w", fg="#555")
        self.chosen.pack(fill="x", padx=16)

        trow = tk.Frame(root)
        trow.pack(fill="x", padx=16, pady=(8, 0))
        self.template_label = tk.Label(trow, anchor="w", fg="#555")
        self.template_label.pack(side="left", fill="x", expand=True)
        tk.Button(trow, text="Change…", command=self.pick_template).pack(side="right")
        tk.Checkbutton(trow, text="Check for updates at startup",
                       variable=self.auto_check, fg="#555",
                       command=self.save_auto_check).pack(side="right", padx=12)
        self.show_template()

        self.log = scrolledtext.ScrolledText(root, height=16, wrap="word",
                                             state="disabled", font="TkFixedFont")
        self.log.pack(fill="both", expand=True, padx=16, pady=(10, 16))

        self.say(f"Version {core.VERSION}. Ready.")
        if self.auto_check.get():
            # A moment after the window is up, so it never delays opening.
            self.root.after(800, self.check_updates_quietly)
        if core.running_from_temp():
            messagebox.showwarning(
                "Unzip the folder first",
                "This is running from inside a zip file, which does not work.\n\n"
                "Extract the whole folder somewhere ordinary, such as your "
                "Desktop, then run it from there.")

    # ------------------------------------------------------------------ ui --
    def say(self, text):
        """
        Add a line to the report. Safe to call from the worker thread: Tk must
        only be touched from the thread that owns the window, so the work is
        handed back with after(). Windows tends to forgive this; macOS does
        not, and a dialog raised from the wrong thread can hang the app.
        """
        self.root.after(0, self._say, text)

    def _say(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def open_guide(self):
        """Open one of the documents that came with the app."""
        available = [(label, name) for label, name in core.DOCUMENTS
                     if core.document_path(name)]
        if not available:
            messagebox.showinfo(
                "No guides here",
                "The documents did not come with this copy of the app. They are "
                f"in the repository: {core.RELEASES_PAGE}")
            return
        if len(available) == 1:
            self._open_doc(available[0][1])
            return
        GuideChoice(self.root, available, self._open_doc)

    def _open_doc(self, filename):
        try:
            opened = core.open_document(filename)
        except Exception as exc:                          # noqa: BLE001
            self.say(f"Could not open {filename}: {exc}")
            return
        self.say(f"Opened {opened.name}")

    def save_auto_check(self):
        data = core.load_settings()
        data["check_at_startup"] = bool(self.auto_check.get())
        core.save_settings(data)

    def show_template(self):
        if self.template:
            self.template_label.config(text=f"House template: {self.template.name}", fg="#333")
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

    def choose(self):
        paths = filedialog.askopenfilenames(
            title="Choose one or more articles",
            filetypes=[("Articles", "*.docx *.html *.htm"),
                       ("Word documents", "*.docx"),
                       ("InDesign exports", "*.html *.htm"),
                       ("All files", "*.*")])
        if not paths:
            return
        self.paths = [pathlib.Path(p) for p in paths]
        self.chosen.config(
            text=self.paths[0].name if len(self.paths) == 1
            else f"{len(self.paths)} files chosen", fg="#000")
        self.convert_btn.config(state="normal")

    # --------------------------------------------------------- house styles --
    def resolve_template(self):
        """Confirm the remembered template, or pick a different one."""
        if self.template:
            choice = TemplateChoice(self.root, self.template).result
            if choice is None:
                return None
            if choice == "use":
                return self.template
        return self.pick_template()

    def add_styles(self):
        manuscript = filedialog.askopenfilename(
            title="Choose the author's Word document",
            filetypes=[("Word documents", "*.docx")])
        if not manuscript:
            return
        template = self.resolve_template()
        if not template:
            self.say("No template chosen; nothing done.")
            return
        self.say("")
        self.say(f"--- {pathlib.Path(manuscript).name}")
        self.say(f"    template: {template.name}")
        try:
            out, added, already = core.add_house_styles(manuscript, template)
        except Exception as exc:                          # noqa: BLE001
            self.say(f"    FAILED  {exc}")
            return
        for name in already:
            self.say(f"    already there: {name}")
        if not out:
            self.say("    nothing to add; the document already has them")
            return
        for name in added:
            self.say(f"    added: {name}")
        self.say(f"    wrote {pathlib.Path(out).name}")
        self.say("    Only the style list changed. The text, comments and")
        self.say("    tracked changes are exactly as the author sent them.")

    # ------------------------------------------------------------- updates --
    def check_updates_quietly(self):
        """
        The check that runs by itself at startup. It speaks up only when
        there is something newer: a failure is noted in the report and
        nothing else, because an article can be converted perfectly well
        with no internet at all.
        """
        threading.Thread(target=self._check_updates, args=(True,),
                         daemon=True).start()

    def check_updates(self):
        self.update_btn.config(state="disabled", text="Checking…")
        threading.Thread(target=self._check_updates, daemon=True).start()

    def _check_updates(self, quiet=False):
        try:
            newer = core.check_for_update()
        except core.UpdateError as exc:
            self.say("")
            self.say(f"Update check: {exc}")
            if not quiet:
                self.root.after(0, self.update_done)
            return
        if not newer:
            if quiet:
                self.say(f"Checked for updates: {core.VERSION} is the newest.")
            else:
                self.say("")
                self.say(f"Version {core.VERSION} is the newest there is.")
                self.root.after(0, self.update_done)
            return
        self.root.after(0, self.offer_update, newer)

    def offer_update(self, newer):
        self.update_done()
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
                      "No download is attached to that release.\n\n")
                   + "The new version is saved alongside this one rather than "
                     "replacing it, so you can go back if you need to.")
        if not newer.get("asset_url"):
            messagebox.showinfo("A newer version exists", message)
            self.say(f"Version {newer['version']} is available: {newer['page']}")
            return
        if not messagebox.askyesno("A newer version is available", message):
            self.say(f"Update declined. It remains at {newer['page']}")
            return
        folder = filedialog.askdirectory(title="Where should it be saved?")
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

    def update_done(self):
        self.update_btn.config(state="normal", text="Check for updates")

    # ------------------------------------------------------------- working --
    def start(self):
        self.choose_btn.config(state="disabled")
        self.convert_btn.config(state="disabled", text="Working…")
        threading.Thread(target=self.run, daemon=True).start()

    def ask_orphans(self, texts):
        """Called from the worker thread; asks the main thread and waits."""
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
                    path, decide_orphans=lambda t: self.ask_orphans(t))
                for line in log:
                    self.say("    " + line)
                if html is None:
                    self.say("    nothing written")
                    failed += 1
                    continue
                out_html, out_txt = core.write_outputs(path, html)
                self.say(f"    wrote {out_html.name}")
                self.say(f"    wrote {out_txt.name}")
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
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
