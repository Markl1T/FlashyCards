import os
import sqlite3, smtplib
from flask import Flask, render_template, url_for, request, redirect, flash, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
load_dotenv()
app.secret_key = os.getenv("SECRET_KEY", "secret_key")
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = os.getenv("SESSION_TYPE", "filesystem")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

db_path = os.getenv("DATABASE_PATH", "flashycards.db")

with sqlite3.connect(db_path) as conn:
    cu = conn.cursor()
    cu.execute("""CREATE TABLE IF NOT EXISTS users (
               user_id INTEGER PRIMARY KEY AUTOINCREMENT, 
               user_name TEXT NOT NULL UNIQUE, 
               email TEXT NOT NULL UNIQUE, 
               password_hash TEXT NOT NULL,
               created_at TEXT DEFAULT (DATETIME('now')),
               updated_at TEXT DEFAULT (DATETIME('now')))""")
    
    cu.execute("""CREATE TABLE IF NOT EXISTS decks (
               deck_id INTEGER PRIMARY KEY AUTOINCREMENT, 
               user_id INTEGER NOT NULL, 
               deck_name TEXT NOT NULL, 
               description TEXT,
               created_at TEXT DEFAULT (DATETIME('now')),
               updated_at TEXT DEFAULT (DATETIME('now')),
               UNIQUE (user_id, deck_name),
               FOREIGN KEY (user_id) REFERENCES users(user_id))""")
    
    cu.execute("""CREATE TABLE IF NOT EXISTS flashcards (
               flashcard_id INTEGER PRIMARY KEY AUTOINCREMENT, 
               deck_id INTEGER NOT NULL, 
               front TEXT NOT NULL, 
               back TEXT NOT NULL,
               FOREIGN KEY (deck_id) REFERENCES decks(deck_id))""")


class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username


