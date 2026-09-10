"""
image_export.py
Query result ko image me convert karne ka module.
Do formats support karta hai:
  - "table" : multiple documents, rows/columns wali table image
  - "card"  : ek single document, bada highlighted card

Dono functions PNG bytes return karte hain (image_bytes) —
isse file me save bhi kar sakte ho aur seedha Matrix pe bhi
bhej sakte ho, bina disk pe likhe.
"""

import io
import textwrap
from typing import Any

import matplotlib
matplotlib.use("Agg")  # server pe chalane ke liye (no display needed)
import matplotlib.pyplot as plt


def _fig_to_bytes(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _format_value(value, wrap_width: int = 22) -> str:
    """
    MongoDB se aane wale raw values (ObjectId, date, list, dict) ko
    readable, image-friendly text me convert karta hai. Lambe text
    ko wrap bhi karta hai taaki table cells overlap na hon.
    """
    if isinstance(value, dict):
        if "$oid" in value:
            text = value["$oid"]
        elif "$date" in value:
            text = str(value["$date"]).split("T")[0]
        else:
            text = str(value)
    elif isinstance(value, list):
        text = ", ".join(str(v) for v in value)
    elif value is None:
        text = ""
    else:
        text = str(value)

    if len(text) > wrap_width:
        text = "\n".join(textwrap.wrap(text, width=wrap_width))
    return text


def generate_table_image(data, columns, title: str = "") -> bytes:
    """
    Multiple documents ko ek clean table image me convert karta hai.
    data    : list of dicts (query result)
    columns : kaunse columns dikhane hain, order me
    title   : image ka heading
    """
    if not data:
        raise ValueError("Table image ke liye data khaali nahi ho sakta")

    rows = [[_format_value(doc.get(col, "")) for col in columns] for doc in data]

    max_lines_per_row = [max(cell.count("\n") + 1 for cell in row) for row in rows] or [1]
    total_height = sum(0.35 * lines + 0.25 for lines in max_lines_per_row) + 1.3

    fig, ax = plt.subplots(figsize=(max(len(columns) * 2.0, 6), total_height))
    ax.axis("off")
    if title:
        ax.set_title(title, fontsize=14, fontweight="bold", pad=20)

    table = ax.table(cellText=rows, colLabels=columns, cellLoc="center", loc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(9.5)
    table.auto_set_column_width(col=list(range(len(columns))))

    for row_idx, lines in enumerate(max_lines_per_row, start=1):
        for col_idx in range(len(columns)):
            table[row_idx, col_idx].set_height(0.09 * lines + 0.05)

    for col_idx in range(len(columns)):
        header_cell = table[0, col_idx]
        header_cell.set_facecolor("#2c3e50")
        header_cell.set_text_props(color="white", fontweight="bold")

    for row_idx in range(1, len(rows) + 1):
        color = "#f2f2f2" if row_idx % 2 == 0 else "white"
        for col_idx in range(len(columns)):
            table[row_idx, col_idx].set_facecolor(color)

    plt.tight_layout()
    return _fig_to_bytes(fig)


def generate_card_image(document, title: str = "") -> bytes:
    """
    Ek single document ko bade, highlighted "card" style image
    me dikhata hai — jab sirf ek record ka focus chahiye ho.
    """
    if not document:
        raise ValueError("Card image ke liye document khaali nahi ho sakta")

    fields = [(k, _format_value(v, wrap_width=40)) for k, v in document.items()]
    fig_height = 0.9 + sum((v.count("\n") + 1) * 0.45 + 0.15 for _, v in fields)
    fig, ax = plt.subplots(figsize=(6.5, fig_height))
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    ax.add_patch(plt.Rectangle((0, 0), 1, 1, facecolor="#ffffff", edgecolor="#2c3e50", linewidth=2))
    header_h = 0.9 / (len(fields) + 1.6)
    ax.add_patch(plt.Rectangle((0, 1 - header_h), 1, header_h, facecolor="#2c3e50"))
    ax.text(0.05, 1 - header_h / 2, title or "Record", fontsize=15, fontweight="bold",
            color="white", va="center", ha="left")

    row_h = (1 - header_h) / max(len(fields), 1)
    for i, (key, value) in enumerate(fields):
        y = 1 - header_h - (i + 0.5) * row_h
        ax.text(0.05, y, str(key), fontsize=10.5, color="#8b98a5", va="center", ha="left")
        ax.text(0.95, y, value, fontsize=11, color="#1a1a1a", va="center", ha="right", fontweight="medium")
        if i < len(fields) - 1:
            ax.axhline(y - row_h / 2, xmin=0.03, xmax=0.97, color="#eeeeee", linewidth=1)

    return _fig_to_bytes(fig)

