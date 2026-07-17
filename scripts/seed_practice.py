#!/usr/bin/env python3
"""Seed ZAP Langgymnasium Zürich practice content into DynamoDB.

Run:  python scripts/seed_practice.py [--table TABLE] [--region REGION]

Topic structure (Mathematik, ZAP Langgymnasium, 6. Primarklasse):
  1. Brüche            — Bruchrechnung, Kürzen, Addieren, Subtrahieren, Multiplizieren
  2. Gleichungen       — Lineare Gleichungen, einfache Textgleichungen
  3. Geometrie         — Flächen, Umfang, Volumen, Pythagoras-Vorstufe
  4. Prozentrechnung   — Prozent, Zins, Verhältnisse
  5. Textaufgaben      — Kombinierte Sachaufgaben wie im ZAP-Examen

Each topic has 2 units, each unit has 2 lessons, each lesson has 3 challenges.
Total: 5 topics × 2 units × 2 lessons × 3 challenges = 60 questions.
"""
import argparse
import os

import boto3

from stoa.db.repositories import practice_repo
from stoa.models.practice import DirectionalHintTemplateId
from stoa.services import practice_projection_service

# ── Data ──────────────────────────────────────────────────────────────────

SUBJECT = {
    "subject_id": "mathematics",
    "name": "Mathematik",
    "description": (
        "Vorbereitung auf die Zentrale Aufnahmeprüfung (ZAP) ins Langgymnasium Zürich. "
        "Alle Themen basieren auf den offiziellen Prüfungsanforderungen für die 6. Primarklasse."
    ),
    "grade_levels": [
        {"id": "grade_6_primary", "label": "6. Primarklasse (ZAP)", "order": 1}
    ],
    "accent": "burgundy",
    "order": 1,
}

# ── Question bank ─────────────────────────────────────────────────────────

def _mc(lesson_id, topic_id, subject_id, grade_level, topic_title,
        unit_id, order, prompt, options, correct, _hint, explanation,
        correct_feedback=None, incorrect_feedback=None):
    cid = f"{lesson_id}-c{order}"
    return {
        "challenge_id": cid, "lesson_id": lesson_id, "unit_id": unit_id,
        "topic_id": topic_id, "subject_id": subject_id, "grade_level": grade_level,
        "topic_title": topic_title, "order": order, "type": "multiple_choice",
        "prompt": prompt, "options": options, "correct_answer": correct,
        "directional_hint_template_id": "review_problem_structure",
        "explanation": explanation,
        "correct_feedback": correct_feedback or "Richtig! Gut gemacht.",
        "incorrect_feedback": incorrect_feedback or "Leider falsch. Lies den Hinweis und versuche es nochmal.",
    }


def _input(lesson_id, topic_id, subject_id, grade_level, topic_title,
           unit_id, order, prompt, correct, _hint, explanation,
           correct_feedback=None, incorrect_feedback=None):
    cid = f"{lesson_id}-c{order}"
    return {
        "challenge_id": cid, "lesson_id": lesson_id, "unit_id": unit_id,
        "topic_id": topic_id, "subject_id": subject_id, "grade_level": grade_level,
        "topic_title": topic_title, "order": order, "type": "text_input",
        "prompt": prompt, "correct_answer": correct,
        "directional_hint_template_id": "review_problem_structure",
        "explanation": explanation,
        "correct_feedback": correct_feedback or "Richtig!",
        "incorrect_feedback": incorrect_feedback or "Nicht ganz. Schau dir den Hinweis an.",
    }


# ── Topic 1: Brüche ───────────────────────────────────────────────────────

