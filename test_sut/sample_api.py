"""
Simple Sample API for Testing the Checklist Processor.
"""

from flask import Flask, jsonify, request
import time
import random

app = Flask(__name__)

# State
items = {}


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "timestamp": time.time()})


@app.route("/items", methods=["POST"])
def create_item():
    data = request.json or {}
    # Validation: require non-empty 'name' field
    if not data.get("name"):
        return jsonify(
            {
                "error": "ValidationError",
                "details": {"name": "Missing required field 'name'"},
            }
        ), 400
    item_id = str(len(items) + 1)
    items[item_id] = {
        "id": item_id,
        "name": data.get("name", f"Item {item_id}"),
        "status": "pending",
        "created_at": time.time(),
    }
    return jsonify(items[item_id]), 201


@app.route("/items", methods=["GET"])
def list_items():
    return jsonify(list(items.values()))


@app.route("/items/<item_id>", methods=["GET"])
def get_item(item_id):
    if item_id not in items:
        return jsonify({"error": "Not found"}), 404
    return jsonify(items[item_id])


@app.route("/items/<item_id>/process", methods=["POST"])
def process_item(item_id):
    if item_id not in items:
        return jsonify({"error": "Not found"}), 404

    # Simulate processing time
    time.sleep(0.5)

    # Simulate random failure (10% chance)
    if random.random() < 0.1:
        return jsonify({"error": "Random processing failure"}), 500

    items[item_id]["status"] = "processed"
    return jsonify(items[item_id])


@app.route("/reset", methods=["POST"])
def reset():
    items.clear()
    return jsonify({"status": "reset"})


if __name__ == "__main__":
    app.run(port=5000)
