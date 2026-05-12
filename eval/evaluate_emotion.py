"""
eval/evaluate_emotion.py
Offline evaluation of Novu's EmotionInference on a labelled phrase set.

Usage:
    cd /path/to/novu
    python -m eval.evaluate_emotion          # full run, prints + saves report
    python -m eval.evaluate_emotion --quick  # skip slow examples
"""

import sys
import os
import json
import time
import argparse
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from modules.emotion_inference import EmotionInference

# ---------------------------------------------------------------------------
# Labelled test set  (text, expected_emotion)
# Ground-truth covers all 6 Novu emotion labels:
#   happy | excited | neutral | frustrated | angry | sad
# ---------------------------------------------------------------------------
TEST_SET = [
    # ── happy ───────────────────────────────────────────────────────────
    ("I just got a promotion at work today!",           "happy"),
    ("My best friend is getting married and I'm thrilled!", "happy"),
    ("We finally finished the project, it feels great.", "happy"),
    ("I had such a wonderful birthday, thank you.",     "happy"),
    ("Everything worked out perfectly in the end.",     "happy"),

    # ── excited ──────────────────────────────────────────────────────────
    ("Oh my gosh I can't believe it I won the lottery!", "excited"),
    ("We're going to Disneyland tomorrow, I'm so pumped!", "excited"),
    ("This is absolutely incredible, I'm buzzing right now!", "excited"),
    ("YES! We scored in the last second — unbelievable!", "excited"),
    ("I just got accepted to my dream university!",     "excited"),

    # ── neutral ──────────────────────────────────────────────────────────
    ("What time does the library close today?",         "neutral"),
    ("Can you remind me how to make pasta?",            "neutral"),
    ("I need to schedule a dentist appointment.",       "neutral"),
    ("The meeting is at three in the afternoon.",       "neutral"),
    ("I'm just reading a book right now.",              "neutral"),
    ("What's the weather like in London?",              "neutral"),

    # ── frustrated ───────────────────────────────────────────────────────
    ("I've been stuck on this bug for six hours and nothing works.", "frustrated"),
    ("Why does this keep happening every single time?", "frustrated"),
    ("I'm so tired of repeating myself and no one listens.", "frustrated"),
    ("The printer is jammed again, I can't deal with this.", "frustrated"),
    ("I asked three times and still nothing has changed.", "frustrated"),

    # ── angry ─────────────────────────────────────────────────────────────
    ("I am absolutely furious right now, this is unacceptable!", "angry"),
    ("How dare they treat me like that, I am so angry!",         "angry"),
    ("This is outrageous and I will not stand for it.",          "angry"),
    ("I'm beyond angry — they completely betrayed my trust.",    "angry"),
    ("Stop pushing me around, I've had enough!",                 "angry"),

    # ── sad ───────────────────────────────────────────────────────────────
    ("I just found out my dog passed away this morning.",        "sad"),
    ("I feel so alone and nobody seems to care.",                "sad"),
    ("Everything feels heavy and I don't know why.",             "sad"),
    ("I miss my grandmother so much, I can't stop crying.",      "sad"),
    ("I feel completely lost and don't know what to do anymore.", "sad"),
]

EMOTION_LABELS = ["happy", "excited", "neutral", "frustrated", "angry", "sad"]

# ---------------------------------------------------------------------------

def _confusion(true_labels, pred_labels, labels):
    mat = {t: {p: 0 for p in labels} for t in labels}
    for t, p in zip(true_labels, pred_labels):
        mat[t][p] += 1
    return mat


def _metrics(mat, label):
    tp = mat[label][label]
    fp = sum(mat[r][label] for r in mat if r != label)
    fn = sum(mat[label][c] for c in mat[label] if c != label)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall    = tp / (tp + fn) if (tp + fn) else 0.0
    f1        = (2 * precision * recall / (precision + recall)
                 if (precision + recall) else 0.0)
    return precision, recall, f1