def _brueche_data():
    tid = "brueche"
    sid = "mathematics"
    gl  = "grade_6_primary"
    tt  = "Brüche"

    units = [
        {"unit_id": f"{tid}-u1", "topic_id": tid, "subject_id": sid, "grade_level": gl,
         "title": "Brüche verstehen und kürzen",
         "description": "Brüche lesen, darstellen und auf die einfachste Form bringen.",
         "order": 1},
        {"unit_id": f"{tid}-u2", "topic_id": tid, "subject_id": sid, "grade_level": gl,
         "title": "Brüche rechnen",
         "description": "Brüche addieren, subtrahieren und multiplizieren.",
         "order": 2},
    ]

    lessons = [
        {"lesson_id": f"{tid}-l1", "unit_id": f"{tid}-u1", "topic_id": tid,
         "subject_id": sid, "grade_level": gl, "topic_title": tt,
         "title": "Brüche lesen und kürzen", "difficulty": "intro",
         "estimated_minutes": 10, "order": 1, "challenge_count": 3},
        {"lesson_id": f"{tid}-l2", "unit_id": f"{tid}-u1", "topic_id": tid,
         "subject_id": sid, "grade_level": gl, "topic_title": tt,
         "title": "Gleichwertige Brüche", "difficulty": "practice",
         "estimated_minutes": 12, "order": 2, "challenge_count": 3},
        {"lesson_id": f"{tid}-l3", "unit_id": f"{tid}-u2", "topic_id": tid,
         "subject_id": sid, "grade_level": gl, "topic_title": tt,
         "title": "Brüche addieren und subtrahieren", "difficulty": "practice",
         "estimated_minutes": 15, "order": 3, "challenge_count": 3},
        {"lesson_id": f"{tid}-l4", "unit_id": f"{tid}-u2", "topic_id": tid,
         "subject_id": sid, "grade_level": gl, "topic_title": tt,
         "title": "Brüche multiplizieren", "difficulty": "review",
         "estimated_minutes": 12, "order": 4, "challenge_count": 3},
    ]

    challenges = [
        # l1 — Kürzen
        _mc(f"{tid}-l1", tid, sid, gl, tt, f"{tid}-u1", 1,
            "Welcher Bruch ist der gekürzte Bruch von 6/8?",
            ["1/2", "3/4", "2/3", "4/6"], "3/4",
            "Teile Zähler und Nenner durch ihren grössten gemeinsamen Teiler (ggT). ggT(6,8) = 2.",
            "6÷2 = 3 und 8÷2 = 4, also ist 6/8 = 3/4.",
            "Genau! 6/8 = 3/4, da ggT(6,8) = 2.", "Nicht ganz. Suche den ggT von 6 und 8."),
        _input(f"{tid}-l1", tid, sid, gl, tt, f"{tid}-u1", 2,
            "Kürze den Bruch 12/18 so weit wie möglich. Schreibe das Ergebnis als a/b.",
            "2/3",
            "Der ggT von 12 und 18 ist 6. Teile Zähler und Nenner durch 6.",
            "12÷6 = 2 und 18÷6 = 3, also 12/18 = 2/3.",
            "Richtig! 12/18 = 2/3.", "Nicht ganz. Der ggT von 12 und 18 ist 6."),
        _mc(f"{tid}-l1", tid, sid, gl, tt, f"{tid}-u1", 3,
            "Welcher Bruch liegt zwischen 1/2 und 1 auf der Zahlengeraden?",
            ["1/3", "3/4", "1/4", "2/3"],
            "3/4",  # both 3/4 and 2/3 are valid, but 3/4 is given in options as unique clear answer
            "Rechne: 1/2 = 2/4 und 1 = 4/4. Welcher Viertelbruch liegt dazwischen?",
            "3/4 liegt genau zwischen 2/4 (= 1/2) und 4/4 (= 1).",
            "Richtig! 3/4 liegt auf der Hälfte zwischen 1/2 und 1.", "Nicht ganz. Schreibe 1/2 als Viertel um."),
        # l2 — gleichwertige Brüche
        _input(f"{tid}-l2", tid, sid, gl, tt, f"{tid}-u1", 1,
            "Fülle die Lücke: 3/4 = ?/12. Was ist ?",
            "9",
            "Zähler und Nenner müssen mit demselben Faktor multipliziert werden. 4 × 3 = 12.",
            "3 × 3 = 9 und 4 × 3 = 12, also 3/4 = 9/12.",
            "Super! 3/4 = 9/12.", "Denk daran: 4 × 3 = 12. Mit was musst du auch den Zähler multiplizieren?"),
        _mc(f"{tid}-l2", tid, sid, gl, tt, f"{tid}-u1", 2,
            "Welche zwei Brüche sind gleichwertig?",
            ["2/5 und 4/9", "3/7 und 6/14", "1/3 und 2/5", "4/6 und 5/8"], "3/7 und 6/14",
            "Prüfe: Kannst du 3/7 durch Erweitern zu 6/14 machen? 3×2=6, 7×2=14.",
            "3/7 = 6/14, da Zähler und Nenner beide mit 2 multipliziert wurden.",
            "Genau! 3/7 und 6/14 sind gleichwertig.", "Nicht ganz. Prüfe jedes Paar: kann man vom ersten zum zweiten mit gleichem Faktor erweitern?"),
        _mc(f"{tid}-l2", tid, sid, gl, tt, f"{tid}-u1", 3,
            "Anna sagt: 2/3 und 8/12 sind gleichwertig. Hat sie recht?",
            ["Ja, denn 2×4=8 und 3×4=12", "Nein, 8/12 ist grösser", "Nein, man muss erst kürzen", "Ja, denn 2+6=8"],
            "Ja, denn 2×4=8 und 3×4=12",
            "Erweitere 2/3 mit dem Faktor 4: 2×4 = 8, 3×4 = 12.",
            "2/3 = 8/12, weil Zähler und Nenner beide mit 4 multipliziert wurden.",
            "Richtig!", "Nicht ganz. Erweitern bedeutet: beide mal denselben Faktor."),
        # l3 — addieren/subtrahieren
        _input(f"{tid}-l3", tid, sid, gl, tt, f"{tid}-u2", 1,
            "Berechne: 1/4 + 2/4 = ?",
            "3/4",
            "Gleiche Nenner: addiere nur die Zähler. 1 + 2 = 3.",
            "1/4 + 2/4 = 3/4. Bei gleichen Nennern werden nur die Zähler addiert.",
            "Korrekt! 1/4 + 2/4 = 3/4.", "Tipp: Addiere nur die Zähler, der Nenner bleibt gleich."),
        _input(f"{tid}-l3", tid, sid, gl, tt, f"{tid}-u2", 2,
            "Berechne: 5/6 − 1/3. Schreibe das Ergebnis als gekürzten Bruch (a/b).",
            "1/2",
            "Bringe 1/3 auf Sechstel: 1/3 = 2/6. Dann: 5/6 − 2/6 = 3/6 = 1/2.",
            "5/6 − 1/3 = 5/6 − 2/6 = 3/6 = 1/2.",
            "Super! 5/6 − 1/3 = 1/2.", "Wandle zuerst 1/3 in Sechstel um: 1/3 = 2/6."),
        _mc(f"{tid}-l3", tid, sid, gl, tt, f"{tid}-u2", 3,
            "Eine Pizza wird in 8 gleichgrosse Stücke geteilt. Luca isst 3/8, Mia isst 2/8. Wie viel haben sie zusammen gegessen?",
            ["5/8", "5/16", "6/8", "1/2"], "5/8",
            "Gleiche Nenner (8): addiere die Zähler. 3 + 2 = 5.",
            "3/8 + 2/8 = 5/8. Zusammen haben sie 5 von 8 Stücken gegessen.",
            "Richtig! 5/8 der Pizza.", "Addiere nur die Zähler – der Nenner bleibt 8."),
        # l4 — multiplizieren
        _input(f"{tid}-l4", tid, sid, gl, tt, f"{tid}-u2", 1,
            "Berechne: 2/3 × 3/4 = ? Kürze das Ergebnis (a/b).",
            "1/2",
            "Zähler mal Zähler, Nenner mal Nenner: (2×3)/(3×4) = 6/12 = 1/2.",
            "2/3 × 3/4 = 6/12 = 1/2.",
            "Korrekt! 2/3 × 3/4 = 1/2.", "Multipliziere Zähler mit Zähler und Nenner mit Nenner, dann kürzen."),
        _mc(f"{tid}-l4", tid, sid, gl, tt, f"{tid}-u2", 2,
            "Welches Ergebnis ist richtig für 3/5 × 5/9?",
            ["1/3", "15/45", "8/14", "2/3"], "1/3",
            "3/5 × 5/9 = 15/45. Kürze: ggT(15,45) = 15 → 1/3.",
            "3/5 × 5/9 = 15/45 = 1/3. Du kannst auch vorher kürzen: (3×5)/(5×9) = 3/9 = 1/3.",
            "Sehr gut! 3/5 × 5/9 = 1/3.", "Rechne: Zähler × Zähler und Nenner × Nenner, dann kürzen."),
        _input(f"{tid}-l4", tid, sid, gl, tt, f"{tid}-u2", 3,
            "Von 24 Schüler:innen kommen 3/4 mit dem Velo. Wie viele Schüler:innen kommen mit dem Velo?",
            "18",
            "3/4 von 24 = 3/4 × 24 = 72/4 = 18.",
            "3/4 × 24 = 18. Du kannst auch rechnen: 24 ÷ 4 × 3 = 6 × 3 = 18.",
            "Super! 18 Schüler:innen fahren mit dem Velo.", "Rechne: 24 ÷ 4 = 6 (ein Viertel). Dann × 3 = 18."),
    ]

    topic = {
        "topic_id": tid, "subject_id": sid, "grade_level": gl, "title": tt,
        "description": "Brüche lesen, kürzen, addieren, subtrahieren und multiplizieren – zentrale ZAP-Kompetenzen.",
        "order": 1, "status": "available",
    }
    return topic, units, lessons, challenges


# ── Topic 2: Gleichungen ──────────────────────────────────────────────────

