"""What the curriculum validation report says about a draft (`stoa.services.curriculum_issues`, #112).

Every reader is staff, addressed formally. The English is the sentence the
report sent before it carried codes, and is still its `message`.
"""

TEXT: dict[str, dict[str, str]] = {
    "curriculum_issue.lesson_field_missing": {
        "de": "Ein Pflichtfeld der Lektion fehlt.",
        "en": "Required lesson field is missing.",
        "fr": "Un champ obligatoire de la leçon manque.",
        "it": "Manca un campo obbligatorio della lezione.",
    },
    "curriculum_issue.unit_missing": {
        "de": "Eine Lektion muss die Einheit nennen, zu der sie gehört.",
        "en": "A lesson must name the unit it belongs to.",
        "fr": "Une leçon doit indiquer l’unité à laquelle elle appartient.",
        "it": "Una lezione deve indicare l’unità a cui appartiene.",
    },
    "curriculum_issue.unit_unknown": {
        "de": "Die genannte Einheit existiert nicht.",
        "en": "The named unit does not exist.",
        "fr": "L’unité indiquée n’existe pas.",
        "it": "L’unità indicata non esiste.",
    },
    "curriculum_issue.topic_not_the_units": {
        "de": "Das Thema muss das Thema der Einheit sein.",
        "en": "The topic must be the unit's topic.",
        "fr": "Le thème doit être celui de l’unité.",
        "it": "L’argomento deve essere quello dell’unità.",
    },
    "curriculum_issue.subject_not_the_units": {
        "de": "Das Fach muss das Fach der Einheit sein.",
        "en": "The subject must be the unit's subject.",
        "fr": "La branche doit être celle de l’unité.",
        "it": "La materia deve essere quella dell’unità.",
    },
    "curriculum_issue.prerequisite_unknown": {
        "de": "Jede Voraussetzung muss eine andere, bestehende Lektion sein.",
        "en": "Every prerequisite must be another existing lesson.",
        "fr": "Chaque prérequis doit être une autre leçon existante.",
        "it": "Ogni prerequisito deve essere un’altra lezione esistente.",
    },
    "curriculum_issue.prerequisite_unrelated": {
        "de": "Eine Voraussetzung muss die Einheit oder das Thema dieser Lektion teilen.",
        "en": "A prerequisite must share this lesson's unit or topic.",
        "fr": "Un prérequis doit partager l’unité ou le thème de cette leçon.",
        "it": "Un prerequisito deve condividere l’unità o l’argomento di questa lezione.",
    },
    "curriculum_issue.prerequisite_cycle": {
        "de": "Die Voraussetzungen dürfen keinen Kreis bilden.",
        "en": "Prerequisites must not close a cycle.",
        "fr": "Les prérequis ne doivent pas former de cycle.",
        "it": "I prerequisiti non devono formare un ciclo.",
    },
    "curriculum_issue.exercise_required": {
        "de": "Mindestens eine Übung ist nötig.",
        "en": "At least one exercise is required.",
        "fr": "Au moins un exercice est requis.",
        "it": "Serve almeno un esercizio.",
    },
    "curriculum_issue.exercise_id_repeated": {
        "de": "Die Übungs-ID kommt in dieser Lektion mehr als einmal vor.",
        "en": "Exercise id is used more than once in this lesson.",
        "fr": "L’identifiant d’exercice est utilisé plus d’une fois dans cette leçon.",
        "it": "L’ID dell’esercizio è usato più di una volta in questa lezione.",
    },
    "curriculum_issue.exercise_field_missing": {
        "de": "Ein Pflichtfeld der Übung fehlt.",
        "en": "Required exercise field is missing.",
        "fr": "Un champ obligatoire de l’exercice manque.",
        "it": "Manca un campo obbligatorio dell’esercizio.",
    },
    "curriculum_issue.options_without_choice": {
        "de": "Nur eine Multiple-Choice-Übung hat Antwortoptionen.",
        "en": "Only a multiple-choice exercise has options.",
        "fr": "Seul un exercice à choix multiple a des options.",
        "it": "Solo un esercizio a scelta multipla ha delle opzioni.",
    },
    "curriculum_issue.too_few_options": {
        "de": "Eine Multiple-Choice-Übung braucht mindestens zwei Optionen.",
        "en": "A multiple-choice exercise needs at least two options.",
        "fr": "Un exercice à choix multiple nécessite au moins deux options.",
        "it": "Un esercizio a scelta multipla richiede almeno due opzioni.",
    },
    "curriculum_issue.options_read_the_same": {
        "de": "Zwei Optionen lauten gleich.",
        "en": "Two options read the same.",
        "fr": "Deux options se lisent de la même façon.",
        "it": "Due opzioni hanno lo stesso testo.",
    },
    "curriculum_issue.answer_not_an_option": {
        "de": "Die Antwort muss eine der Optionen sein.",
        "en": "The answer must be one of the options.",
        "fr": "La réponse doit être l’une des options.",
        "it": "La risposta deve essere una delle opzioni.",
    },
    "curriculum_issue.skills_not_a_list": {
        "de": "Die Kompetenzen müssen eine Liste sein.",
        "en": "Skills must be a list.",
        "fr": "Les compétences doivent être une liste.",
        "it": "Le competenze devono essere un elenco.",
    },
    "curriculum_issue.skill_unknown": {
        "de": "Unbekannte Kompetenz «{skill}».",
        "en": "Unknown skill '{skill}'.",
        "fr": "Compétence inconnue « {skill} ».",
        "it": "Competenza sconosciuta «{skill}».",
    },
    "curriculum_issue.skill_in_another_unit": {
        "de": "Die Kompetenz «{skill}» gehört zur Einheit «{unit}», nicht zu «{lesson_unit}».",
        "en": "Skill '{skill}' belongs to unit '{unit}', not '{lesson_unit}'.",
        "fr": "La compétence « {skill} » appartient à l’unité « {unit} », pas à « {lesson_unit} ».",
        "it": "La competenza «{skill}» appartiene all’unità «{unit}», non a «{lesson_unit}».",
    },
    "curriculum_issue.figure_not_text": {
        "de": "Eine Abbildung muss SVG-Text sein.",
        "en": "A figure must be SVG text.",
        "fr": "Une figure doit être du texte SVG.",
        "it": "Una figura deve essere testo SVG.",
    },
    "curriculum_issue.figure_too_long": {
        "de": "Eine Abbildung hat höchstens {max_length} Zeichen.",
        "en": "A figure is at most {max_length} characters.",
        "fr": "Une figure compte au plus {max_length} caractères.",
        "it": "Una figura ha al massimo {max_length} caratteri.",
    },
    "curriculum_issue.figure_forbidden_markup": {
        "de": "Eine Abbildung darf keinen Dokumenttyp, keine Entität, keine Verarbeitungsanweisung und keine Skript-URL enthalten.",
        "en": "A figure may hold no document type, entity, processing instruction or script URL.",
        "fr": "Une figure ne peut contenir ni type de document, ni entité, ni instruction de traitement, ni URL de script.",
        "it": "Una figura non può contenere tipo di documento, entità, istruzioni di elaborazione o URL di script.",
    },
    "curriculum_issue.figure_malformed": {
        "de": "Eine Abbildung muss wohlgeformtes SVG sein.",
        "en": "A figure must be well-formed SVG.",
        "fr": "Une figure doit être du SVG bien formé.",
        "it": "Una figura deve essere SVG ben formato.",
    },
    "curriculum_issue.figure_root_not_svg": {
        "de": "Das Wurzelelement einer Abbildung muss ein svg-Element im SVG-Namensraum sein.",
        "en": "A figure's root must be an svg element in the SVG namespace.",
        "fr": "La racine d’une figure doit être un élément svg dans l’espace de noms SVG.",
        "it": "La radice di una figura deve essere un elemento svg nello spazio dei nomi SVG.",
    },
    "curriculum_issue.figure_element_not_allowed": {
        "de": "Das Element «{element}» ist in einer Abbildung nicht erlaubt.",
        "en": "Element '{element}' is not allowed in a figure.",
        "fr": "L’élément « {element} » n’est pas autorisé dans une figure.",
        "it": "L’elemento «{element}» non è ammesso in una figura.",
    },
    "curriculum_issue.figure_attribute_not_allowed": {
        "de": "Das Attribut «{attribute}» ist in einer Abbildung nicht erlaubt.",
        "en": "Attribute '{attribute}' is not allowed in a figure.",
        "fr": "L’attribut « {attribute} » n’est pas autorisé dans une figure.",
        "it": "L’attributo «{attribute}» non è ammesso in una figura.",
    },
    "curriculum_issue.figure_reference_outside": {
        "de": "Das Attribut «{attribute}» darf nur auf eine Markierung der Abbildung selbst verweisen.",
        "en": "Attribute '{attribute}' may only refer to a marker of the figure itself.",
        "fr": "L’attribut « {attribute} » ne peut renvoyer qu’à un marqueur de la figure elle-même.",
        "it": "L’attributo «{attribute}» può riferirsi solo a un marcatore della figura stessa.",
    },
    "curriculum_issue.option_figures_mismatch": {
        "de": "Pro Option eine Abbildung, leer, wo eine Option keine hat.",
        "en": "Option figures go one per option, empty where an option has none.",
        "fr": "Une figure par option, vide lorsqu’une option n’en a pas.",
        "it": "Una figura per opzione, vuota dove un’opzione non ne ha.",
    },
    "curriculum_issue.translations_not_a_map": {
        "de": "Übersetzungen müssen einer Sprache ihren Text zuordnen.",
        "en": "Translations must map a locale to its text.",
        "fr": "Les traductions doivent associer une langue à son texte.",
        "it": "Le traduzioni devono associare una lingua al suo testo.",
    },
    "curriculum_issue.translation_locale_unsupported": {
        "de": "Nicht unterstützte Sprache «{language}».",
        "en": "Unsupported locale '{language}'.",
        "fr": "Langue non prise en charge « {language} ».",
        "it": "Lingua non supportata «{language}».",
    },
    "curriculum_issue.translation_prompt_missing": {
        "de": "Eine Übersetzung braucht ihre Aufgabenstellung.",
        "en": "A translation needs its prompt.",
        "fr": "Une traduction a besoin de son énoncé.",
        "it": "Una traduzione ha bisogno della sua consegna.",
    },
    "curriculum_issue.translation_too_long": {
        "de": "Zu lang: {fields}.",
        "en": "Too long: {fields}.",
        "fr": "Trop long : {fields}.",
        "it": "Troppo lungo: {fields}.",
    },
    "curriculum_issue.translation_options_mismatch": {
        "de": "Eine Übersetzung braucht für jede Option eine Option.",
        "en": "A translation needs one option for each option.",
        "fr": "Une traduction nécessite une option pour chaque option.",
        "it": "Una traduzione richiede un’opzione per ogni opzione.",
    },
    "curriculum_issue.translation_answer_not_the_option": {
        "de": "Die übersetzte Antwort muss die übersetzte richtige Option sein.",
        "en": "The translated answer must be the translated right option.",
        "fr": "La réponse traduite doit être la bonne option traduite.",
        "it": "La risposta tradotta deve essere l’opzione corretta tradotta.",
    },
    "curriculum_issue.translation_answer_missing": {
        "de": "Eine Übersetzung braucht ihre Antwort.",
        "en": "A translation needs its answer.",
        "fr": "Une traduction a besoin de sa réponse.",
        "it": "Una traduzione ha bisogno della sua risposta.",
    },
    "curriculum_issue.accepted_answers_out_of_bounds": {
        "de": "Zu viele oder zu lange akzeptierte Antworten.",
        "en": "Too many or too long accepted answers.",
        "fr": "Trop de réponses acceptées, ou des réponses acceptées trop longues.",
        "it": "Troppe risposte accettate, o risposte accettate troppo lunghe.",
    },
}
