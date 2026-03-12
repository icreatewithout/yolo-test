"""Simple dashboard for real-time river monitoring stream metadata."""

from __future__ import annotations

import time
from collections import deque
from random import randint

from flask import Flask, jsonify, render_template

app = Flask(__name__)
HISTORY = deque(maxlen=100)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/metrics")
def metrics():
    sample = {
        "timestamp": int(time.time()),
        "dead_fish": randint(0, 8),
        "live_fish": randint(10, 40),
        "floating_object": randint(0, 5),
    }
    HISTORY.append(sample)
    return jsonify({"latest": sample, "history": list(HISTORY)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