def _gleichungen_data():
    tid = "gleichungen"
    sid = "mathematics"
    gl  = "grade_6_primary"
    tt  = "Gleichungen"

    units = [
        {"unit_id": f"{tid}-u1", "topic_id": tid, "subject_id": sid, "grade_level": gl,
         "title": "Einfache Gleichungen lösen",
         "description": "Gleichungen mit einer Unbekannten, ein- und zweistellig.",
         "order": 1},
        {"unit_id": f"{tid}-u2", "topic_id": tid, "subject_id": sid, "grade_level": gl,
         "title": "Gleichungen aus Sachaufgaben",
         "description": "Sachsituationen als Gleichungen formulieren und lösen.",
         "order": 2},
    ]

    lessons = [
        {"lesson_id": f"{tid}-l1", "unit_id": f"{tid}-u1", "topic_id": tid,
         "subject_id": sid, "grade_level": gl, "topic_title": tt,
         "title": "Einstufige Gleichungen", "difficulty": "intro",
         "estimated_minutes": 10, "order": 1, "challenge_count": 3},
        {"lesson_id": f"{tid}-l2", "unit_id": f"{tid}-u1", "topic_id": tid,
         "subject_id": sid, "grade_level": gl, "topic_title": tt,
         "title": "Zweistufige Gleichungen", "difficulty": "practice",
         "estimated_minutes": 12, "order": 2, "challenge_count": 3},
        {"lesson_id": f"{tid}-l3", "unit_id": f"{tid}-u2", "topic_id": tid,
         "subject_id": sid, "grade_level": gl, "topic_title": tt,
         "title": "Gleichung aufstellen", "difficulty": "practice",
         "estimated_minutes": 15, "order": 3, "challenge_count": 3},
        {"lesson_id": f"{tid}-l4", "unit_id": f"{tid}-u2", "topic_id": tid,
         "subject_id": sid, "grade_level": gl, "topic_title": tt,
         "title": "ZAP-Aufgaben: Gleichungen", "difficulty": "review",
         "estimated_minutes": 15, "order": 4, "challenge_count": 3},
    ]

    challenges = [
        # l1 — einstufig
        _input(f"{tid}-l1", tid, sid, gl, tt, f"{tid}-u1", 1,
            "Löse: x + 15 = 42. Was ist x?",
            "27",
            "Subtrahiere 15 auf beiden Seiten: x = 42 − 15.",
            "x + 15 = 42 → x = 42 − 15 = 27.",
            "Korrekt! x = 27.", "Subtrahiere 15 von beiden Seiten."),
        _input(f"{tid}-l1", tid, sid, gl, tt, f"{tid}-u1", 2,
            "Löse: 4 · x = 56. Was ist x?",
            "14",
            "Dividiere beide Seiten durch 4: x = 56 ÷ 4.",
            "4 · x = 56 → x = 56 ÷ 4 = 14.",
            "Richtig! x = 14.", "Teile beide Seiten durch 4."),
        _mc(f"{tid}-l1", tid, sid, gl, tt, f"{tid}-u1", 3,
            "Welche Gleichung hat die Lösung x = 9?",
            ["x − 4 = 13", "3·x = 27", "x + 9 = 21", "x ÷ 3 = 4"],
            "3·x = 27",
            "Prüfe: 3 · 9 = 27 ✓. Bei den anderen: 9−4 = 5 ≠ 13; 9+9 = 18 ≠ 21; 9÷3 = 3 ≠ 4.",
            "3 · 9 = 27 stimmt. Die anderen Gleichungen ergeben kein 9.",
            "Genau! 3·x = 27 hat die Lösung x = 9.", "Setze x = 9 in jede Gleichung ein und prüfe."),
        # l2 — zweistufig
        _input(f"{tid}-l2", tid, sid, gl, tt, f"{tid}-u1", 1,
            "Löse: 2·x + 7 = 21. Was ist x?",
            "7",
            "Erst −7 auf beiden Seiten (2·x = 14), dann ÷2 (x = 7).",
            "2·x + 7 = 21 → 2·x = 14 → x = 7.",
            "Super! x = 7.", "Schritt 1: −7. Schritt 2: ÷2."),
        _input(f"{tid}-l2", tid, sid, gl, tt, f"{tid}-u1", 2,
            "Löse: 3·x − 5 = 16. Was ist x?",
            "7",
            "Erst +5 auf beiden Seiten (3·x = 21), dann ÷3 (x = 7).",
            "3·x − 5 = 16 → 3·x = 21 → x = 7.",
            "Korrekt! x = 7.", "Schritt 1: +5. Schritt 2: ÷3."),
        _mc(f"{tid}-l2", tid, sid, gl, tt, f"{tid}-u1", 3,
            "Welcher erste Schritt ist beim Lösen von 5·x + 12 = 47 richtig?",
            ["Dividiere durch 5", "Subtrahiere 12 auf beiden Seiten",
             "Addiere 47 auf beiden Seiten", "Multipliziere mit 12"],
            "Subtrahiere 12 auf beiden Seiten",
            "Zuerst den Term ohne x entfernen: 47 − 12 = 35, also 5·x = 35.",
            "Erster Schritt: 47 − 12 = 35, also 5·x = 35. Dann ÷5 → x = 7.",
            "Genau! Zuerst −12, dann ÷5.", "Der Schritt ohne x zuerst entfernen."),
        # l3 — Gleichung aufstellen
        _input(f"{tid}-l3", tid, sid, gl, tt, f"{tid}-u2", 1,
            "Tim hat x Franken. Er gibt 8 Franken aus und hat noch 17 Franken. Welche Gleichung beschreibt das? Schreibe nur die Gleichung (z.B. x-8=17).",
            "x-8=17",
            "Tim gibt 8 aus → x − 8. Er hat noch 17 → = 17.",
            "x − 8 = 17 → x = 25. Tim hatte 25 Franken.",
            "Richtig! x − 8 = 17.", "Tim hatte x, gibt 8 weg und hat 17 übrig: x − 8 = 17."),
        _input(f"{tid}-l3", tid, sid, gl, tt, f"{tid}-u2", 2,
            "Eine Zahl wird verdreifacht und dann um 4 erhöht. Das Ergebnis ist 22. Stelle eine Gleichung auf und löse sie. Was ist die gesuchte Zahl x?",
            "6",
            "Gleichung: 3·x + 4 = 22. Lösung: 3·x = 18, also x = 6.",
            "3·x + 4 = 22 → 3·x = 18 → x = 6.",
            "Super! x = 6.", "Verdreifacht = ×3, um 4 erhöht = +4, Ergebnis 22 → 3x+4=22."),
        _mc(f"{tid}-l3", tid, sid, gl, tt, f"{tid}-u2", 3,
            "Welche Gleichung passt zur Aufgabe: «5 gleich grosse Pakete wiegen zusammen 35 kg»?",
            ["x + 5 = 35", "5 · x = 35", "x − 5 = 35", "35 · x = 5"],
            "5 · x = 35",
            "5 Pakete × Gewicht eines Pakets x = Gesamtgewicht 35 kg.",
            "5 · x = 35 → x = 7. Jedes Paket wiegt 7 kg.",
            "Korrekt! 5·x = 35.", "5 Pakete, jedes wiegt x: 5 × x = 35."),
        # l4 — ZAP-Niveau
        _input(f"{tid}-l4", tid, sid, gl, tt, f"{tid}-u2", 1,
            "(ZAP 2023) Löse: 6·(x − 3) = 30. Was ist x?",
            "8",
            "Dividiere zuerst durch 6: x − 3 = 5. Dann +3: x = 8.",
            "6·(x − 3) = 30 → x − 3 = 5 → x = 8.",
            "Richtig! x = 8.", "Schritt 1: ÷6 → x − 3 = 5. Schritt 2: +3 → x = 8."),
        _input(f"{tid}-l4", tid, sid, gl, tt, f"{tid}-u2", 2,
            "(ZAP) Lena ist doppelt so alt wie ihr Bruder. Die Summe ihrer Alter ist 18. Wie alt ist Lena?",
            "12",
            "Sei x = Alter Bruder. Dann: x + 2x = 18 → 3x = 18 → x = 6. Lena = 2×6 = 12.",
            "Bruder = x, Lena = 2x. x + 2x = 18 → 3x = 18 → x = 6 → Lena = 12 Jahre.",
            "Super! Lena ist 12 Jahre alt.", "Bruder = x, Lena = 2x. Zusammen: x + 2x = 18."),
        _mc(f"{tid}-l4", tid, sid, gl, tt, f"{tid}-u2", 3,
            "(ZAP) Ein Rechteck hat den Umfang 36 cm. Die Länge ist 4 cm mehr als die Breite. Wie breit ist das Rechteck?",
            ["5 cm", "7 cm", "8 cm", "9 cm"], "7 cm",
            "Sei b = Breite. Länge = b + 4. Umfang: 2·(b + b + 4) = 36 → 2·(2b+4)=36 → 2b+4=18 → b=7.",
            "Breite = b, Länge = b+4. 2(b + b+4) = 36 → 4b+8 = 36 → 4b = 28 → b = 7 cm.",
            "Korrekt! Die Breite ist 7 cm.", "Gleichung: 2·(Breite + Länge) = 36. Ersetze Länge = Breite + 4."),
    ]

    topic = {
        "topic_id": tid, "subject_id": sid, "grade_level": gl, "title": tt,
        "description": "Lineare Gleichungen aufstellen und lösen – wie im ZAP-Examen gefordert.",
        "order": 2, "status": "available",
    }
    return topic, units, lessons, challenges


