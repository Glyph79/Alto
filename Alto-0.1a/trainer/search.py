#!/usr/bin/env python3
"""
GUI Search for model database.
Fully configurable fuzzy matching:
- Word match scorer & threshold
- Question scorer & threshold
Compatible with optimized schema (words table + word_index with word_id).
"""

import os
import re
import sqlite3
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import msgpack
from fuzzywuzzy import fuzz, process

# ----------------------------------------------------------------------
#  Search backend (fully configurable)
# ----------------------------------------------------------------------
def normalize_word(word: str) -> str:
    return re.sub(r'[^\w\s]', '', word.lower())

def search_model(db_path: str, query: str,
                 score_threshold: int = 60,
                 word_threshold: int = 70,
                 limit: int = 10,
                 word_scorer=fuzz.ratio,      # scorer for word matching
                 question_scorer=fuzz.WRatio): # scorer for final scoring
    """
    Search the database.
    - score_threshold : minimum fuzzy score for a question to be included.
    - word_threshold  : minimum fuzzy score for a word to be considered similar.
    - word_scorer     : fuzzy function for comparing words (e.g., fuzz.ratio, fuzz.WRatio).
    - question_scorer : fuzzy function for comparing full questions.
    """
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"Database file not found: {db_path}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON")

    query_words = [normalize_word(w) for w in query.split() if normalize_word(w)]
    if not query_words:
        return []

    # 1. Get all distinct words from the words table
    cursor = conn.execute("SELECT word FROM words")
    all_words = [row[0] for row in cursor.fetchall()]

    # 2. Find words similar to each query word using the chosen word_scorer
    similar_words = set()
    for qw in query_words:
        if len(qw) < 3:
            continue
        matches = process.extract(qw, all_words, limit=10, scorer=word_scorer)
        for word, score in matches:
            if score >= word_threshold:
                similar_words.add(word)

    # Also include exact matches (in case they are below the threshold)
    similar_words.update(qw for qw in query_words if qw in all_words)

    if not similar_words:
        return []

    # 3. Get group IDs that contain any of those words.
    placeholders = ','.join('?' * len(similar_words))
    cursor = conn.execute(f"""
        SELECT DISTINCT wi.group_id
        FROM word_index wi
        JOIN words w ON wi.word_id = w.id
        WHERE w.word IN ({placeholders})
    """, list(similar_words))
    candidate_ids = [row[0] for row in cursor.fetchall()]

    if not candidate_ids:
        return []

    # 4. Load groups and score questions using the chosen question_scorer
    placeholders = ','.join('?' * len(candidate_ids))
    cursor = conn.execute(f"""
        SELECT id, data FROM groups
        WHERE id IN ({placeholders})
    """, candidate_ids)

    results = []
    for row in cursor:
        group_id, blob = row
        group = msgpack.unpackb(blob, raw=False)
        questions = group.get("questions", [])
        for q_idx, question in enumerate(questions):
            score = question_scorer(query.lower(), question.lower())
            if score >= score_threshold:
                results.append((group_id, q_idx, question, score))

    results.sort(key=lambda x: x[3], reverse=True)
    return results[:limit]


