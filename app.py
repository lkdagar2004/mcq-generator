from flask import Flask, render_template, request
from flask_bootstrap import Bootstrap
import spacy
from collections import Counter
import random
from PyPDF2 import PdfReader
import io
import sys
import os

app = Flask(__name__)
Bootstrap(app)

# Attempt to load spaCy model; exit with clear message if missing.
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    print(
        "ERROR: spaCy model 'en_core_web_sm' is not installed in this environment.\n"
        "Install it inside your virtualenv with:\n"
        "    python -m spacy download en_core_web_sm\n"
        "Then re-run this app.",
        file=sys.stderr,
    )
    sys.exit(1)


def generate_mcqs(text, num_questions=5):
    """
    Generate up to `num_questions` MCQs from `text`.
    Each MCQ is a tuple: (question_stem, answer_choices_list, correct_answer_letter)
    """
    if not text:
        return []

    doc = nlp(text)
    sentences = [sent.text.strip() for sent in doc.sents if sent.text.strip()]
    if not sentences:
        return []

    # Build a global noun/proper-noun pool (lemmas)
    global_nouns = [token.lemma_ for token in doc if token.pos_ in ("NOUN", "PROPN")]
    global_nouns = [w for w in dict.fromkeys(global_nouns) if w]

    num_questions = min(num_questions, len(sentences))
    selected_sentences = random.sample(sentences, num_questions)

    mcqs = []
    for sentence in selected_sentences:
        sent_doc = nlp(sentence)
        nouns = [token.lemma_ for token in sent_doc if token.pos_ in ("NOUN", "PROPN")]
        nouns = [n for n in dict.fromkeys(nouns) if n]

        # Choose subject
        if not nouns and global_nouns:
            subject = random.choice(global_nouns)
        elif nouns:
            subject = Counter(nouns).most_common(1)[0][0]
        else:
            # nothing to use — skip
            continue

        # Replace first case-insensitive occurrence of subject with blank
        lower_sentence = sentence.lower()
        subj_lower = subject.lower()
        idx = lower_sentence.find(subj_lower)
        if idx != -1:
            question_stem = sentence[:idx] + "______" + sentence[idx + len(subject):]
        else:
            # fallback: replace first exact-match occurrence
            question_stem = sentence.replace(subject, "______", 1)

        # Build distractors from sentence nouns then global nouns excluding the subject
        distractor_pool = [n for n in nouns + global_nouns if n.lower() != subject.lower()]
        distractor_pool = list(dict.fromkeys(distractor_pool))

        # Ensure at least 3 distractors (use placeholders as last resort)
        while len(distractor_pool) < 3:
            distractor_pool.append("[distractor]")

        random.shuffle(distractor_pool)
        answer_choices = [subject] + distractor_pool[:3]
        random.shuffle(answer_choices)

        correct_letter = chr(65 + answer_choices.index(subject))  # 'A', 'B', ...

        mcqs.append((question_stem, answer_choices, correct_letter))

    return mcqs


def process_pdf(file_storage):
    """
    Extract text from a Flask FileStorage (uploaded PDF).
    Returns concatenated text or empty string on failure.
    """
    # Try reader with file_storage.stream first (non-destructive)
    try:
        reader = PdfReader(file_storage.stream)
    except Exception:
        # Fallback: read bytes and use BytesIO
        try:
            file_storage.stream.seek(0)
            file_bytes = file_storage.read()
            reader = PdfReader(io.BytesIO(file_bytes))
        except Exception:
            return ""

    text_parts = []
    for p in reader.pages:
        try:
            page_text = p.extract_text()
        except Exception:
            page_text = None
        if page_text:
            text_parts.append(page_text)
    return "\n".join(text_parts)


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        text = ""

        # files input name should be "files[]" in form
        uploaded_files = request.files.getlist("files[]")
        if uploaded_files and uploaded_files[0].filename != "":
            for f in uploaded_files:
                fname = f.filename.lower()
                if fname.endswith(".pdf"):
                    text += process_pdf(f) + "\n"
                elif fname.endswith(".txt"):
                    try:
                        f.stream.seek(0)
                        text += f.read().decode("utf-8", errors="ignore") + "\n"
                    except Exception:
                        try:
                            f.stream.seek(0)
                            text += f.read().decode("latin-1", errors="ignore") + "\n"
                        except Exception:
                            continue
        else:
            text = request.form.get("text", "")

        try:
            num_questions = int(request.form.get("num_questions", 5))
        except (TypeError, ValueError):
            num_questions = 5

        mcqs = generate_mcqs(text, num_questions=num_questions)
        mcqs_with_index = [(i + 1, mcq) for i, mcq in enumerate(mcqs)]
        return render_template("mcqs.html", mcqs=mcqs_with_index)

    return render_template("index.html")


if __name__ == "__main__":
    # Optional: print template folder for quick debugging
    print("Template folder:", app.template_folder)
    # Use a non-default port to avoid conflicts; change as needed.
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=True, port=port, host="127.0.0.1")
