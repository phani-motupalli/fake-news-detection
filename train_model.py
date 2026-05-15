import pandas as pd
import re
import string
import joblib

from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, classification_report

from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import MultinomialNB
from sklearn.ensemble import RandomForestClassifier

# Load datasets
fake = pd.read_csv("dataset/Fake.csv")
true = pd.read_csv("dataset/True.csv")

# Add labels
fake["label"] = 0
true["label"] = 1

# Keep needed columns
fake = fake[["title", "text", "label"]]
true = true[["title", "text", "label"]]

# Combine
data = pd.concat([fake, true], axis=0)
data = data.sample(frac=1, random_state=42).reset_index(drop=True)

# Combine title and text
data["content"] = data["title"] + " " + data["text"]

# Clean text
def clean_text(text):
    text = str(text).lower()
    text = re.sub(r"https?://\S+|www\.\S+", "", text)
    text = re.sub(r"<.*?>", "", text)
    text = re.sub(r"[%s]" % re.escape(string.punctuation), "", text)
    text = re.sub(r"\n", " ", text)
    return text

data["content"] = data["content"].apply(clean_text)

# Split
X = data["content"]
y = data["label"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

# TF-IDF with n-grams
vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_df=0.7)

X_train_vec = vectorizer.fit_transform(X_train)
X_test_vec = vectorizer.transform(X_test)

# Models
models = {
    "Logistic Regression": LogisticRegression(max_iter=1000),
    "Naive Bayes": MultinomialNB(),
    "Random Forest": RandomForestClassifier(n_estimators=100, random_state=42)
}

best_model = None
best_model_name = ""
best_accuracy = 0

print("\nMODEL COMPARISON RESULTS\n")

for name, model in models.items():
    model.fit(X_train_vec, y_train)
    y_pred = model.predict(X_test_vec)
    acc = accuracy_score(y_test, y_pred)

    print(f"Model: {name}")
    print(f"Accuracy: {acc:.4f}")
    print(classification_report(y_test, y_pred))
    print("-" * 60)

    if acc > best_accuracy:
        best_accuracy = acc
        best_model = model
        best_model_name = name

# Save best model and vectorizer
joblib.dump(best_model, "model/fake_news_model.pkl")
joblib.dump(vectorizer, "model/vectorizer.pkl")

# Save comparison results
results_df = pd.DataFrame({
    "Model": list(models.keys()),
    "Accuracy": [
        accuracy_score(y_test, models["Logistic Regression"].predict(X_test_vec)),
        accuracy_score(y_test, models["Naive Bayes"].predict(X_test_vec)),
        accuracy_score(y_test, models["Random Forest"].predict(X_test_vec))
    ]
})

results_df.to_csv("model/model_comparison.csv", index=False)

print(f"\nBest Model: {best_model_name}")
print(f"Best Accuracy: {best_accuracy:.4f}")
print("Best model and vectorizer saved successfully.")
print("Model comparison saved to model/model_comparison.csv")