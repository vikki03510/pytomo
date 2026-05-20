from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/dictionary")
def dictionary():
    return render_template("dictionary.html")

@app.route("/improve")
def improve():
    return render_template("improve.html")

@app.route("/contacts")
def contacts():
    return render_template("contacts.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/suggest")
def suggest():
    return render_template("suggest.html")

@app.route("/admin")
def admin():
    return render_template("admin_database.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)