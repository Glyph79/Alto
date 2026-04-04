import sqlite3
from typing import List

def update_fts_index(conn: sqlite3.Connection, group_id: int, questions: List[str]):
    conn.execute("DELETE FROM questions_fts WHERE group_id = ?", (group_id,))
    for question in questions:
        conn.execute("INSERT INTO questions_fts(group_id, question) VALUES (?, ?)", (group_id, question))