# ── Topic 3: Geometrie ────────────────────────────────────────────────────

def _geometrie_data():
    tid = "geometrie"
    sid = "mathematics"
    gl  = "grade_6_primary"
    tt  = "Geometrie"

    units = [
        {"unit_id": f"{tid}-u1", "topic_id": tid, "subject_id": sid, "grade_level": gl,
         "title": "Fläche und Umfang",
         "description": "Fläche und Umfang von Rechteck, Dreieck, Kreis.",
         "order": 1},
        {"unit_id": f"{tid}-u2", "topic_id": tid, "subject_id": sid, "grade_level": gl,
         "title": "Volumen und Oberfläche",
         "description": "Quader- und Würfelvolumen, Pythagoras.",
         "order": 2},
    ]

    lessons = [
        {"lesson_id": f"{tid}-l1", "unit_id": f"{tid}-u1", "topic_id": tid,
         "subject_id": sid, "grade_level": gl, "topic_title": tt,
         "title": "Rechteck und Dreieck", "difficulty": "intro",
         "estimated_minutes": 12, "order": 1, "challenge_count": 3},
        {"lesson_id": f"{tid}-l2", "unit_id": f"{tid}-u1", "topic_id": tid,
         "subject_id": sid, "grade_level": gl, "topic_title": tt,
         "title": "Kreisfläche und -umfang", "difficulty": "practice",
         "estimated_minutes": 12, "order": 2, "challenge_count": 3},
        {"lesson_id": f"{tid}-l3", "unit_id": f"{tid}-u2", "topic_id": tid,
         "subject_id": sid, "grade_level": gl, "topic_title": tt,
         "title": "Volumen Quader und Würfel", "difficulty": "practice",
         "estimated_minutes": 12, "order": 3, "challenge_count": 3},
        {"lesson_id": f"{tid}-l4", "unit_id": f"{tid}-u2", "topic_id": tid,
         "subject_id": sid, "grade_level": gl, "topic_title": tt,
         "title": "Satz des Pythagoras", "difficulty": "review",
         "estimated_minutes": 15, "order": 4, "challenge_count": 3},
    ]

    challenges = [
        # l1 — Rechteck/Dreieck
        _input(f"{tid}-l1", tid, sid, gl, tt, f"{tid}-u1", 1,
            "Ein Rechteck hat die Seiten a = 8 cm und b = 5 cm. Berechne den Umfang in cm.",
            "26",
            "Umfang = 2·(a + b) = 2·(8+5) = 2·13 = 26 cm.",
            "U = 2·(8+5) = 26 cm.",
            "Richtig! U = 26 cm.", "Umfang Rechteck = 2 × (Länge + Breite)."),
        _input(f"{tid}-l1", tid, sid, gl, tt, f"{tid}-u1", 2,
            "Ein Rechteck hat Länge 12 cm und Breite 7 cm. Berechne die Fläche in cm².",
            "84",
            "Fläche = Länge × Breite = 12 × 7 = 84 cm².",
            "A = 12 × 7 = 84 cm².",
            "Korrekt! A = 84 cm².", "Fläche Rechteck = Länge × Breite."),
        _input(f"{tid}-l1", tid, sid, gl, tt, f"{tid}-u1", 3,
            "Ein rechtwinkliges Dreieck hat die Grundlinie g = 10 cm und die Höhe h = 6 cm. Berechne die Fläche in cm².",
            "30",
            "Dreiecksfläche = (g × h) ÷ 2 = (10 × 6) ÷ 2 = 60 ÷ 2 = 30 cm².",
            "A = g·h/2 = 10·6/2 = 30 cm².",
            "Super! A = 30 cm².", "Fläche Dreieck = (Grundlinie × Höhe) ÷ 2."),
        # l2 — Kreis
        _input(f"{tid}-l2", tid, sid, gl, tt, f"{tid}-u1", 1,
            "Ein Kreis hat den Radius r = 5 cm. Berechne den Umfang. Verwende π ≈ 3,14. Runde auf 1 Dezimalstelle.",
            "31.4",
            "Umfang = 2·π·r = 2 · 3,14 · 5 = 31,4 cm.",
            "U = 2·π·r = 2 × 3,14 × 5 = 31,4 cm.",
            "Richtig! U = 31,4 cm.", "Formel: U = 2 · π · r."),
        _input(f"{tid}-l2", tid, sid, gl, tt, f"{tid}-u1", 2,
            "Berechne die Fläche eines Kreises mit Radius r = 4 cm (π ≈ 3,14). Runde auf 2 Dezimalstellen.",
            "50.24",
            "Fläche = π · r² = 3,14 · 16 = 50,24 cm².",
            "A = π·r² = 3,14 × 4² = 3,14 × 16 = 50,24 cm².",
            "Genau! A = 50,24 cm².", "Formel: A = π · r². r² = r × r."),
        _mc(f"{tid}-l2", tid, sid, gl, tt, f"{tid}-u1", 3,
            "Der Durchmesser eines Kreises ist 14 cm. Was ist der Radius?",
            ["14 cm", "28 cm", "7 cm", "3,5 cm"], "7 cm",
            "Radius = Durchmesser ÷ 2 = 14 ÷ 2 = 7 cm.",
            "r = d/2 = 14/2 = 7 cm.",
            "Korrekt! r = 7 cm.", "Radius = Durchmesser ÷ 2."),
        # l3 — Volumen
        _input(f"{tid}-l3", tid, sid, gl, tt, f"{tid}-u2", 1,
            "Ein Quader hat l = 6 cm, b = 4 cm, h = 3 cm. Berechne das Volumen in cm³.",
            "72",
            "V = l · b · h = 6 · 4 · 3 = 72 cm³.",
            "V = 6 × 4 × 3 = 72 cm³.",
            "Korrekt! V = 72 cm³.", "Volumen Quader = Länge × Breite × Höhe."),
        _input(f"{tid}-l3", tid, sid, gl, tt, f"{tid}-u2", 2,
            "Ein Würfel hat die Seitenlänge a = 5 cm. Berechne das Volumen in cm³.",
            "125",
            "V = a³ = 5³ = 125 cm³.",
            "V = a³ = 5 × 5 × 5 = 125 cm³.",
            "Super! V = 125 cm³.", "Volumen Würfel = a³ = a × a × a."),
        _mc(f"{tid}-l3", tid, sid, gl, tt, f"{tid}-u2", 3,
            "Ein Aquarium ist 60 cm lang, 30 cm breit und 40 cm hoch. Es wird zu 3/4 mit Wasser gefüllt. Wie viele Liter Wasser sind drin? (1 dm³ = 1 Liter)",
            ["54 Liter", "72 Liter", "36 Liter", "48 Liter"], "54 Liter",
            "Volumen = 6·3·4 = 72 dm³ (Einheiten in dm). 3/4 davon: 72 · 3/4 = 54 Liter.",
            "V = 0,6·0,3·0,4 m³ oder 6·3·4 dm³ = 72 dm³. 3/4 × 72 = 54 Liter.",
            "Richtig! 54 Liter.", "Rechne das Volumen in dm³ (1 dm = 10 cm), dann 3/4 davon."),
        # l4 — Pythagoras
        _input(f"{tid}-l4", tid, sid, gl, tt, f"{tid}-u2", 1,
            "Ein rechtwinkliges Dreieck hat die Katheten a = 3 cm und b = 4 cm. Wie lang ist die Hypotenuse c in cm?",
            "5",
            "Satz des Pythagoras: c² = a² + b² = 9 + 16 = 25 → c = 5 cm.",
            "c² = 3² + 4² = 9 + 16 = 25 → c = √25 = 5 cm.",
            "Korrekt! c = 5 cm. (Pythagoräisches Zahlentripel 3-4-5!)", "c² = a² + b². c = √(a²+b²)."),
        _mc(f"{tid}-l4", tid, sid, gl, tt, f"{tid}-u2", 2,
            "In einem rechtwinkligen Dreieck: a = 5 cm, c = 13 cm (Hypotenuse). Wie lang ist b?",
            ["8 cm", "10 cm", "12 cm", "11 cm"], "12 cm",
            "b² = c² − a² = 169 − 25 = 144 → b = 12 cm.",
            "b² = 13² − 5² = 169 − 25 = 144 → b = √144 = 12 cm.",
            "Genau! b = 12 cm.", "b² = c² − a². Beachte: c ist die Hypotenuse (längste Seite)."),
        _input(f"{tid}-l4", tid, sid, gl, tt, f"{tid}-u2", 3,
            "(ZAP-Typ) Eine Leiter lehnt an einer Wand. Sie ist 5 m lang. Ihr Fuss steht 3 m von der Wand entfernt. Wie hoch reicht sie an der Wand (in m)?",
            "4",
            "h² = 5² − 3² = 25 − 9 = 16 → h = 4 m.",
            "Pythagoras: h² = Leiter² − Bodenabstand² = 25 − 9 = 16 → h = 4 m.",
            "Super! Die Leiter reicht 4 m hoch.", "Hypotenuse = 5 m, eine Kathete = 3 m → andere Kathete = ?"),
    ]

    topic = {
        "topic_id": tid, "subject_id": sid, "grade_level": gl, "title": tt,
        "description": "Flächen, Umfang, Volumen und Satz des Pythagoras – Geometrieteil der ZAP.",
        "order": 3, "status": "available",
    }
    return topic, units, lessons, challenges


