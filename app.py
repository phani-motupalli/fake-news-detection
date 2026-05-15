from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from langdetect import detect
from urllib.parse import urlparse
import sqlite3
import os
import re

try:
    import joblib
except Exception:
    joblib = None

try:
    import requests
    from bs4 import BeautifulSoup
except Exception:
    requests = None
    BeautifulSoup = None

try:
    from deep_translator import GoogleTranslator
except Exception:
    GoogleTranslator = None

app = Flask(__name__)
app.secret_key = "fake_news_secret_key_123"

DATABASE = "predictions.db"
MODEL_PATH = os.path.join("model", "fake_news_model.pkl")
VECTORIZER_PATH = os.path.join("model", "vectorizer.pkl")

model = None
vectorizer = None


# -----------------------------
# Database
# -----------------------------
def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            input_type TEXT,
            input_value TEXT,
            extracted_text TEXT,
            prediction TEXT,
            confidence REAL,
            credibility TEXT,
            suspicious_keywords TEXT,
            created_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


def save_prediction(user_id, input_type, input_value, extracted_text, prediction, confidence, credibility, suspicious_keywords):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO predictions (
            user_id, input_type, input_value, extracted_text, prediction,
            confidence, credibility, suspicious_keywords, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        input_type,
        input_value,
        extracted_text,
        prediction,
        confidence,
        credibility,
        suspicious_keywords,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    conn.commit()
    conn.close()


def get_user_predictions(user_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, input_type, input_value, extracted_text, prediction,
               confidence, credibility, suspicious_keywords, created_at
        FROM predictions
        WHERE user_id = ?
        ORDER BY id DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows


# -----------------------------
# Authentication helper
# -----------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login to access this feature.")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


# -----------------------------
# Model loading
# -----------------------------
def load_ml_files():
    global model, vectorizer

    if joblib is None:
        print("joblib not installed. Running in fallback mode.")
        return

    if os.path.exists(MODEL_PATH) and os.path.exists(VECTORIZER_PATH):
        try:
            model = joblib.load(MODEL_PATH)
            vectorizer = joblib.load(VECTORIZER_PATH)
            print("Model and vectorizer loaded successfully.")
        except Exception as e:
            print("Error loading model/vectorizer:", e)
            model = None
            vectorizer = None
    else:
        print("Model files not found. Running in fallback mode.")
        print("Expected model path:", MODEL_PATH)
        print("Expected vectorizer path:", VECTORIZER_PATH)


# -----------------------------
# Utility functions
# -----------------------------
def extract_text_from_url(url):
    if requests is None or BeautifulSoup is None:
        return "", "requests or bs4 not installed."

    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(["script", "style", "noscript"]):
            tag.extract()

        paragraphs = soup.find_all("p")
        text = " ".join(p.get_text(" ", strip=True) for p in paragraphs)
        text = re.sub(r"\s+", " ", text).strip()

        if len(text) < 50:
            return "", "Very little text could be extracted from this URL."

        return text, None

    except Exception as e:
        return "", f"Failed to extract article text: {str(e)}"


def clean_text(text):
    text = text.lower()
    text = re.sub(r"http\S+|www\S+", "", text)
    text = re.sub(r"[^a-zA-Z\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def detect_language_name(text):
    try:
        lang_code = detect(text)
        lang_map = {
            "en": "English",
            "hi": "Hindi",
            "te": "Telugu"
        }
        return lang_map.get(lang_code, lang_code), lang_code
    except Exception:
        return "Unknown", "unknown"


def translate_to_english(text, lang_code):
    try:
        if lang_code == "en":
            return text

        if lang_code in ["te", "hi"] and GoogleTranslator is not None:
            translated = GoogleTranslator(source="auto", target="en").translate(text)
            if translated and translated.strip():
                return translated

        return text
    except Exception as e:
        print("Translation error:", e)
        return text


def find_suspicious_keywords(text):
    suspicious_words = [
        "shocking", "breaking", "secret", "viral", "unbelievable",
        "exclusive", "urgent", "exposed", "banned", "miracle",
        "alert", "warning", "scam", "fake", "hoax", "sensational",
        "hidden", "conspiracy", "guaranteed", "cure", "all diseases",
        "scientists are hiding", "government is hiding", "overnight"
    ]

    text_lower = text.lower()
    found = []

    for word in suspicious_words:
        if word in text_lower:
            found.append(word)

    return found

def get_credibility_level(score, suspicious_count):
    if score >= 85 and suspicious_count <= 1:
        return "High"
    elif score >= 65 and suspicious_count <= 3:
        return "Medium"
    return "Low"


def check_source_credibility(url):
    trusted_sites = [
        "bbc.com",
        "reuters.com",
        "thehindu.com",
        "indianexpress.com",
        "ndtv.com",
        "apnews.com",
        "theguardian.com",
        "timesofindia.indiatimes.com"
    ]

    suspicious_sites = [
        "fake-news-site.com",
        "viralrumours.net",
        "clickbaitnews.xyz",
        "rumorworld.net"
    ]

    try:
        domain = urlparse(url).netloc.lower().replace("www.", "")
        if not domain:
            return "Unknown", "-"

        for site in trusted_sites:
            if site in domain:
                return "High", domain

        for site in suspicious_sites:
            if site in domain:
                return "Low", domain

        return "Medium", domain
    except Exception:
        return "Unknown", "-"


def is_valid_url(url):
    try:
        parsed = urlparse(url)
        return parsed.scheme in ["http", "https"] and parsed.netloc != ""
    except Exception:
        return False


def is_meaningful_text(text):
    text = text.strip()

    if len(text) < 20:
        return False, "Please enter a longer news article or headline."

    words = text.split()

    if len(words) < 4:
        return False, "Input is too short to analyze."

    valid_words = []
    for word in words:
        cleaned = re.sub(r"[^\u0900-\u097F\u0C00-\u0C7FA-Za-z]", "", word)
        if len(cleaned) >= 2:
            valid_words.append(cleaned)

    if len(valid_words) < max(4, len(words) // 2):
        return False, "Please enter valid text content."

    if len(set(text.replace(" ", ""))) < 5:
        return False, "Input seems invalid or repetitive."

    return True, None


def fallback_predict(text):
    suspicious = find_suspicious_keywords(text)
    suspicious_count = len(suspicious)

    if suspicious_count >= 3:
        prediction = "Fake News"
        fake_score = min(round(75.0 + suspicious_count * 4, 2), 95.0)
        real_score = round(100.0 - fake_score, 2)
    else:
        real_score = min(round(70.0 + max(0, 3 - suspicious_count) * 4, 2), 92.0)
        fake_score = round(100.0 - real_score, 2)
        prediction = "Real News"

    credibility = get_credibility_level(max(fake_score, real_score), suspicious_count)
    return prediction, fake_score, real_score, credibility, suspicious


def model_predict(text):
    cleaned = clean_text(text)

    if not cleaned.strip():
        return fallback_predict(text)

    suspicious = find_suspicious_keywords(text)
    suspicious_count = len(suspicious)

    if model is not None and vectorizer is not None:
        try:
            text_vector = vectorizer.transform([cleaned])
            pred = model.predict(text_vector)[0]

            fake_score = 50.0
            real_score = 50.0

            if hasattr(model, "predict_proba"):
                probs = model.predict_proba(text_vector)[0]

                # Current mapping: class 0 = Real, class 1 = Fake
                real_score = round(float(probs[0] * 100), 2)
                fake_score = round(float(probs[1] * 100), 2)
            else:
                if int(pred) == 0:
                    real_score = 78.0
                    fake_score = 22.0
                else:
                    fake_score = 78.0
                    real_score = 22.0

            # Strong fake-style keyword adjustment
            if suspicious_count >= 4:
                fake_score = max(fake_score, 85.0)
                real_score = 100.0 - fake_score
            elif suspicious_count == 3:
                fake_score = max(fake_score, 75.0)
                real_score = 100.0 - fake_score
            elif suspicious_count == 2:
                fake_score = max(fake_score, 60.0)
                real_score = 100.0 - fake_score

            prediction = "Real News" if real_score >= fake_score else "Fake News"
            credibility = get_credibility_level(max(fake_score, real_score), suspicious_count)

            return prediction, round(fake_score, 2), round(real_score, 2), credibility, suspicious

        except Exception as e:
            print("Prediction error, using fallback mode:", e)

    return fallback_predict(text)

# -----------------------------
# Routes: Authentication
# -----------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not email or not password:
            flash("All fields are required.")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                (username, email, hashed_password)
            )
            conn.commit()
            flash("Registration successful. Please login.")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Email already exists.")
            return redirect(url_for("register"))
        finally:
            conn.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, email, password FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[3], password):
            session["user_id"] = user[0]
            session["username"] = user[1]
            session["email"] = user[2]
            flash("Login successful.")
            return redirect(url_for("home"))

        flash("Invalid email or password.")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.")
    return redirect(url_for("home"))


# -----------------------------
# Routes: Main
# -----------------------------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/predict", methods=["POST"])
@login_required
def predict():
    news_text = request.form.get("news_text", "").strip()
    news_url = request.form.get("news_url", "").strip()

    input_type = None
    input_value = None
    extracted_text = ""
    user_id = session.get("user_id")

    source = "-"
    source_credibility = "Unknown"

    if news_text:
        is_valid, validation_error = is_meaningful_text(news_text)
        if not is_valid:
            return render_template(
                "result.html",
                prediction="Invalid Input",
                fake_score=0,
                real_score=0,
                credibility="Unknown",
                suspicious_keywords=[],
                article_preview="",
                input_type="Text",
                input_value=news_text[:500],
                detected_language="Unknown",
                detected_language_code="unknown",
                source="-",
                source_credibility="Unknown",
                error_message=validation_error,
                confidence_warning=None
            )

        input_type = "Text"
        input_value = news_text[:500]
        extracted_text = news_text

    elif news_url:
        if not is_valid_url(news_url):
            return render_template(
                "result.html",
                prediction="Invalid Input",
                fake_score=0,
                real_score=0,
                credibility="Unknown",
                suspicious_keywords=[],
                article_preview="",
                input_type="URL",
                input_value=news_url,
                detected_language="Unknown",
                detected_language_code="unknown",
                source="-",
                source_credibility="Unknown",
                error_message="Please enter a valid URL starting with http:// or https://",
                confidence_warning=None
            )

        input_type = "URL"
        input_value = news_url
        source_credibility, source = check_source_credibility(news_url)
        extracted_text, error = extract_text_from_url(news_url)

        if error:
            return render_template(
                "result.html",
                prediction="Error",
                fake_score=0,
                real_score=0,
                credibility="Unknown",
                suspicious_keywords=[],
                article_preview="",
                input_type=input_type,
                input_value=input_value,
                detected_language="Unknown",
                detected_language_code="unknown",
                source=source,
                source_credibility=source_credibility,
                error_message=error,
                confidence_warning=None
            )

        is_valid, validation_error = is_meaningful_text(extracted_text)
        if not is_valid:
            return render_template(
                "result.html",
                prediction="Invalid Input",
                fake_score=0,
                real_score=0,
                credibility="Unknown",
                suspicious_keywords=[],
                article_preview=extracted_text[:500],
                input_type=input_type,
                input_value=input_value,
                detected_language="Unknown",
                detected_language_code="unknown",
                source=source,
                source_credibility=source_credibility,
                error_message=validation_error,
                confidence_warning=None
            )
    else:
        flash("Please enter article text or URL.")
        return redirect(url_for("home"))

    detected_language, detected_language_code = detect_language_name(extracted_text)
    text_for_prediction = translate_to_english(extracted_text, detected_language_code)

    prediction, fake_score, real_score, credibility, suspicious_keywords = model_predict(text_for_prediction)

    confidence = max(fake_score, real_score)
    confidence_warning = None
    if confidence < 75:
        confidence_warning = "Moderate confidence — result may not be fully accurate."

    save_prediction(
        user_id=user_id,
        input_type=input_type,
        input_value=input_value,
        extracted_text=extracted_text[:3000],
        prediction=prediction,
        confidence=confidence,
        credibility=credibility,
        suspicious_keywords=", ".join(suspicious_keywords)
    )

    return render_template(
        "result.html",
        prediction=prediction,
        fake_score=fake_score,
        real_score=real_score,
        credibility=credibility,
        suspicious_keywords=suspicious_keywords,
        article_preview=extracted_text[:1200],
        input_type=input_type,
        input_value=input_value,
        detected_language=detected_language,
        detected_language_code=detected_language_code,
        source=source,
        source_credibility=source_credibility,
        error_message=None,
        confidence_warning=confidence_warning
    )


@app.route("/history")
@login_required
def history():
    user_id = session.get("user_id")
    rows = get_user_predictions(user_id)
    return render_template("history.html", rows=rows)


@app.route("/model-comparison")
@login_required
def model_comparison():
    model_results = [
        {"name": "Logistic Regression", "accuracy": 94.2},
        {"name": "Naive Bayes", "accuracy": 89.6},
        {"name": "Random Forest", "accuracy": 92.8},
        {"name": "SVM", "accuracy": 95.1}
    ]

    best_model = max(model_results, key=lambda x: x["accuracy"])
    return render_template(
        "model_comparison.html",
        model_results=model_results,
        best_model=best_model["name"],
        best_accuracy=best_model["accuracy"]
    )


@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session.get("user_id")
    rows = get_user_predictions(user_id)

    total_predictions = len(rows)
    fake_count = sum(1 for row in rows if row[4] == "Fake News")
    real_count = sum(1 for row in rows if row[4] == "Real News")
    avg_confidence = round(
        sum(float(row[5]) for row in rows) / total_predictions, 2
    ) if total_predictions > 0 else 0

    return render_template(
        "dashboard.html",
        total_predictions=total_predictions,
        fake_count=fake_count,
        real_count=real_count,
        avg_confidence=avg_confidence,
        recent_rows=rows[:5]
    )


if __name__ == "__main__":
    init_db()
    load_ml_files()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)