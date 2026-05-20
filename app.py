from datetime import datetime

import mysql.connector
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = "532407163467524682538073071135"

db_config = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "slutprojekt",
}


def get_db_connection():
    return mysql.connector.connect(**db_config)


def fetch_one(sql, params=None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql, params or ())
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row


def fetch_all(sql, params=None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql, params or ())
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


def execute(sql, params=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, params or ())
    conn.commit()
    last_id = cursor.lastrowid
    cursor.close()
    conn.close()
    return last_id


@app.template_filter("datum")
def format_datum(value):
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y, %H:%M:%S")
    return value


def get_all_topics():
    return fetch_all(
        """
        SELECT t.id, t.title, t.content, t.created_at,
               u.username AS author_username,
               (SELECT COUNT(*) FROM posts p WHERE p.topic_id = t.id) AS post_count
        FROM topics t
        JOIN users u ON t.user_id = u.id
        ORDER BY t.created_at DESC
        """
    )


def get_topic_with_posts(topic_id):
    topic = fetch_one(
        """
        SELECT t.id, t.title, t.content, t.created_at, t.user_id,
               u.username AS author_username
        FROM topics t JOIN users u ON t.user_id = u.id
        WHERE t.id = %s
        """,
        (topic_id,),
    )
    if topic is None:
        return None, None
    posts = fetch_all(
        """
        SELECT p.id, p.content, p.created_at, p.user_id,
               u.username AS author_username
        FROM posts p JOIN users u ON p.user_id = u.id
        WHERE p.topic_id = %s ORDER BY p.created_at ASC
        """,
        (topic_id,),
    )
    return topic, posts


@app.route("/")
def page_index():
    return render_template("forum.html", topics=get_all_topics())


@app.route("/forum")
def page_forum_redirect():
    return redirect(url_for("page_index"))


@app.route("/login", methods=["GET", "POST"])
def page_login():
    if "user_id" in session:
        if "next" in request.args:
            return redirect(request.args["next"])
        return redirect(url_for("page_index"))

    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        next_url = request.form["next"]

        if not username or not password:
            flash("Ange användarnamn och lösenord", "error")
            return render_template("login.html", next_url=next_url)

        user = fetch_one(
            "SELECT id, username, password, role FROM users WHERE username = %s",
            (username,),
        )
        if user is None or not check_password_hash(user["password"], password):
            flash("Fel användarnamn eller lösenord", "error")
            return render_template("login.html", next_url=next_url)

        session.clear()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user["role"]
        return redirect(next_url)

    if "next" in request.args:
        next_url = request.args["next"]
    else:
        next_url = url_for("page_index")
    return render_template("login.html", next_url=next_url)


@app.route("/register", methods=["GET", "POST"])
def page_register():
    if "user_id" in session:
        return redirect(url_for("page_index"))

    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        if not username or len(username) < 3:
            flash("Användarnamn minst 3 tecken", "error")
            return render_template("register.html")
        if not password or len(password) < 6:
            flash("Lösenord minst 6 tecken", "error")
            return render_template("register.html")
        if fetch_one("SELECT id FROM users WHERE username = %s", (username,)):
            flash("Användarnamnet är upptaget", "error")
            return render_template("register.html")

        hashed = generate_password_hash(password)
        execute(
            "INSERT INTO users (username, password, role) VALUES (%s, %s, 'user')",
            (username, hashed),
        )
        flash("Konto skapat. Logga in", "success")
        return redirect(url_for("page_login"))

    return render_template("register.html")


@app.route("/logout")
def page_logout():
    session.clear()
    return redirect(url_for("page_index"))


@app.route("/topic/<int:topic_id>", methods=["GET", "POST"])
def page_topic(topic_id):
    topic, posts = get_topic_with_posts(topic_id)
    if topic is None:
        flash("Ämnet hittades inte", "error")
        return redirect(url_for("page_index"))

    if request.method == "POST":
        if "user_id" not in session:
            return redirect(url_for("page_login", next=request.path))

        content = request.form["content"].strip()
        if not content:
            flash("Skriv ett svar", "error")
        else:
            execute(
                "INSERT INTO posts (content, topic_id, user_id) VALUES (%s, %s, %s)",
                (content, topic_id, session["user_id"]),
            )
            flash("Svar publicerat", "success")
        return redirect(url_for("page_topic", topic_id=topic_id))

    return render_template("topic.html", topic=topic, posts=posts)


@app.route("/post/<int:post_id>/delete", methods=["POST"])
def delete_post(post_id):
    if "user_id" not in session:
        return redirect(url_for("page_login", next=request.path))
    execute("DELETE FROM posts WHERE id = %s", (post_id,))
    flash("Inlägg borttaget", "success")
    return redirect(url_for("page_index"))


@app.route("/create-topic", methods=["GET", "POST"])
def page_create_topic():
    if "user_id" not in session:
        return redirect(url_for("page_login", next=request.path))

    if request.method == "POST":
        title = request.form["title"].strip()
        content = request.form["content"].strip()
        if not title or not content:
            flash("Titel och innehåll krävs", "error")
            return render_template("create_topic.html")

        topic_id = execute(
            "INSERT INTO topics (title, content, user_id) VALUES (%s, %s, %s)",
            (title, content, session["user_id"]),
        )
        flash("Ämne skapat", "success")
        return redirect(url_for("page_topic", topic_id=topic_id))

    return render_template("create_topic.html")


@app.route("/topic/<int:topic_id>/delete", methods=["POST"])
def delete_topic(topic_id):
    if "user_id" not in session:
        return redirect(url_for("page_login", next=request.path))

    if fetch_one("SELECT id FROM topics WHERE id = %s", (topic_id,)) is None:
        flash("Ämnet hittades inte", "error")
        return redirect(url_for("page_index"))

    execute("DELETE FROM topics WHERE id = %s", (topic_id,))
    flash("Ämne borttaget", "success")
    return redirect(url_for("page_index"))


@app.route("/profile")
def page_profile():

    return render_template("profile.html")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