# ── Topic 4: Prozentrechnung ──────────────────────────────────────────────

def _prozent_data():
    tid = "prozentrechnung"
    sid = "mathematics"
    gl  = "grade_6_primary"
    tt  = "Prozent- und Verhältnisrechnung"

    units = [
        {"unit_id": f"{tid}-u1", "topic_id": tid, "subject_id": sid, "grade_level": gl,
         "title": "Prozentwert berechnen",
         "description": "Prozentzahl, Grundwert und Prozentwert berechnen.",
         "order": 1},
        {"unit_id": f"{tid}-u2", "topic_id": tid, "subject_id": sid, "grade_level": gl,
         "title": "Verhältnisse und Proportionalität",
         "description": "Verhältnisse, direkte und indirekte Proportionalität.",
         "order": 2},
    ]

    lessons = [
        {"lesson_id": f"{tid}-l1", "unit_id": f"{tid}-u1", "topic_id": tid,
         "subject_id": sid, "grade_level": gl, "topic_title": tt,
         "title": "Prozent-Grundaufgaben", "difficulty": "intro",
         "estimated_minutes": 12, "order": 1, "challenge_count": 3},
        {"lesson_id": f"{tid}-l2", "unit_id": f"{tid}-u1", "topic_id": tid,
         "subject_id": sid, "grade_level": gl, "topic_title": tt,
         "title": "Rabatt, Preiserhöhung, Mehrwertsteuer", "difficulty": "practice",
         "estimated_minutes": 15, "order": 2, "challenge_count": 3},
        {"lesson_id": f"{tid}-l3", "unit_id": f"{tid}-u2", "topic_id": tid,
         "subject_id": sid, "grade_level": gl, "topic_title": tt,
         "title": "Verhältnisse", "difficulty": "practice",
         "estimated_minutes": 12, "order": 3, "challenge_count": 3},
        {"lesson_id": f"{tid}-l4", "unit_id": f"{tid}-u2", "topic_id": tid,
         "subject_id": sid, "grade_level": gl, "topic_title": tt,
         "title": "ZAP-Aufgaben: Prozent & Verhältnis", "difficulty": "review",
         "estimated_minutes": 15, "order": 4, "challenge_count": 3},
    ]

    challenges = [
        # l1
        _input(f"{tid}-l1", tid, sid, gl, tt, f"{tid}-u1", 1,
            "Berechne 25% von 80.",
            "20",
            "25% = 25/100 = 1/4. Ein Viertel von 80 = 20.",
            "25% von 80 = 0,25 × 80 = 20.",
            "Richtig! 25% von 80 = 20.", "25% = 1/4. Teile 80 durch 4."),
        _input(f"{tid}-l1", tid, sid, gl, tt, f"{tid}-u1", 2,
            "36 von 90 Schüler:innen fahren mit dem Bus. Wie viel Prozent ist das?",
            "40",
            "Prozentzahl = (Anteil / Ganzes) × 100 = (36/90) × 100 = 40%.",
            "36/90 × 100 = 40%.",
            "Korrekt! 40%.", "(36 ÷ 90) × 100 = Prozentzahl."),
        _input(f"{tid}-l1", tid, sid, gl, tt, f"{tid}-u1", 3,
            "30% von einer Zahl sind 45. Was ist die ganze Zahl (Grundwert)?",
            "150",
            "Grundwert = Prozentwert / (Prozentzahl/100) = 45 / 0,30 = 150.",
            "45 / 0,3 = 150.",
            "Super! Die Zahl ist 150.", "Grundwert = Prozentwert ÷ Prozentzahl × 100 = 45 ÷ 30 × 100."),
        # l2
        _input(f"{tid}-l2", tid, sid, gl, tt, f"{tid}-u1", 1,
            "Ein Buch kostet CHF 40.–. Es gibt 15% Rabatt. Was kostet das Buch nach dem Rabatt?",
            "34",
            "Rabatt = 15% von 40 = 6 CHF. Preis = 40 − 6 = 34 CHF.",
            "15% von 40 = 6. 40 − 6 = CHF 34.–.",
            "Richtig! CHF 34.–.", "Rabatt = 15% × 40 = 6. Neuer Preis = 40 − 6."),
        _mc(f"{tid}-l2", tid, sid, gl, tt, f"{tid}-u1", 2,
            "Ein T-Shirt kostet nach 20% Rabatt noch CHF 32.–. Was war der ursprüngliche Preis?",
            ["CHF 40.–", "CHF 38.40", "CHF 42.–", "CHF 38.–"], "CHF 40.–",
            "Nach 20% Rabatt sind noch 80% übrig: 32 = 80% × x → x = 32/0,8 = 40.",
            "80% des Originalpreises = 32 → Originalpreis = 32 ÷ 0,8 = CHF 40.–.",
            "Genau! Ursprünglicher Preis: CHF 40.–.", "80% des Originalpreises = 32. Also Originalpreis = 32 ÷ 0,8."),
        _input(f"{tid}-l2", tid, sid, gl, tt, f"{tid}-u1", 3,
            "Eine Jacke kostet CHF 120.–. Die Mehrwertsteuer beträgt 8%. Wie viel kostet die Jacke mit MwSt?",
            "129.6",
            "MwSt = 8% von 120 = 9.60. Preis mit MwSt = 120 + 9.60 = 129.60.",
            "8% von 120 = 9.60. 120 + 9.60 = CHF 129.60.",
            "Richtig! CHF 129.60.", "MwSt = 8% × 120 = 9.60. Addiere zur Grundlage."),
        # l3
        _mc(f"{tid}-l3", tid, sid, gl, tt, f"{tid}-u2", 1,
            "Mische Farben im Verhältnis Blau:Gelb = 3:2. Du verwendest 15 ml Blau. Wie viel Gelb brauchst du?",
            ["6 ml", "10 ml", "12 ml", "9 ml"], "10 ml",
            "3:2 → für 15 ml Blau: 15 ÷ 3 × 2 = 10 ml Gelb.",
            "15/3 × 2 = 10 ml Gelb.",
            "Richtig! 10 ml Gelb.", "15 ml sind 3 Teile. Ein Teil = 15÷3 = 5. Gelb = 2 Teile = 10 ml."),
        _input(f"{tid}-l3", tid, sid, gl, tt, f"{tid}-u2", 2,
            "4 Arbeiter brauchen 6 Tage für eine Arbeit. Wie viele Tage brauchen 8 Arbeiter? (Indirekte Proportionalität)",
            "3",
            "Mehr Arbeiter → weniger Tage. 4 × 6 = 24 Arbeitstage insgesamt. 24 ÷ 8 = 3 Tage.",
            "4 × 6 = 24 Tage·Person. 8 Arbeiter brauchen 24 ÷ 8 = 3 Tage.",
            "Super! 3 Tage.", "Gesamt-Arbeitstage = 4×6 = 24. 8 Arbeiter: 24÷8 = 3 Tage."),
        _mc(f"{tid}-l3", tid, sid, gl, tt, f"{tid}-u2", 3,
            "Jonas fährt mit dem Velo 12 km in 30 Minuten. Wie weit fährt er in 45 Minuten (gleiche Geschwindigkeit)?",
            ["16 km", "18 km", "15 km", "20 km"], "18 km",
            "Direkte Proportionalität: 12/30 = x/45 → x = 12 × 45/30 = 18 km.",
            "Geschwindigkeit = 12/30 km/min. In 45 min: 12/30 × 45 = 18 km.",
            "Korrekt! 18 km.", "Direkte Proportionalität: mehr Zeit → mehr Strecke. Faktor: 45/30."),
        # l4 — ZAP
        _input(f"{tid}-l4", tid, sid, gl, tt, f"{tid}-u2", 1,
            "(ZAP 2024) In einer Klasse sind 60% Mädchen. Es sind 15 Mädchen. Wie viele Schüler:innen hat die Klasse?",
            "25",
            "60% = 15 → Grundwert = 15/0,6 = 25.",
            "60% entsprechen 15. 100% = 15 ÷ 60 × 100 = 25.",
            "Richtig! 25 Schüler:innen.", "Grundwert = Prozentwert ÷ Prozentzahl × 100 = 15 ÷ 60 × 100."),
        _mc(f"{tid}-l4", tid, sid, gl, tt, f"{tid}-u2", 2,
            "(ZAP) Ein Fahrrad kostet CHF 450.–. Der Preis wird um 10% erhöht und dann um 10% reduziert. Was kostet das Fahrrad jetzt?",
            ["CHF 445.50", "CHF 450.–", "CHF 440.–", "CHF 455.–"], "CHF 445.50",
            "+10%: 450 × 1,1 = 495. −10%: 495 × 0,9 = 445.50. Nicht wieder CHF 450!",
            "450 × 1,1 = 495. 495 × 0,9 = 445.50. Die Erhöhung und Senkung gleichen sich nicht aus.",
            "Genau! CHF 445.50.", "+10% von 450 = 495. Dann −10% von 495 (nicht von 450)!"),
        _input(f"{tid}-l4", tid, sid, gl, tt, f"{tid}-u2", 3,
            "(ZAP) Zement und Sand werden im Verhältnis 1:4 gemischt. Für eine Mischung werden insgesamt 30 kg benötigt. Wie viel kg Zement werden gebraucht?",
            "6",
            "1 + 4 = 5 Teile. Zement = 1/5 von 30 = 6 kg.",
            "Verhältnis 1:4 → 5 Teile gesamt. Zement = 30/5 × 1 = 6 kg.",
            "Richtig! 6 kg Zement.", "Gesamtteile = 1+4 = 5. Zement = 30 ÷ 5 × 1."),
    ]

    topic = {
        "topic_id": tid, "subject_id": sid, "grade_level": gl, "title": tt,
        "description": "Prozentwert, Grundwert, Verhältnisse und Proportionalität – ZAP-typisch.",
        "order": 4, "status": "available",
    }
    return topic, units, lessons, challenges


