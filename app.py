"""
GoodWe 8kW Battery Discount Dashboard – Flask backend
"""

from flask import Flask, jsonify, render_template, request
from scraper import fetch_listings

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/listings")
def api_listings():
    min_discount = float(request.args.get("min_discount", 40))
    include_oos = request.args.get("include_out_of_stock", "true").lower() == "true"
    data = fetch_listings(min_discount=min_discount, include_out_of_stock=include_oos)
    return jsonify(data)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