# ----------------------------------------------------------------------
#  GUI Application (both scorers configurable)
# ----------------------------------------------------------------------
class SearchApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Model Search")
        self.root.geometry("1050x700")  # Slightly wider for extra dropdowns

        self.db_path = tk.StringVar()
        self.query = tk.StringVar()
        self.score_threshold = tk.IntVar(value=60)
        self.word_threshold = tk.IntVar(value=70)
        self.limit = tk.IntVar(value=10)
        
        # Scorer choices
        self.question_scorer_choice = tk.StringVar(value="Weighted (WRatio)")
        self.word_scorer_choice = tk.StringVar(value="Strict (ratio)")
        
        self.status = tk.StringVar(value="Ready")
        self.queue = queue.Queue()

        # Mapping from displayed names to fuzzy functions
        self.scorers = {
            "Strict (ratio)": fuzz.ratio,
            "Weighted (WRatio)": fuzz.WRatio,
            "Token Set": fuzz.token_set_ratio,
            "Partial": fuzz.partial_ratio,
            "Token Sort": fuzz.token_sort_ratio  # extra option
        }

        self.create_widgets()
        self.populate_model_list()
        self.poll_queue()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Model selection
        model_frame = ttk.LabelFrame(main_frame, text="Model", padding="5")
        model_frame.pack(fill=tk.X, pady=5)

        ttk.Label(model_frame, text="Select model:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.model_combo = ttk.Combobox(model_frame, state="readonly", width=40)
        self.model_combo.grid(row=0, column=1, padx=5, sticky=tk.W)
        self.model_combo.bind("<<ComboboxSelected>>", self.on_model_selected)
        ttk.Button(model_frame, text="Browse...", command=self.browse_db).grid(row=0, column=2, padx=5)
        ttk.Label(model_frame, text="or").grid(row=0, column=3, padx=5)
        self.db_path_label = ttk.Label(model_frame, text="", foreground="blue")
        self.db_path_label.grid(row=0, column=4, padx=5, sticky=tk.W)

        # Search inputs
        search_frame = ttk.LabelFrame(main_frame, text="Search", padding="5")
        search_frame.pack(fill=tk.X, pady=5)

        # Query row
        ttk.Label(search_frame, text="Query:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(search_frame, textvariable=self.query, width=70).grid(row=0, column=1, columnspan=8, padx=5, sticky=tk.W)

        # Row 1: thresholds and limit
        ttk.Label(search_frame, text="Score threshold (%):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Spinbox(search_frame, from_=0, to=100, textvariable=self.score_threshold, width=5).grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)

        ttk.Label(search_frame, text="Word match threshold (%):").grid(row=1, column=2, sticky=tk.W, padx=(20,5), pady=5)
        ttk.Spinbox(search_frame, from_=0, to=100, textvariable=self.word_threshold, width=5).grid(row=1, column=3, sticky=tk.W, padx=5, pady=5)

        ttk.Label(search_frame, text="Limit:").grid(row=1, column=4, sticky=tk.W, padx=(20,5), pady=5)
        ttk.Spinbox(search_frame, from_=1, to=100, textvariable=self.limit, width=5).grid(row=1, column=5, sticky=tk.W, padx=5, pady=5)

        # Row 2: scorer choices
        ttk.Label(search_frame, text="Question scorer:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        q_scorer_combo = ttk.Combobox(search_frame, textvariable=self.question_scorer_choice,
                                      values=list(self.scorers.keys()), state="readonly", width=18)
        q_scorer_combo.grid(row=2, column=1, padx=5, pady=5, sticky=tk.W)

        ttk.Label(search_frame, text="Word scorer:").grid(row=2, column=2, sticky=tk.W, padx=(20,5), pady=5)
        w_scorer_combo = ttk.Combobox(search_frame, textvariable=self.word_scorer_choice,
                                      values=list(self.scorers.keys()), state="readonly", width=18)
        w_scorer_combo.grid(row=2, column=3, padx=5, pady=5, sticky=tk.W)

        # Search button
        ttk.Button(search_frame, text="Search", command=self.start_search).grid(row=2, column=4, columnspan=2, padx=20, pady=5)

        # Results tree
        tree_frame = ttk.LabelFrame(main_frame, text="Results", padding="5")
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        columns = ("score", "question", "group_id", "q_idx")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=15)
        self.tree.heading("score", text="Score")
        self.tree.heading("question", text="Question")
        self.tree.heading("group_id", text="Group ID")
        self.tree.heading("q_idx", text="Q Index")
        self.tree.column("score", width=60, anchor=tk.CENTER)
        self.tree.column("question", width=750)
        self.tree.column("group_id", width=80, anchor=tk.CENTER)
        self.tree.column("q_idx", width=60, anchor=tk.CENTER)

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky=tk.NSEW)
        vsb.grid(row=0, column=1, sticky=tk.NS)
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # Status bar
        status_bar = ttk.Frame(main_frame, relief=tk.SUNKEN, padding="2")
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, pady=(5,0))
        ttk.Label(status_bar, textvariable=self.status).pack(side=tk.LEFT)

    def populate_model_list(self):
        models_dir = "models"
        if not os.path.isdir(models_dir):
            self.model_combo['values'] = []
            return
        model_names = []
        for entry in os.listdir(models_dir):
            full_path = os.path.join(models_dir, entry)
            if os.path.isdir(full_path):
                db_files = [f for f in os.listdir(full_path) if f.endswith('.db')]
                if db_files:
                    model_names.append(entry)
        self.model_combo['values'] = sorted(model_names)

    def on_model_selected(self, event=None):
        model_name = self.model_combo.get()
        if not model_name:
            return
        safe_name = model_name.replace('/', '_').replace('\\', '_').replace(':', '_')
        db_candidate = os.path.join("models", safe_name, f"{model_name}.db")
        if os.path.isfile(db_candidate):
            self.db_path.set(db_candidate)
            self.db_path_label.config(text=os.path.basename(db_candidate))
        else:
            folder = os.path.join("models", safe_name)
            if os.path.isdir(folder):
                dbs = [f for f in os.listdir(folder) if f.endswith('.db')]
                if dbs:
                    self.db_path.set(os.path.join(folder, dbs[0]))
                    self.db_path_label.config(text=dbs[0])
                else:
                    self.db_path.set("")
                    self.db_path_label.config(text="No .db file found")
            else:
                self.db_path.set("")
                self.db_path_label.config(text="Folder missing")

    def browse_db(self):
        filename = filedialog.askopenfilename(
            title="Select model database",
            filetypes=[("SQLite DB", "*.db"), ("All files", "*.*")]
        )
        if filename:
            self.db_path.set(filename)
            self.db_path_label.config(text=os.path.basename(filename))
            self.model_combo.set('')

    def start_search(self):
        db = self.db_path.get().strip()
        if not db:
            messagebox.showerror("Error", "No database selected.")
            return
        if not os.path.isfile(db):
            messagebox.showerror("Error", f"Database file not found:\n{db}")
            return
        query_text = self.query.get().strip()
        if not query_text:
            messagebox.showerror("Error", "Please enter a search query.")
            return

        # Get selected scorer functions
        question_scorer_name = self.question_scorer_choice.get()
        question_scorer = self.scorers.get(question_scorer_name, fuzz.WRatio)
        
        word_scorer_name = self.word_scorer_choice.get()
        word_scorer = self.scorers.get(word_scorer_name, fuzz.ratio)

        for row in self.tree.get_children():
            self.tree.delete(row)

        self.status.set("Searching...")
        self.root.update_idletasks()

        thread = threading.Thread(
            target=self.search_thread,
            args=(db, query_text,
                  self.score_threshold.get(),
                  self.word_threshold.get(),
                  self.limit.get(),
                  word_scorer,
                  question_scorer),
            daemon=True
        )
        thread.start()

    def search_thread(self, db_path, query, score_thresh, word_thresh, limit,
                      word_scorer, question_scorer):
        try:
            results = search_model(db_path, query, score_thresh, word_thresh,
                                   limit, word_scorer, question_scorer)
            self.queue.put(("success", results))
        except Exception as e:
            self.queue.put(("error", str(e)))

    def poll_queue(self):
        try:
            msg = self.queue.get_nowait()
            if msg[0] == "success":
                results = msg[1]
                self.display_results(results)
                self.status.set(f"Found {len(results)} match(es).")
            elif msg[0] == "error":
                messagebox.showerror("Search Error", msg[1])
                self.status.set("Error during search.")
        except queue.Empty:
            pass
        self.root.after(100, self.poll_queue)

    def display_results(self, results):
        for group_id, q_idx, question, score in results:
            self.tree.insert("", tk.END, values=(f"{score}%", question, group_id, q_idx))


def main():
    root = tk.Tk()
    app = SearchApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