def run_evaluation(quick: bool = False):
    test_data = TEST_SET
    if quick:
        # One sample per class for a fast sanity check
        seen = set()
        test_data = []
        for phrase, label in TEST_SET:
            if label not in seen:
                test_data.append((phrase, label))
                seen.add(label)

    print("\n" + "═" * 62)
    print("  Novu — Emotion Inference Evaluation")
    print("═" * 62)
    print(f"  Model : j-hartmann/emotion-english-distilroberta-base")
    print(f"  Samples: {len(test_data)}  |  Classes: {len(EMOTION_LABELS)}")
    print("═" * 62)

    engine = EmotionInference()

    true_labels = []
    pred_labels = []
    errors      = []
    start       = time.time()

    for phrase, expected in test_data:
        predicted = engine.infer(phrase, audio_array=None)
        true_labels.append(expected)
        pred_labels.append(predicted)
        status = "✓" if predicted == expected else "✗"
        if predicted != expected:
            errors.append((phrase, expected, predicted))
        label_col = f"{expected:<12}"
        print(f"  {status}  [{label_col}→ {predicted:<12}]  "{phrase[:48]}"")

    elapsed = time.time() - start

    # ── Aggregate metrics ────────────────────────────────────────────────
    n         = len(true_labels)
    correct   = sum(t == p for t, p in zip(true_labels, pred_labels))
    accuracy  = correct / n if n else 0.0
    mat       = _confusion(true_labels, pred_labels, EMOTION_LABELS)

    print("\n" + "─" * 62)
    print(f"  {'CLASS':<14}  {'PREC':>6}  {'RECALL':>6}  {'F1':>6}  {'SUPPORT':>7}")
    print("─" * 62)

    macro_p = macro_r = macro_f1 = 0.0
    for label in EMOTION_LABELS:
        p, r, f1 = _metrics(mat, label)
        macro_p  += p; macro_r += r; macro_f1 += f1
        support = sum(1 for t in true_labels if t == label)
        print(f"  {label:<14}  {p:>6.2%}  {r:>6.2%}  {f1:>6.2%}  {support:>7}")

    n_cls = len(EMOTION_LABELS)
    print("─" * 62)
    print(f"  {'MACRO AVG':<14}  {macro_p/n_cls:>6.2%}  "
          f"{macro_r/n_cls:>6.2%}  {macro_f1/n_cls:>6.2%}  {n:>7}")
    print("─" * 62)
    print(f"\n  Overall Accuracy : {accuracy:.2%}  ({correct}/{n} correct)")
    print(f"  Elapsed time     : {elapsed:.1f}s")

    if errors:
        print(f"\n  Misclassified ({len(errors)}):")
        for phrase, exp, got in errors:
            print(f"    expected={exp:<12} got={got:<12}  "{phrase[:48]}"")

    # ── Save JSON report ─────────────────────────────────────────────────
    report_dir  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "eval")
    report_path = os.path.join(report_dir, "emotion_eval_report.json")

    report = {
        "timestamp"  : datetime.now().isoformat(),
        "model"      : "j-hartmann/emotion-english-distilroberta-base",
        "samples"    : n,
        "accuracy"   : round(accuracy, 4),
        "elapsed_s"  : round(elapsed, 2),
        "per_class"  : {},
        "misclassified": [
            {"phrase": ph, "expected": ex, "predicted": pr}
            for ph, ex, pr in errors
        ],
    }
    for label in EMOTION_LABELS:
        p, r, f1 = _metrics(mat, label)
        report["per_class"][label] = {
            "precision": round(p, 4),
            "recall"   : round(r, 4),
            "f1"       : round(f1, 4),
            "support"  : sum(1 for t in true_labels if t == label),
        }

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n  Report saved → {report_path}")
    print("═" * 62 + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true",
                        help="One sample per class (fast sanity check)")
    args = parser.parse_args()
    run_evaluation(quick=args.quick)