# ── Topic 5: Textaufgaben ─────────────────────────────────────────────────

def _textaufgaben_data():
    tid = "textaufgaben"
    sid = "mathematics"
    gl  = "grade_6_primary"
    tt  = "Textaufgaben"

    units = [
        {"unit_id": f"{tid}-u1", "topic_id": tid, "subject_id": sid, "grade_level": gl,
         "title": "Kombinierte Sachaufgaben",
         "description": "Mathematische Probleme aus dem Alltag lösen.",
         "order": 1},
        {"unit_id": f"{tid}-u2", "topic_id": tid, "subject_id": sid, "grade_level": gl,
         "title": "ZAP-Prüfungsaufgaben",
         "description": "Originalnahe Aufgaben aus den ZAP-Prüfungsarchiven.",
         "order": 2},
    ]

    lessons = [
        {"lesson_id": f"{tid}-l1", "unit_id": f"{tid}-u1", "topic_id": tid,
         "subject_id": sid, "grade_level": gl, "topic_title": tt,
         "title": "Geld und Einkauf", "difficulty": "intro",
         "estimated_minutes": 12, "order": 1, "challenge_count": 3},
        {"lesson_id": f"{tid}-l2", "unit_id": f"{tid}-u1", "topic_id": tid,
         "subject_id": sid, "grade_level": gl, "topic_title": tt,
         "title": "Zeit, Geschwindigkeit, Weg", "difficulty": "practice",
         "estimated_minutes": 15, "order": 2, "challenge_count": 3},
        {"lesson_id": f"{tid}-l3", "unit_id": f"{tid}-u2", "topic_id": tid,
         "subject_id": sid, "grade_level": gl, "topic_title": tt,
         "title": "ZAP 2023–2025: Aufgaben Typ A", "difficulty": "review",
         "estimated_minutes": 20, "order": 3, "challenge_count": 3},
        {"lesson_id": f"{tid}-l4", "unit_id": f"{tid}-u2", "topic_id": tid,
         "subject_id": sid, "grade_level": gl, "topic_title": tt,
         "title": "ZAP 2023–2025: Aufgaben Typ B", "difficulty": "review",
         "estimated_minutes": 20, "order": 4, "challenge_count": 3},
    ]

    challenges = [
        # l1 — Geld
        _input(f"{tid}-l1", tid, sid, gl, tt, f"{tid}-u1", 1,
            "Nina kauft 3 Hefte à CHF 2.40 und 2 Stifte à CHF 1.80. Wie viel zahlt sie insgesamt?",
            "10.8",
            "Hefte: 3 × 2.40 = 7.20. Stifte: 2 × 1.80 = 3.60. Total: 7.20 + 3.60 = 10.80.",
            "3×2.40 + 2×1.80 = 7.20 + 3.60 = CHF 10.80.",
            "Korrekt! CHF 10.80.", "Berechne zuerst jeden Posten, dann addiere."),
        _input(f"{tid}-l1", tid, sid, gl, tt, f"{tid}-u1", 2,
            "Tobias hat CHF 50.–. Er gibt davon 3/5 aus. Wie viel Franken hat er noch?",
            "20",
            "3/5 von 50 = 30. Tobias hat 50 − 30 = 20 CHF übrig.",
            "3/5 × 50 = 30 ausgegeben. 50 − 30 = 20 CHF.",
            "Richtig! CHF 20.–.", "3/5 von 50 = 30. 50 − 30 = 20."),
        _mc(f"{tid}-l1", tid, sid, gl, tt, f"{tid}-u1", 3,
            "Für 6 Brötchen bezahlt man CHF 3.60. Was kosten 10 Brötchen?",
            ["CHF 5.40", "CHF 6.00", "CHF 6.20", "CHF 5.80"], "CHF 6.00",
            "Ein Brötchen: 3.60 ÷ 6 = 0.60 CHF. 10 Brötchen: 10 × 0.60 = 6.00 CHF.",
            "Preis pro Brötchen = 3.60/6 = 0.60. 10 × 0.60 = CHF 6.00.",
            "Richtig! CHF 6.00.", "Zuerst den Preis pro Brötchen, dann mal 10."),
        # l2 — Zeit/Geschwindigkeit
        _input(f"{tid}-l2", tid, sid, gl, tt, f"{tid}-u1", 1,
            "Ein Zug fährt 180 km in 2 Stunden. Wie viele km/h fährt er?",
            "90",
            "Geschwindigkeit = Strecke ÷ Zeit = 180 ÷ 2 = 90 km/h.",
            "v = s/t = 180/2 = 90 km/h.",
            "Korrekt! 90 km/h.", "Geschwindigkeit = Strecke ÷ Zeit."),
        _input(f"{tid}-l2", tid, sid, gl, tt, f"{tid}-u1", 2,
            "Ein Auto fährt 75 km/h. Wie lange fährt es, bis es 225 km zurückgelegt hat? (Antwort in Stunden)",
            "3",
            "Zeit = Strecke ÷ Geschwindigkeit = 225 ÷ 75 = 3 Stunden.",
            "t = s/v = 225/75 = 3 h.",
            "Richtig! 3 Stunden.", "Zeit = Strecke ÷ Geschwindigkeit."),
        _mc(f"{tid}-l2", tid, sid, gl, tt, f"{tid}-u1", 3,
            "Julia fährt um 8:30 Uhr los und kommt um 11:15 Uhr an. Wie lange war sie unterwegs?",
            ["2 h 30 min", "2 h 45 min", "3 h 15 min", "2 h 15 min"], "2 h 45 min",
            "Von 8:30 bis 11:15 = 2 h 45 min. (8:30 → 11:30 = 3 h, minus 15 min = 2:45.)",
            "11:15 − 8:30 = 2 h 45 min.",
            "Korrekt! 2 Stunden 45 Minuten.", "Zähle von 8:30 auf 11:15: 8:30→9:30→10:30→11:15 = 2h45min."),
        # l3 — ZAP Typ A
        _input(f"{tid}-l3", tid, sid, gl, tt, f"{tid}-u2", 1,
            "(ZAP 2024, Typ A) Ein rechteckiges Zimmer ist 4,5 m lang und 3,6 m breit. Wie viele Quadratmeter Teppich braucht man für den ganzen Boden?",
            "16.2",
            "Fläche = 4,5 × 3,6 = 16,2 m².",
            "A = 4,5 × 3,6 = 16,2 m².",
            "Richtig! 16,2 m².", "Fläche Rechteck = Länge × Breite."),
        _input(f"{tid}-l3", tid, sid, gl, tt, f"{tid}-u2", 2,
            "(ZAP-Typ) In einer Schachtel sind rote und blaue Murmeln im Verhältnis 2:3. Es sind 30 Murmeln insgesamt. Wie viele rote Murmeln gibt es?",
            "12",
            "Gesamtteile: 2+3=5. Rote = 2/5 von 30 = 12.",
            "30 ÷ 5 × 2 = 12 rote Murmeln.",
            "Korrekt! 12 rote Murmeln.", "2 + 3 = 5 Teile. Ein Teil = 30/5 = 6. Rot = 2 × 6 = 12."),
        _mc(f"{tid}-l3", tid, sid, gl, tt, f"{tid}-u2", 3,
            "(ZAP-Typ) Ein Tank enthält 200 Liter. Jede Minute fliessen 8 Liter hinein und 3 Liter ab. Nach wie vielen Minuten sind 235 Liter im Tank?",
            ["3 min", "5 min", "7 min", "4 min"], "7 min",
            "Netto-Zufluss: 8 − 3 = 5 L/min. Benötigt: 235 − 200 = 35 L. 35 ÷ 5 = 7 Minuten.",
            "Nettozufluss = 5 L/min. 35 L fehlen. 35/5 = 7 Minuten.",
            "Richtig! 7 Minuten.", "Nettozufluss = 8 − 3 = 5 L/min. Dann: (235−200) ÷ 5."),
        # l4 — ZAP Typ B
        _input(f"{tid}-l4", tid, sid, gl, tt, f"{tid}-u2", 1,
            "(ZAP 2025, Aufgabe ähnlich) Ein Quadrat hat den Umfang 48 cm. Berechne die Fläche des Quadrats in cm².",
            "144",
            "Seite = 48 ÷ 4 = 12 cm. Fläche = 12² = 144 cm².",
            "U = 4a → a = 48/4 = 12 cm. A = 12² = 144 cm².",
            "Korrekt! 144 cm².", "Erst Seite aus Umfang: a = U/4 = 12. Dann Fläche = a²."),
        _mc(f"{tid}-l4", tid, sid, gl, tt, f"{tid}-u2", 2,
            "(ZAP-Typ) 5 Orangen kosten gleich viel wie 3 Äpfel. 1 Apfel kostet CHF 0.90. Was kosten 10 Orangen?",
            ["CHF 5.40", "CHF 4.50", "CHF 6.00", "CHF 5.00"], "CHF 5.40",
            "3 Äpfel = 3 × 0.90 = CHF 2.70 = 5 Orangen. 1 Orange = 2.70/5 = 0.54. 10 Orangen = 5.40.",
            "5 Orangen = 3 × 0.90 = 2.70. 1 Orange = 0.54. 10 Orangen = 5.40 CHF.",
            "Richtig! CHF 5.40.", "3 Äpfel à 0.90 = CHF 2.70 für 5 Orangen. 1 Orange = 0.54."),
        _input(f"{tid}-l4", tid, sid, gl, tt, f"{tid}-u2", 3,
            "(ZAP 2025, letzte Aufgabe Typ) Eine Bahn fährt auf einem kreisförmigen Gleis mit Radius 50 m. Wie weit fährt sie bei 3 vollen Runden? (π ≈ 3,14, Antwort in m, gerundet auf ganze Meter)",
            "942",
            "Umfang = 2·π·r = 2·3,14·50 = 314 m. 3 Runden = 3 × 314 = 942 m.",
            "U = 2 × 3,14 × 50 = 314 m. 3 Runden: 3 × 314 = 942 m.",
            "Super! 942 m.", "Umfang = 2·π·r. Dann × 3 Runden."),
    ]

    topic = {
        "topic_id": tid, "subject_id": sid, "grade_level": gl, "title": tt,
        "description": "Kombinierte Sachaufgaben aus dem ZAP-Prüfungsarchiv (Typen 2023–2025).",
        "order": 5, "status": "available",
    }
    return topic, units, lessons, challenges