@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""SELECT user_id, user_name 
                FROM users 
                WHERE user_id = ?""", (user_id,))
    user_data = cur.fetchone()
    conn.close()
    if user_data:
        return User(user_data[0], user_data[1])
    return None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        if not email or not username or not password or not confirmation:
            flash("You must fill all the required information.", "warning")
            return render_template("register.html")
        elif password != confirmation:
            flash("Your passwords do not match.", "warning")
            return render_template("register.html")
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            try:
                cur.execute("""INSERT INTO users (email, user_name, password_hash, created_at, updated_at) 
                            VALUES (?, ?, ?, DATETIME('now'), DATETIME('now'))""", (email, username, generate_password_hash(password)))
                conn.commit()
                flash("You are registered.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("You already have an account or the username is taken.", "warning")
                return render_template("register.html")
    else:
        return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    session.clear()
    if request.method == "POST":
        email_username = request.form.get("email_username")
        password = request.form.get("password")
        if not email_username or not password:
            flash("You must fill all the required information.", "warning")
            return render_template("login.html")
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            rows = cur.execute("""SELECT * 
                               FROM users 
                               WHERE email = ? OR user_name = ?""", (email_username, email_username))
        rows = rows.fetchall()
        if not rows or not check_password_hash(rows[0][3], password):
            flash("Your email/username or password was incorrect", "danger")
            return render_template("login.html")
        id = rows[0][0]
        username = rows[0][1]
        user = User(id, username)
        login_user(user, remember=True)
        flash("You have logged in.", "success")
        return redirect(url_for("decks"))
    else:
        return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have logged out.", "success")
    return redirect(url_for("index"))


@app.route("/create", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        name = request.form.get("name")
        description = request.form.get("description")
        nrOfFlashcards = int(request.form.get("nrOfFlashcards"))
        if not name:
            flash("Your deck must have a name.", "warning")
            return redirect(request.referrer)
        flashcards = []
        for i in range(1, nrOfFlashcards+1):
            front = request.form.get(f"front_{i}")
            back = request.form.get(f"back_{i}")
            if front and back:
                flashcards.append((None, front, back))
        if not flashcards:
            flash("Your deck was not created since you did not add any flashcards in it!", "danger")
            return redirect(url_for("decks"))
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            try:
                cur.execute("""INSERT INTO decks (user_id, deck_name, description, created_at, updated_at) 
                            VALUES (?, ?, ?, DATETIME('now'), DATETIME('now'))""", (current_user.id, name, description))
                conn.commit()
            except sqlite3.IntegrityError:
                flash("You already have a deck with this name!", "danger")
                return render_template("create.html")
            deck_id = cur.lastrowid
            flashcards = [(deck_id, front, back) for _, front, back in flashcards]
            cur.executemany("""INSERT INTO flashcards (deck_id, front, back) 
                            VALUES (?, ?, ?)""", flashcards)
            conn.commit()
        flash("Your deck was created successfully!", "success")
        return redirect(url_for("decks"))
    else:
        return render_template("create.html")


@app.route("/decks", methods=["GET", "POST"])
@login_required
def decks():
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        deck_rows = cur.execute("""SELECT deck_id, deck_name, description 
                                FROM decks
                                WHERE user_id = ?""", (current_user.id,))
        deck_rows = deck_rows.fetchall()
        return render_template("decks.html", rows = deck_rows, username = current_user.username)


@app.route("/decks/search", methods=["GET"])
@login_required
def search():
    searched_deck_name = request.args.get("deck_name")
    if searched_deck_name:
        searched_deck_name = f"%{searched_deck_name}%"
    else:
        searched_deck_name = "%"
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        deck_rows = cur.execute("""SELECT deck_id, deck_name, description 
                                FROM decks
                                WHERE user_id = ? AND deck_name LIKE ?""", (current_user.id, searched_deck_name))
        deck_rows = deck_rows.fetchall()
        return render_template("search.html", rows = deck_rows, username = current_user.username, searched_deck_name = request.args.get("deck_name"))


@app.route("/decks/<username>/<deck_name>/edit", methods=["GET", "POST"])
@login_required
def edit(username, deck_name):
    if request.method == "POST":
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            deck_id = cur.execute("""SELECT deck_id 
                                  FROM decks 
                                  WHERE deck_name = ?""", (deck_name,))
            deck_id = cur.fetchone()[0]
            flashcards = cur.execute("""SELECT flashcard_id
                                    FROM flashcards
                                    WHERE deck_id = ?""", (deck_id,))
            flashcards = cur.fetchall()
            initial_description = request.form.get("initial_description")
            description = request.form.get("description")
            new_deck_name = request.form.get("name")
            if new_deck_name != deck_name:
                try:
                    cur.execute("""UPDATE decks 
                                SET deck_name = ?
                                WHERE deck_id = ?""", (new_deck_name, deck_id))
                except sqlite3.IntegrityError:
                    flash(f"You already have a deck named '{new_deck_name}'.", "danger")
                    new_deck_name = deck_name
            if initial_description != description:
                cur.execute("""UPDATE decks 
                            SET description = ?
                            WHERE deck_id = ?""", (description, deck_id))
            conn.commit()
            for flashcard in flashcards:
                initial_front = request.form.get(f"initial_front_{flashcard[0]}")
                initial_back = request.form.get(f"initial_back_{flashcard[0]}")
                front = request.form.get(f"front_{flashcard[0]}")
                back = request.form.get(f"back_{flashcard[0]}")
                if not front or not back:
                    cur.execute("""DELETE FROM flashcards 
                                WHERE flashcard_id = ?""", (flashcard[0],))
                elif front != initial_front or back != initial_back:
                    cur.execute("""UPDATE flashcards 
                                SET front = ?, back = ? 
                                WHERE flashcard_id = ?""", (front, back, flashcard[0]))
                conn.commit()
            cur.execute("""UPDATE decks
                        SET updated_at = DATETIME('now')
                        WHERE deck_id = ?""", (deck_id,))
            conn.commit()
            nr_of_new_flashcards = int(request.form.get("nrOfNewFlashcards"))
            for i in range(nr_of_new_flashcards):
                new_front = request.form.get(f"new_front_{i+1}")
                new_back = request.form.get(f"new_back_{i+1}")
                if new_front and new_back:
                    cur.execute("""INSERT INTO flashcards (deck_id, front, back)
                                VALUES (?, ?, ?)""", (deck_id, new_front, new_back))
                    conn.commit()
        flash("Your deck was updated successfully.", "success")
        return redirect(url_for("flashcards", username=username, deck_name=new_deck_name))
    else:
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            id = cur.execute("""SELECT u.user_id
                            FROM users u
                            JOIN decks d ON d.user_id = u.user_id
                            WHERE u.user_id = ? AND d.deck_name = ?""", (current_user.id, deck_name))
            id = id.fetchone()
            if not id:
                flash("You do not have access to edit that deck", "danger")
                return redirect(url_for("error"))
            flashcards = cur.execute("""SELECT f.flashcard_id, f.front, f.back
                                    FROM flashcards f
                                    JOIN decks d ON f.deck_id = d.deck_id
                                    JOIN users u ON d.user_id = u.user_id
                                    WHERE u.user_name = ? AND d.deck_name = ?""", (username, deck_name))
            flashcards = flashcards.fetchall()
            if not flashcards:
                return redirect(url_for("error"))
            description = cur.execute("""SELECT description 
                                      FROM decks 
                                      WHERE deck_name = ?""", (deck_name,))
            description = description.fetchone()[0]
        return render_template("edit.html", flashcards=flashcards, deck_name=deck_name, username=username, description=description)


@app.route("/decks/<username>/<deck_name>", methods=["GET", "POST"])
def flashcards(username, deck_name):
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        flashcards = cur.execute("""SELECT f.front, f.back
                                 FROM flashcards f
                                 JOIN decks d ON f.deck_id = d.deck_id
                                 JOIN users u ON d.user_id = u.user_id
                                 WHERE u.user_name = ? AND d.deck_name = ?""", (username, deck_name))
        flashcards = flashcards.fetchall()
        if not flashcards:
            return redirect(url_for("error"))
        description = cur.execute("""SELECT d.description 
                                  FROM decks d
                                  JOIN users u ON d.user_id = u.user_id 
                                  WHERE u.user_name = ? AND d.deck_name = ?""", (username, deck_name))
        description = cur.fetchone()[0]
    return render_template("flashcards.html", flashcards = flashcards, deck_name=deck_name, username=username, description=description)


@app.route("/delete_flashcard", methods=["POST"])
@login_required
def delete_flashcard():
    with sqlite3.connect(db_path) as conn:
        flashcard_id = request.form.get("confirmation")
        cur = conn.cursor()
        cur.execute("""SELECT deck_id 
                    FROM flashcards 
                    WHERE flashcard_id = ?""", (flashcard_id,))
        deck_id = cur.fetchone()[0]
        cur.execute("""DELETE FROM flashcards 
                    WHERE flashcard_id = ?""", (flashcard_id,))
        conn.commit()
        cur.execute("""SELECT COUNT(*) 
                    FROM flashcards 
                    WHERE deck_id = ?""", (deck_id,))
        flashcardsInDeck = cur.fetchone()[0]
        if flashcardsInDeck == 0:
            cur.execute("""DELETE FROM decks 
                        WHERE deck_id = ?""", (deck_id,))
            conn.commit()
            flash("Flashcard and Deck deleted successfully.", "success")
            return redirect(url_for("decks"))
    flash("Flashcard deleted successfully.", "success")
    return redirect(request.referrer)


@app.route("/delete_deck", methods=["POST"])
@login_required
def delete_deck():
    with sqlite3.connect(db_path) as conn:
        deck_id = request.form.get("confirmation")
        cur = conn.cursor()
        cur.execute("""DELETE FROM flashcards 
                    WHERE deck_id = ?""", (deck_id,))
        conn.commit()
        cur.execute("""DELETE FROM decks 
                    WHERE deck_id = ?""", (deck_id,))
        conn.commit()
    flash("Deck deleted successfully.", "success")
    return redirect(url_for("decks"))


@app.route("/contact_us", methods=["GET", "POST"])
@login_required
def contact_us():
    if request.method == "POST":
        subject = request.form.get("subject")
        body = request.form.get("body")
        if not subject or not body:
            flash("Enter a subject and a body for the message!", "warning")
            return render_template("contact-us.html")
        body += "\n\nSent by: \n" + current_user.username
        email = os.getenv("EMAIL")
        password = os.getenv("EMAIL_PASSWORD")
        message = MIMEMultipart()
        message["From"] = email
        message["To"] = email
        message["Subject"] = subject
        message.attach(MIMEText(body, "plain"))
        try:
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(email, password)
                server.sendmail(email, email, message.as_string())
        except Exception:
            flash("Something went wrong.", "danger")
            return redirect(url_for("index"))
        flash("Your email was sent successfully!", "success")
        return redirect(url_for("index"))
    else:
        return render_template("contact-us.html")


@app.route("/error")
def error():
    return render_template("error.html")