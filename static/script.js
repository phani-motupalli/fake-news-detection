function toggleTheme() {
    document.body.classList.toggle("dark-mode");

    const isDark = document.body.classList.contains("dark-mode");
    localStorage.setItem("theme", isDark ? "dark" : "light");
}

function applySavedTheme() {
    const savedTheme = localStorage.getItem("theme");
    if (savedTheme === "dark") {
        document.body.classList.add("dark-mode");
    }
}

function clearForm() {
    const textBox = document.getElementById("news_text");
    const urlBox = document.getElementById("news_url");

    if (textBox) textBox.value = "";
    if (urlBox) urlBox.value = "";
}

document.addEventListener("DOMContentLoaded", function () {
    applySavedTheme();

    const form = document.getElementById("analyzeForm");
    const loadingBox = document.getElementById("loadingBox");
    const analyzeBtn = document.getElementById("analyzeBtn");

    if (form) {
        form.addEventListener("submit", function () {
            if (loadingBox) {
                loadingBox.classList.remove("hidden");
            }
            if (analyzeBtn) {
                analyzeBtn.disabled = true;
                analyzeBtn.innerText = "Analyzing...";
            }
        });
    }
});