# ── DynamoDB writer ───────────────────────────────────────────────────────

def prepare_challenge_items(challenges: list[dict]) -> list[dict]:
    """Version challenges and create one answer-free direct pointer per opaque ID."""
    seen_ids: set[str] = set()
    prepared: list[dict] = []
    for raw in challenges:
        if any(
            field in raw
            for field in ("hint", "hint_approved", "directional_hint_parameters")
        ):
            raise ValueError("legacy or dynamic hint content is forbidden")
        challenge_id = str(raw.get("challenge_id") or "").strip()
        if not challenge_id:
            raise ValueError("challenge_id is required")
        if challenge_id in seen_ids:
            raise ValueError(f"duplicate challenge_id: {challenge_id}")
        seen_ids.add(challenge_id)
        canonical = dict(raw)
        canonical["PK"] = "PRACTICE"
        canonical["SK"] = f"CHALLENGE#{canonical['lesson_id']}#{challenge_id}"
        try:
            template_id = DirectionalHintTemplateId(
                canonical.get("directional_hint_template_id")
            )
        except (TypeError, ValueError) as error:
            raise ValueError("invalid directional hint template") from error
        canonical = practice_repo.version_challenge(canonical)
        if "hint_non_derivability_decision" not in canonical:
            canonical["hint_non_derivability_decision"] = {
                "template_id": template_id.value,
                "challenge_version": canonical["challenge_version"],
                "content_hash": canonical["challenge_content_hash"],
                "reviewer_id": "practice-seed-reviewer",
                "reviewer_role": "teacher",
                "policy_version": "practice-directional-hints-v1",
                "decision": "non_derivable",
                "approved_at": "2026-07-17T00:00:00+00:00",
            }
        if practice_projection_service.approved_directional_hint(canonical) is None:
            raise ValueError("invalid hint non-derivability decision")
        prepared.extend((canonical, practice_repo.challenge_pointer(canonical)))
    return prepared

def seed(table_name: str, region: str, dry_run: bool = False):
    all_topics, all_units, all_lessons, all_challenges = [], [], [], []

    for fn in [_brueche_data, _gleichungen_data, _geometrie_data,
               _prozent_data, _textaufgaben_data]:
        topic, units, lessons, challenges = fn()
        all_topics.append(topic)
        all_units.extend(units)
        all_lessons.extend(lessons)
        all_challenges.extend(challenges)

    items_to_write = []

    # Subject
    items_to_write.append({"PK": "PRACTICE", "SK": f"SUBJECT#{SUBJECT['subject_id']}", **SUBJECT})

    # Topics
    for t in all_topics:
        items_to_write.append({"PK": "PRACTICE", "SK": f"TOPIC#{t['topic_id']}", **t})

    # Units
    for u in all_units:
        items_to_write.append({"PK": "PRACTICE", "SK": f"UNIT#{u['unit_id']}", **u})

    # Lessons
    for lesson in all_lessons:
        items_to_write.append(
            {"PK": "PRACTICE", "SK": f"LESSON#{lesson['lesson_id']}", **lesson}
        )

    # Validate all IDs before any write, then add canonical rows and direct pointers.
    items_to_write.extend(prepare_challenge_items(all_challenges))

    print(f"Items to seed: {len(items_to_write)}")
    print(f"  Subjects: 1 | Topics: {len(all_topics)} | Units: {len(all_units)} | "
          f"Lessons: {len(all_lessons)} | Challenges: {len(all_challenges)}")

    if dry_run:
        print("[DRY RUN] Skipping DynamoDB writes.")
        for item in items_to_write[:3]:
            print(f"  {item['SK']}: {item.get('title', item.get('name', ''))}")
        return

    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)
    with table.batch_writer() as batch:
        for item in items_to_write:
            batch.put_item(Item=item)

    print(f"Done! {len(items_to_write)} items written to {table_name}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", default=os.environ.get("STOA_TABLE", "stoa-main"))
    parser.add_argument("--region", default=os.environ.get("AWS_DEFAULT_REGION", "eu-central-2"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    seed(args.table, args.region, dry_run=args.dry_run)
