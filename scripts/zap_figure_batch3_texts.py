"""What the tasks of batch 3 say, in German, English, French and Italian (#596).

A text never names a right or wrong option itself: `{ok}`, `{no}`, `{c1}` … are
filled in from the computed key (`scripts/zap_figure_batch3.py`), so a text
cannot disagree with it. Swiss German spelling (`ss`), a decimal point in every
language, as in the rest of the question bank.
"""

from __future__ import annotations

LOCALES = ("de", "en", "fr", "it")
_AND = {"de": "und", "en": "and", "fr": "et", "it": "e"}


def listing(items: list[str], locale: str) -> str:
    """`$P$, $Q$ und $R$` in the reader's language."""
    if not items:
        raise ValueError("a text may not list nothing")
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} {_AND[locale]} {items[-1]}"


def finish(text: str, locale: str) -> str:
    """French sets a no-break space before `?`, `!`, `:` and `;`."""
    if locale != "fr":
        return text
    for mark in "?!:;":
        text = text.replace(f" {mark}", f" {mark}")
    return text


#: task key -> locale -> (prompt, explanation)
TEXTS: dict[str, dict[str, tuple[str, str]]] = {
    "rastplaetze": {
        "de": (
            "Die Karte zeigt die Burg $B$, den Hafen $H$, die Kirche $K$ und den Weg $w$. Ein Häuschen ist "
            "100 m breit. Am Weg sind die Rastplätze $P$ bis $U$ markiert. Welche Rastplätze liegen näher "
            "bei der Burg als beim Hafen und höchstens 450 m von der Kirche entfernt? Wähle alle aus.",
            "Näher bei $B$ als bei $H$ liegt ein Punkt, wenn er auf der Seite von $B$ der Mittelsenkrechten "
            "von $BH$ liegt. Das gilt für {c1}.\n"
            "Höchstens 450 m von $K$ entfernt heisst: im Kreis um $K$ mit Radius 4.5 Häuschen. Das gilt "
            "für {c2}.\n"
            "Beide Bedingungen erfüllen nur {ok}.",
        ),
        "en": (
            "The map shows the castle $B$, the harbour $H$, the church $K$ and the path $w$. One square is "
            "100 m wide. The rest areas $P$ to $U$ are marked on the path. Which rest areas are closer to "
            "the castle than to the harbour and at most 450 m from the church? Select all of them.",
            "A point is closer to $B$ than to $H$ when it lies on $B$'s side of the perpendicular bisector "
            "of $BH$. This is true for {c1}.\n"
            "At most 450 m from $K$ means inside the circle around $K$ with a radius of 4.5 squares. This "
            "is true for {c2}.\n"
            "Only {ok} meet both conditions.",
        ),
        "fr": (
            "La carte montre le château $B$, le port $H$, l'église $K$ et le chemin $w$. Un carreau mesure "
            "100 m de côté. Les aires de repos $P$ à $U$ sont marquées sur le chemin. Quelles aires de "
            "repos sont plus proches du château que du port et à 450 m au plus de l'église ? "
            "Sélectionne-les toutes.",
            "Un point est plus proche de $B$ que de $H$ s'il se trouve du côté de $B$ par rapport à la "
            "médiatrice du segment $BH$. C'est le cas de {c1}.\n"
            "À 450 m au plus de $K$ signifie : dans le cercle de centre $K$ et de rayon 4.5 carreaux. "
            "C'est le cas de {c2}.\n"
            "Seuls {ok} remplissent les deux conditions.",
        ),
        "it": (
            "La mappa mostra il castello $B$, il porto $H$, la chiesa $K$ e il sentiero $w$. Un quadretto "
            "è largo 100 m. Sul sentiero sono segnate le aree di sosta da $P$ a $U$. Quali aree di sosta "
            "sono più vicine al castello che al porto e distano al massimo 450 m dalla chiesa? "
            "Selezionale tutte.",
            "Un punto è più vicino a $B$ che a $H$ se si trova dalla parte di $B$ rispetto all'asse del "
            "segmento $BH$. Vale per {c1}.\n"
            "Al massimo 450 m da $K$ significa: dentro il cerchio di centro $K$ e raggio 4.5 quadretti. "
            "Vale per {c2}.\n"
            "Solo {ok} soddisfano entrambe le condizioni.",
        ),
    },
    "zwei-geraden": {
        "de": (
            "Gegeben sind die Geraden $g$ und $h$ und die Punkte $A$ und $B$. Welche der markierten Punkte "
            "$P$ bis $W$ liegen näher bei $A$ als bei $B$ und zugleich näher bei $g$ als bei $h$? Wähle "
            "alle aus.",
            "Näher bei $A$ als bei $B$: auf der Seite von $A$ der Mittelsenkrechten von $AB$. Das gilt für "
            "{c1}.\n"
            "Näher bei $g$ als bei $h$: Der Abstand zu einer Geraden wird senkrecht zu ihr gemessen. Die "
            "Grenze bilden die beiden Winkelhalbierenden von $g$ und $h$. Näher bei $g$ liegen {c2}.\n"
            "Beide Bedingungen erfüllen {ok}.",
        ),
        "en": (
            "The lines $g$ and $h$ and the points $A$ and $B$ are given. Which of the marked points $P$ to "
            "$W$ are closer to $A$ than to $B$ and also closer to $g$ than to $h$? Select all of them.",
            "Closer to $A$ than to $B$: on $A$'s side of the perpendicular bisector of $AB$. This is true "
            "for {c1}.\n"
            "Closer to $g$ than to $h$: the distance to a line is measured at right angles to it. The "
            "boundary is formed by the two angle bisectors of $g$ and $h$. Closer to $g$ are {c2}.\n"
            "{ok} meet both conditions.",
        ),
        "fr": (
            "On donne les droites $g$ et $h$ et les points $A$ et $B$. Lesquels des points marqués $P$ à "
            "$W$ sont plus proches de $A$ que de $B$ et en même temps plus proches de $g$ que de $h$ ? "
            "Sélectionne-les tous.",
            "Plus proche de $A$ que de $B$ : du côté de $A$ par rapport à la médiatrice du segment $AB$. "
            "C'est le cas de {c1}.\n"
            "Plus proche de $g$ que de $h$ : la distance à une droite se mesure perpendiculairement à "
            "elle. La limite est formée par les deux bissectrices de $g$ et $h$. Sont plus proches de $g$ : "
            "{c2}.\n"
            "{ok} remplissent les deux conditions.",
        ),
        "it": (
            "Sono date le rette $g$ e $h$ e i punti $A$ e $B$. Quali dei punti segnati da $P$ a $W$ sono "
            "più vicini ad $A$ che a $B$ e allo stesso tempo più vicini a $g$ che a $h$? Selezionali tutti.",
            "Più vicino ad $A$ che a $B$: dalla parte di $A$ rispetto all'asse del segmento $AB$. Vale per "
            "{c1}.\n"
            "Più vicino a $g$ che a $h$: la distanza da una retta si misura perpendicolarmente ad essa. "
            "Il confine è formato dalle due bisettrici di $g$ e $h$. Sono più vicini a $g$: {c2}.\n"
            "{ok} soddisfano entrambe le condizioni.",
        ),
    },
    "kreis-und-geraden": {
        "de": (
            "Die Geraden $g$ und $h$ schneiden sich; der Punkt $M$ liegt auf $g$. Welche der markierten "
            "Punkte $P$ bis $W$ sind weniger als 5 Häuschen von $M$ entfernt und liegen näher bei $h$ als "
            "bei $g$? Wähle alle aus.",
            "Weniger als 5 Häuschen von $M$ entfernt: im Kreis um $M$ mit Radius 5 Häuschen. Das gilt für "
            "{c1}.\n"
            "Näher bei $h$ als bei $g$: Der Abstand zu einer Geraden wird senkrecht zu ihr gemessen. Die "
            "Grenze bilden die beiden Winkelhalbierenden von $g$ und $h$. Näher bei $h$ liegen {c2}.\n"
            "Beide Bedingungen erfüllen {ok}.",
        ),
        "en": (
            "The lines $g$ and $h$ intersect; the point $M$ lies on $g$. Which of the marked points $P$ to "
            "$W$ are less than 5 squares from $M$ and closer to $h$ than to $g$? Select all of them.",
            "Less than 5 squares from $M$: inside the circle around $M$ with a radius of 5 squares. This "
            "is true for {c1}.\n"
            "Closer to $h$ than to $g$: the distance to a line is measured at right angles to it. The "
            "boundary is formed by the two angle bisectors of $g$ and $h$. Closer to $h$ are {c2}.\n"
            "{ok} meet both conditions.",
        ),
        "fr": (
            "Les droites $g$ et $h$ se coupent ; le point $M$ est sur $g$. Lesquels des points marqués $P$ "
            "à $W$ sont à moins de 5 carreaux de $M$ et plus proches de $h$ que de $g$ ? "
            "Sélectionne-les tous.",
            "À moins de 5 carreaux de $M$ : dans le cercle de centre $M$ et de rayon 5 carreaux. C'est le "
            "cas de {c1}.\n"
            "Plus proche de $h$ que de $g$ : la distance à une droite se mesure perpendiculairement à "
            "elle. La limite est formée par les deux bissectrices de $g$ et $h$. Sont plus proches de $h$ : "
            "{c2}.\n"
            "{ok} remplissent les deux conditions.",
        ),
        "it": (
            "Le rette $g$ e $h$ si intersecano; il punto $M$ sta su $g$. Quali dei punti segnati da $P$ a "
            "$W$ distano meno di 5 quadretti da $M$ e sono più vicini a $h$ che a $g$? Selezionali tutti.",
            "Meno di 5 quadretti da $M$: dentro il cerchio di centro $M$ e raggio 5 quadretti. Vale per "
            "{c1}.\n"
            "Più vicino a $h$ che a $g$: la distanza da una retta si misura perpendicolarmente ad essa. "
            "Il confine è formato dalle due bisettrici di $g$ e $h$. Sono più vicini a $h$: {c2}.\n"
            "{ok} soddisfano entrambe le condizioni.",
        ),
    },
    "koordinaten": {
        "de": (
            "Im Koordinatensystem sind die Punkte $A(3/2)$, $B(9/2)$ und $C(5/7)$ eingezeichnet. Gesucht "
            "sind Punkte, die näher bei $B$ als bei $A$ liegen, von $C$ höchstens 5 Einheiten entfernt "
            "sind und von $B$ mindestens halb so weit entfernt sind, wie die Strecke $AB$ lang ist. Welche "
            "der markierten Punkte $P$ bis $W$ erfüllen alle drei Bedingungen? Wähle alle aus.",
            "Näher bei $B$ als bei $A$: rechts der Mittelsenkrechten von $AB$, also rechts von $x = 6$. Das "
            "gilt für {c1}.\n"
            "Höchstens 5 Einheiten von $C$ entfernt: im Kreis um $C$ mit Radius 5. Das gilt für {c2}.\n"
            "$AB$ ist 6 Einheiten lang, die Hälfte ist 3. Mindestens 3 Einheiten von $B$ entfernt sind "
            "{c3}.\n"
            "Alle drei Bedingungen erfüllen {ok}.",
        ),
        "en": (
            "The points $A(3/2)$, $B(9/2)$ and $C(5/7)$ are drawn in the coordinate system. We are looking "
            "for points that are closer to $B$ than to $A$, at most 5 units from $C$, and at least half "
            "as far from $B$ as the segment $AB$ is long. Which of the marked points $P$ to $W$ meet all "
            "three conditions? Select all of them.",
            "Closer to $B$ than to $A$: to the right of the perpendicular bisector of $AB$, that is, to the "
            "right of $x = 6$. This is true for {c1}.\n"
            "At most 5 units from $C$: inside the circle around $C$ with radius 5. This is true for {c2}.\n"
            "$AB$ is 6 units long, half of it is 3. At least 3 units from $B$ are {c3}.\n"
            "{ok} meet all three conditions.",
        ),
        "fr": (
            "Les points $A(3/2)$, $B(9/2)$ et $C(5/7)$ sont placés dans le repère. On cherche des points "
            "plus proches de $B$ que de $A$, à 5 unités au plus de $C$ et dont la distance à $B$ vaut au "
            "moins la moitié de la longueur du segment $AB$. Lesquels des points marqués $P$ à $W$ "
            "remplissent les trois conditions ? Sélectionne-les tous.",
            "Plus proche de $B$ que de $A$ : à droite de la médiatrice du segment $AB$, donc à droite de "
            "$x = 6$. C'est le cas de {c1}.\n"
            "À 5 unités au plus de $C$ : dans le cercle de centre $C$ et de rayon 5. C'est le cas de {c2}.\n"
            "$AB$ mesure 6 unités, la moitié vaut 3. Sont à 3 unités au moins de $B$ : {c3}.\n"
            "{ok} remplissent les trois conditions.",
        ),
        "it": (
            "Nel piano cartesiano sono segnati i punti $A(3/2)$, $B(9/2)$ e $C(5/7)$. Si cercano punti più "
            "vicini a $B$ che ad $A$, distanti al massimo 5 unità da $C$ e la cui distanza da $B$ è almeno "
            "la metà della lunghezza del segmento $AB$. Quali dei punti segnati da $P$ a $W$ soddisfano "
            "tutte e tre le condizioni? Selezionali tutti.",
            "Più vicino a $B$ che ad $A$: a destra dell'asse del segmento $AB$, cioè a destra di $x = 6$. "
            "Vale per {c1}.\n"
            "Al massimo 5 unità da $C$: dentro il cerchio di centro $C$ e raggio 5. Vale per {c2}.\n"
            "$AB$ è lungo 6 unità, la metà è 3. Distano almeno 3 unità da $B$: {c3}.\n"
            "{ok} soddisfano tutte e tre le condizioni.",
        ),
    },
    "zeltplatz": {
        "de": (
            "Auf der Karte ist ein Häuschen 10 m breit. Ein Zelt soll mindestens 25 m vom Bach $b$ "
            "entfernt stehen, höchstens 40 m von der Feuerstelle $F$ und näher beim Brunnen $A$ als beim "
            "Parkplatz $B$. Welche der markierten Plätze $P$ bis $W$ erfüllen alle drei Bedingungen? "
            "Wähle alle aus.",
            "Mindestens 25 m vom Bach: oberhalb der Parallele zu $b$ im Abstand von 2.5 Häuschen. Das gilt "
            "für {c1}.\n"
            "Höchstens 40 m von $F$: im Kreis um $F$ mit Radius 4 Häuschen. Das gilt für {c2}.\n"
            "Näher bei $A$ als bei $B$: auf der Seite von $A$ der Mittelsenkrechten von $AB$. Das gilt für "
            "{c3}.\n"
            "Alle drei Bedingungen erfüllen nur {ok}.",
        ),
        "en": (
            "On the map one square is 10 m wide. A tent is to stand at least 25 m from the brook $b$, at "
            "most 40 m from the fireplace $F$, and closer to the well $A$ than to the car park $B$. Which "
            "of the marked places $P$ to $W$ meet all three conditions? Select all of them.",
            "At least 25 m from the brook: above the parallel to $b$ at a distance of 2.5 squares. This "
            "is true for {c1}.\n"
            "At most 40 m from $F$: inside the circle around $F$ with a radius of 4 squares. This is true "
            "for {c2}.\n"
            "Closer to $A$ than to $B$: on $A$'s side of the perpendicular bisector of $AB$. This is true "
            "for {c3}.\n"
            "Only {ok} meet all three conditions.",
        ),
        "fr": (
            "Sur la carte, un carreau mesure 10 m de côté. Une tente doit se trouver à 25 m au moins du "
            "ruisseau $b$, à 40 m au plus du foyer $F$ et plus près de la fontaine $A$ que du parking $B$. "
            "Lesquels des emplacements marqués $P$ à $W$ remplissent les trois conditions ? "
            "Sélectionne-les tous.",
            "À 25 m au moins du ruisseau : au-dessus de la parallèle à $b$ située à 2.5 carreaux. C'est le "
            "cas de {c1}.\n"
            "À 40 m au plus de $F$ : dans le cercle de centre $F$ et de rayon 4 carreaux. C'est le cas de "
            "{c2}.\n"
            "Plus près de $A$ que de $B$ : du côté de $A$ par rapport à la médiatrice du segment $AB$. "
            "C'est le cas de {c3}.\n"
            "Seuls {ok} remplissent les trois conditions.",
        ),
        "it": (
            "Sulla mappa un quadretto è largo 10 m. Una tenda deve stare ad almeno 25 m dal ruscello $b$, "
            "al massimo a 40 m dal focolare $F$ e più vicino alla fontana $A$ che al parcheggio $B$. Quali "
            "dei posti segnati da $P$ a $W$ soddisfano tutte e tre le condizioni? Selezionali tutti.",
            "Almeno 25 m dal ruscello: sopra la parallela a $b$ a distanza di 2.5 quadretti. Vale per "
            "{c1}.\n"
            "Al massimo 40 m da $F$: dentro il cerchio di centro $F$ e raggio 4 quadretti. Vale per {c2}.\n"
            "Più vicino ad $A$ che a $B$: dalla parte di $A$ rispetto all'asse del segmento $AB$. Vale per "
            "{c3}.\n"
            "Solo {ok} soddisfano tutte e tre le condizioni.",
        ),
    },
    "tram": {
        "de": (
            "Auf dem Ortsplan ist ein Häuschen 100 m breit. Familie Keller sucht eine Wohnung, die mehr "
            "als 200 m von der Tramlinie $t$ entfernt ist und näher bei der Schule $A$ als beim Bahnhof "
            "$B$ liegt. Welche der markierten Wohnungen $P$ bis $W$ kommen in Frage? Wähle alle aus.",
            "Mehr als 200 m von $t$ entfernt: Der Abstand wird senkrecht zur Tramlinie gemessen. Die "
            "Grenze bilden die beiden Parallelen zu $t$ im Abstand von 2 Häuschen; weiter weg liegen "
            "{c1}.\n"
            "Näher bei $A$ als bei $B$: auf der Seite von $A$ der Mittelsenkrechten von $AB$. Das gilt für "
            "{c2}.\n"
            "Beide Bedingungen erfüllen {ok}.",
        ),
        "en": (
            "On the town map one square is 100 m wide. The Keller family is looking for a flat that is "
            "more than 200 m from the tram line $t$ and closer to the school $A$ than to the station $B$. "
            "Which of the marked flats $P$ to $W$ are possible? Select all of them.",
            "More than 200 m from $t$: the distance is measured at right angles to the tram line. The "
            "boundary is formed by the two parallels to $t$ at a distance of 2 squares; farther away are "
            "{c1}.\n"
            "Closer to $A$ than to $B$: on $A$'s side of the perpendicular bisector of $AB$. This is true "
            "for {c2}.\n"
            "{ok} meet both conditions.",
        ),
        "fr": (
            "Sur le plan de la ville, un carreau mesure 100 m de côté. La famille Keller cherche un "
            "appartement situé à plus de 200 m de la ligne de tram $t$ et plus près de l'école $A$ que de "
            "la gare $B$. Lesquels des appartements marqués $P$ à $W$ conviennent ? Sélectionne-les tous.",
            "À plus de 200 m de $t$ : la distance se mesure perpendiculairement à la ligne de tram. La "
            "limite est formée par les deux parallèles à $t$ situées à 2 carreaux ; sont plus loin : "
            "{c1}.\n"
            "Plus près de $A$ que de $B$ : du côté de $A$ par rapport à la médiatrice du segment $AB$. "
            "C'est le cas de {c2}.\n"
            "{ok} remplissent les deux conditions.",
        ),
        "it": (
            "Sulla pianta della città un quadretto è largo 100 m. La famiglia Keller cerca un appartamento "
            "che disti più di 200 m dalla linea del tram $t$ e sia più vicino alla scuola $A$ che alla "
            "stazione $B$. Quali degli appartamenti segnati da $P$ a $W$ vanno bene? Selezionali tutti.",
            "Più di 200 m da $t$: la distanza si misura perpendicolarmente alla linea del tram. Il confine "
            "è formato dalle due parallele a $t$ a distanza di 2 quadretti; più lontani sono {c1}.\n"
            "Più vicino ad $A$ che a $B$: dalla parte di $A$ rispetto all'asse del segmento $AB$. Vale per "
            "{c2}.\n"
            "{ok} soddisfano entrambe le condizioni.",
        ),
    },
    "kreislinie": {
        "de": (
            "Gegeben sind der Kreis $k$ mit Mittelpunkt $M$, die Gerade $g$ und die Punkte $A$ und $B$. "
            "Welche der markierten Punkte $P$ bis $W$ sind höchstens 1.5 Häuschen von der Kreislinie $k$ "
            "entfernt, mindestens 3.5 Häuschen von $g$ entfernt und liegen näher bei $A$ als bei $B$? "
            "Wähle alle aus.",
            "Der Kreis $k$ hat den Radius 3 Häuschen. Höchstens 1.5 Häuschen von der Kreislinie entfernt "
            "ist ein Punkt, der zwischen 1.5 und 4.5 Häuschen von $M$ entfernt ist (ein Kreisring). Das "
            "gilt für {c1}.\n"
            "Mindestens 3.5 Häuschen von $g$ entfernt: rechts der Parallele zu $g$ in diesem Abstand. Das "
            "gilt für {c2}.\n"
            "Näher bei $A$ als bei $B$: auf der Seite von $A$ der Mittelsenkrechten von $AB$. Das gilt für "
            "{c3}.\n"
            "Alle drei Bedingungen erfüllen {ok}.",
        ),
        "en": (
            "The circle $k$ with centre $M$, the line $g$ and the points $A$ and $B$ are given. Which of "
            "the marked points $P$ to $W$ are at most 1.5 squares from the circle line $k$, at least 3.5 "
            "squares from $g$, and closer to $A$ than to $B$? Select all of them.",
            "The circle $k$ has a radius of 3 squares. A point is at most 1.5 squares from the circle line "
            "when it is between 1.5 and 4.5 squares from $M$ (a ring). This is true for {c1}.\n"
            "At least 3.5 squares from $g$: to the right of the parallel to $g$ at that distance. This is "
            "true for {c2}.\n"
            "Closer to $A$ than to $B$: on $A$'s side of the perpendicular bisector of $AB$. This is true "
            "for {c3}.\n"
            "{ok} meet all three conditions.",
        ),
        "fr": (
            "On donne le cercle $k$ de centre $M$, la droite $g$ et les points $A$ et $B$. Lesquels des "
            "points marqués $P$ à $W$ sont à 1.5 carreau au plus du cercle $k$, à 3.5 carreaux au moins "
            "de $g$ et plus proches de $A$ que de $B$ ? Sélectionne-les tous.",
            "Le cercle $k$ a un rayon de 3 carreaux. Un point est à 1.5 carreau au plus du cercle s'il "
            "est situé entre 1.5 et 4.5 carreaux de $M$ (une couronne). C'est le cas de {c1}.\n"
            "À 3.5 carreaux au moins de $g$ : à droite de la parallèle à $g$ située à cette distance. "
            "C'est le cas de {c2}.\n"
            "Plus proche de $A$ que de $B$ : du côté de $A$ par rapport à la médiatrice du segment $AB$. "
            "C'est le cas de {c3}.\n"
            "{ok} remplissent les trois conditions.",
        ),
        "it": (
            "Sono dati la circonferenza $k$ di centro $M$, la retta $g$ e i punti $A$ e $B$. Quali dei "
            "punti segnati da $P$ a $W$ distano al massimo 1.5 quadretti dalla circonferenza $k$, almeno "
            "3.5 quadretti da $g$ e sono più vicini ad $A$ che a $B$? Selezionali tutti.",
            "La circonferenza $k$ ha raggio 3 quadretti. Un punto dista al massimo 1.5 quadretti dalla "
            "circonferenza se si trova tra 1.5 e 4.5 quadretti da $M$ (una corona circolare). Vale per "
            "{c1}.\n"
            "Almeno 3.5 quadretti da $g$: a destra della parallela a $g$ a quella distanza. Vale per "
            "{c2}.\n"
            "Più vicino ad $A$ che a $B$: dalla parte di $A$ rispetto all'asse del segmento $AB$. Vale per "
            "{c3}.\n"
            "{ok} soddisfano tutte e tre le condizioni.",
        ),
    },
    "schatz": {
        "de": (
            "Auf einer Schatzkarte ist ein Häuschen 10 m breit. Der Schatz liegt genau 20 m vom Weg $s$ "
            "entfernt, mindestens 25 m und höchstens 55 m vom Turm $Z$ entfernt und näher bei der Eiche "
            "$A$ als beim Brunnen $B$. An welchen der markierten Stellen $P$ bis $W$ kann der Schatz "
            "liegen? Wähle alle aus.",
            "Genau 20 m vom Weg entfernt: auf einer der beiden Parallelen zu $s$ im Abstand von 2 "
            "Häuschen. Dort liegen {c1}.\n"
            "Zwischen 25 m und 55 m von $Z$ entfernt: im Kreisring um $Z$ mit den Radien 2.5 und 5.5 "
            "Häuschen. Das gilt für {c2}.\n"
            "Näher bei $A$ als bei $B$: auf der Seite von $A$ der Mittelsenkrechten von $AB$. Das gilt für "
            "{c3}.\n"
            "Alle drei Bedingungen erfüllen {ok}.",
        ),
        "en": (
            "On a treasure map one square is 10 m wide. The treasure lies exactly 20 m from the path $s$, "
            "at least 25 m and at most 55 m from the tower $Z$, and closer to the oak $A$ than to the well "
            "$B$. At which of the marked spots $P$ to $W$ can the treasure lie? Select all of them.",
            "Exactly 20 m from the path: on one of the two parallels to $s$ at a distance of 2 squares. "
            "On them lie {c1}.\n"
            "Between 25 m and 55 m from $Z$: in the ring around $Z$ with radii of 2.5 and 5.5 squares. "
            "This is true for {c2}.\n"
            "Closer to $A$ than to $B$: on $A$'s side of the perpendicular bisector of $AB$. This is true "
            "for {c3}.\n"
            "{ok} meet all three conditions.",
        ),
        "fr": (
            "Sur une carte au trésor, un carreau mesure 10 m de côté. Le trésor se trouve exactement à "
            "20 m du chemin $s$, à 25 m au moins et à 55 m au plus de la tour $Z$, et plus près du chêne "
            "$A$ que de la fontaine $B$. À quels endroits marqués $P$ à $W$ le trésor peut-il se trouver ? "
            "Sélectionne-les tous.",
            "Exactement à 20 m du chemin : sur l'une des deux parallèles à $s$ situées à 2 carreaux. S'y "
            "trouvent : {c1}.\n"
            "Entre 25 m et 55 m de $Z$ : dans la couronne de centre $Z$ et de rayons 2.5 et 5.5 carreaux. "
            "C'est le cas de {c2}.\n"
            "Plus près de $A$ que de $B$ : du côté de $A$ par rapport à la médiatrice du segment $AB$. "
            "C'est le cas de {c3}.\n"
            "{ok} remplissent les trois conditions.",
        ),
        "it": (
            "Su una mappa del tesoro un quadretto è largo 10 m. Il tesoro si trova esattamente a 20 m dal "
            "sentiero $s$, ad almeno 25 m e al massimo a 55 m dalla torre $Z$, e più vicino alla quercia "
            "$A$ che alla fontana $B$. In quali dei punti segnati da $P$ a $W$ può trovarsi il tesoro? "
            "Selezionali tutti.",
            "Esattamente a 20 m dal sentiero: su una delle due parallele a $s$ a distanza di 2 quadretti. "
            "Vi si trovano {c1}.\n"
            "Tra 25 m e 55 m da $Z$: nella corona circolare di centro $Z$ con raggi 2.5 e 5.5 quadretti. "
            "Vale per {c2}.\n"
            "Più vicino ad $A$ che a $B$: dalla parte di $A$ rispetto all'asse del segmento $AB$. Vale per "
            "{c3}.\n"
            "{ok} soddisfano tutte e tre le condizioni.",
        ),
    },
    "angeln": {
        "de": (
            "Mia steht bei $M$ und Noé bei $N$ am Ufer $u$ eines Sees. Ein Häuschen ist 1 m breit. Mia "
            "kann ihre Angel höchstens 6 m weit auswerfen. Näher als 2.5 m am Ufer und in der "
            "gestrichelten Badezone darf nicht geangelt werden. Ausserdem soll die Stelle näher bei Mia "
            "als bei Noé liegen. An welchen der markierten Stellen $P$ bis $W$ darf Mia angeln? Wähle "
            "alle aus.",
            "Höchstens 6 m von $M$ entfernt: im Kreis um $M$ mit Radius 6 Häuschen. Das gilt für {c1}.\n"
            "Mindestens 2.5 m vom Ufer entfernt: oberhalb der Parallele zu $u$ in diesem Abstand. Das gilt "
            "für {c2}.\n"
            "Ausserhalb der Badezone liegen {c3}.\n"
            "Näher bei $M$ als bei $N$: links der Mittelsenkrechten von $MN$. Das gilt für {c4}.\n"
            "Alle vier Bedingungen erfüllen {ok}.",
        ),
        "en": (
            "Mia stands at $M$ and Noé at $N$ on the shore $u$ of a lake. One square is 1 m wide. Mia can "
            "cast her line at most 6 m. Fishing is not allowed closer than 2.5 m to the shore or in the "
            "dashed bathing zone. The spot should also be closer to Mia than to Noé. At which of the "
            "marked spots $P$ to $W$ may Mia fish? Select all of them.",
            "At most 6 m from $M$: inside the circle around $M$ with a radius of 6 squares. This is true "
            "for {c1}.\n"
            "At least 2.5 m from the shore: above the parallel to $u$ at that distance. This is true for "
            "{c2}.\n"
            "Outside the bathing zone are {c3}.\n"
            "Closer to $M$ than to $N$: to the left of the perpendicular bisector of $MN$. This is true "
            "for {c4}.\n"
            "{ok} meet all four conditions.",
        ),
        "fr": (
            "Mia se tient en $M$ et Noé en $N$, au bord $u$ d'un lac. Un carreau mesure 1 m de côté. Mia "
            "peut lancer sa ligne à 6 m au plus. Il est interdit de pêcher à moins de 2.5 m du bord et "
            "dans la zone de baignade en pointillé. De plus, l'endroit doit être plus proche de Mia que "
            "de Noé. À quels endroits marqués $P$ à $W$ Mia peut-elle pêcher ? Sélectionne-les tous.",
            "À 6 m au plus de $M$ : dans le cercle de centre $M$ et de rayon 6 carreaux. C'est le cas de "
            "{c1}.\n"
            "À 2.5 m au moins du bord : au-dessus de la parallèle à $u$ située à cette distance. C'est le "
            "cas de {c2}.\n"
            "Sont en dehors de la zone de baignade : {c3}.\n"
            "Plus proche de $M$ que de $N$ : à gauche de la médiatrice du segment $MN$. C'est le cas de "
            "{c4}.\n"
            "{ok} remplissent les quatre conditions.",
        ),
        "it": (
            "Mia si trova in $M$ e Noé in $N$, sulla riva $u$ di un lago. Un quadretto è largo 1 m. Mia "
            "può lanciare la lenza al massimo a 6 m. Non si può pescare a meno di 2.5 m dalla riva né "
            "nella zona balneare tratteggiata. Inoltre il punto deve essere più vicino a Mia che a Noé. "
            "In quali dei punti segnati da $P$ a $W$ Mia può pescare? Selezionali tutti.",
            "Al massimo 6 m da $M$: dentro il cerchio di centro $M$ e raggio 6 quadretti. Vale per {c1}.\n"
            "Almeno 2.5 m dalla riva: sopra la parallela a $u$ a quella distanza. Vale per {c2}.\n"
            "Fuori dalla zona balneare si trovano {c3}.\n"
            "Più vicino a $M$ che a $N$: a sinistra dell'asse del segmento $MN$. Vale per {c4}.\n"
            "{ok} soddisfano tutte e quattro le condizioni.",
        ),
    },
    "kabel": {
        "de": (
            "Ein Mähroboter hängt an einem 9 m langen Kabel, das am Pfosten $A$ befestigt ist. Das Haus "
            "$H$ steht im Weg: Das Kabel kann nicht durch das Haus, es legt sich um die Hausecken. Ein "
            "Häuschen ist 1 m breit. Welche der markierten Stellen $P$ bis $W$ kann der Roboter "
            "erreichen? Wähle alle aus.",
            "Wo das Kabel gerade vom Pfosten zur Stelle laufen kann, zählt der Abstand zu $A$: höchstens "
            "9 Häuschen.\n"
            "Hinter dem Haus muss das Kabel um eine Hausecke. Bis zur Ecke oben rechts braucht es schon "
            "gut 7 m, von dort bleiben knapp 2 m; um die Ecke unten links und weiter um das Haus reicht "
            "es noch weniger weit.\n"
            "Erreichbar sind {ok}. Zu {no} reicht das Kabel nicht.",
        ),
        "en": (
            "A robot mower is attached to a 9 m cable fixed to the post $A$. The house $H$ is in the way: "
            "the cable cannot pass through the house, it bends round the corners of the house. One square "
            "is 1 m wide. Which of the marked spots $P$ to $W$ can the robot reach? Select all of them.",
            "Where the cable can run straight from the post to the spot, the distance to $A$ counts: at "
            "most 9 squares.\n"
            "Behind the house the cable has to go round a corner of the house. Up to the top right corner "
            "it already needs a good 7 m, leaving just under 2 m from there; round the bottom left corner "
            "and on round the house it reaches even less far.\n"
            "The robot can reach {ok}. The cable is too short for {no}.",
        ),
        "fr": (
            "Un robot tondeuse est relié à un câble de 9 m fixé au piquet $A$. La maison $H$ fait "
            "obstacle : le câble ne peut pas traverser la maison, il contourne ses angles. Un carreau "
            "mesure 1 m de côté. Lesquels des endroits marqués $P$ à $W$ le robot peut-il atteindre ? "
            "Sélectionne-les tous.",
            "Là où le câble peut aller tout droit du piquet à l'endroit, c'est la distance à $A$ qui "
            "compte : 9 carreaux au plus.\n"
            "Derrière la maison, le câble doit contourner un angle de la maison. Jusqu'à l'angle en haut "
            "à droite, il faut déjà un peu plus de 7 m, il en reste un peu moins de 2 à partir de là ; "
            "par l'angle en bas à gauche, puis le long de la maison, il va encore moins loin.\n"
            "Le robot peut atteindre {ok}. Le câble est trop court pour {no}.",
        ),
        "it": (
            "Un robot tagliaerba è attaccato a un cavo di 9 m fissato al palo $A$. La casa $H$ fa da "
            "ostacolo: il cavo non può attraversare la casa, gira attorno ai suoi spigoli. Un quadretto è "
            "largo 1 m. Quali dei punti segnati da $P$ a $W$ può raggiungere il robot? Selezionali tutti.",
            "Dove il cavo può andare dritto dal palo al punto, conta la distanza da $A$: al massimo 9 "
            "quadretti.\n"
            "Dietro la casa il cavo deve girare attorno a uno spigolo della casa. Fino allo spigolo in "
            "alto a destra servono già poco più di 7 m, da lì ne restano poco meno di 2; attorno allo "
            "spigolo in basso a sinistra e poi lungo la casa arriva ancora meno lontano.\n"
            "Il robot può raggiungere {ok}. Il cavo è troppo corto per {no}.",
        ),
    },
    "pony": {
        "de": (
            "Ein Pony ist mit einem 7 m langen Seil am Pfosten $A$ angebunden. Die Mauer $m$ kann es "
            "nicht überqueren; das Seil kann sich aber um die beiden Mauerenden legen. Ein Häuschen ist "
            "1 m breit. Welche der markierten Stellen $P$ bis $W$ kann das Pony erreichen? Wähle alle aus.",
            "Wo das Seil gerade vom Pfosten zur Stelle laufen kann, zählt der Abstand zu $A$: höchstens "
            "7 Häuschen.\n"
            "Hinter der Mauer läuft das Seil um ein Mauerende. Bis zum oberen Ende braucht es 5 m, von "
            "dort bleiben 2 m; bis zum unteren Ende braucht es rund 4.5 m, von dort bleiben rund 2.5 m.\n"
            "Erreichbar sind {ok}. Zu {no} reicht das Seil nicht.",
        ),
        "en": (
            "A pony is tied to the post $A$ with a 7 m rope. It cannot cross the wall $m$, but the rope "
            "can bend round the two ends of the wall. One square is 1 m wide. Which of the marked spots "
            "$P$ to $W$ can the pony reach? Select all of them.",
            "Where the rope can run straight from the post to the spot, the distance to $A$ counts: at "
            "most 7 squares.\n"
            "Behind the wall the rope runs round an end of the wall. Up to the top end it needs 5 m, "
            "leaving 2 m from there; up to the bottom end it needs about 4.5 m, leaving about 2.5 m.\n"
            "The pony can reach {ok}. The rope is too short for {no}.",
        ),
        "fr": (
            "Un poney est attaché au piquet $A$ par une corde de 7 m. Il ne peut pas franchir le mur $m$, "
            "mais la corde peut contourner les deux extrémités du mur. Un carreau mesure 1 m de côté. "
            "Lesquels des endroits marqués $P$ à $W$ le poney peut-il atteindre ? Sélectionne-les tous.",
            "Là où la corde peut aller tout droit du piquet à l'endroit, c'est la distance à $A$ qui "
            "compte : 7 carreaux au plus.\n"
            "Derrière le mur, la corde contourne une extrémité du mur. Jusqu'à l'extrémité du haut, il "
            "faut 5 m, il en reste 2 à partir de là ; jusqu'à celle du bas, il faut environ 4.5 m, il en "
            "reste environ 2.5.\n"
            "Le poney peut atteindre {ok}. La corde est trop courte pour {no}.",
        ),
        "it": (
            "Un pony è legato al palo $A$ con una corda di 7 m. Non può superare il muro $m$, ma la corda "
            "può girare attorno alle due estremità del muro. Un quadretto è largo 1 m. Quali dei punti "
            "segnati da $P$ a $W$ può raggiungere il pony? Selezionali tutti.",
            "Dove la corda può andare dritta dal palo al punto, conta la distanza da $A$: al massimo 7 "
            "quadretti.\n"
            "Dietro il muro la corda gira attorno a un'estremità del muro. Fino all'estremità in alto "
            "servono 5 m, da lì ne restano 2; fino a quella in basso servono circa 4.5 m, da lì ne "
            "restano circa 2.5.\n"
            "Il pony può raggiungere {ok}. La corda è troppo corta per {no}.",
        ),
    },
    "winkelstuecke": {
        "de": (
            "Oben sind zwei gleiche Winkelstücke aus je drei Quadraten gezeichnet. Welche der Figuren $A$ "
            "bis $H$ lassen sich aus genau diesen beiden Stücken legen? Die Stücke dürfen gedreht und "
            "gewendet werden. Wähle alle aus.",
            "Jede Figur besteht aus sechs Quadraten, die beiden Stücke zusammen auch. Suche in einer Figur "
            "einen Platz für das erste Stück und prüfe, ob der Rest genau das zweite Stück ist.\n"
            "Das gelingt bei {ok}.\n"
            "Bei {no} bleibt bei jedem Versuch ein Rest, der kein Winkelstück ist.",
        ),
        "en": (
            "At the top there are two identical corner pieces of three squares each. Which of the shapes "
            "$A$ to $H$ can be made from exactly these two pieces? The pieces may be turned and flipped. "
            "Select all of them.",
            "Each shape consists of six squares, and so do the two pieces together. In a shape, look for "
            "a place for the first piece and check whether the rest is exactly the second piece.\n"
            "This works for {ok}.\n"
            "For {no}, every attempt leaves a rest that is not a corner piece.",
        ),
        "fr": (
            "En haut sont dessinées deux pièces identiques en forme d'équerre, de trois carrés chacune. "
            "Lesquelles des figures $A$ à $H$ peut-on former avec exactement ces deux pièces ? On peut "
            "tourner et retourner les pièces. Sélectionne-les toutes.",
            "Chaque figure est formée de six carrés, les deux pièces ensemble aussi. Dans une figure, "
            "cherche une place pour la première pièce et vérifie si le reste est exactement la seconde.\n"
            "Cela réussit pour {ok}.\n"
            "Pour {no}, il reste à chaque essai une partie qui n'est pas une équerre.",
        ),
        "it": (
            "In alto sono disegnati due pezzi uguali a forma di angolo, di tre quadrati ciascuno. Quali "
            "delle figure da $A$ a $H$ si possono comporre esattamente con questi due pezzi? I pezzi si "
            "possono ruotare e ribaltare. Selezionale tutte.",
            "Ogni figura è formata da sei quadrati, e così anche i due pezzi insieme. In una figura cerca "
            "un posto per il primo pezzo e controlla se il resto è esattamente il secondo.\n"
            "Ci si riesce con {ok}.\n"
            "Con {no}, a ogni tentativo resta una parte che non è un angolo.",
        ),
    },
    "t-stueck": {
        "de": (
            "Oben sind ein T-Stück aus vier Quadraten und ein Zweierstück gezeichnet. Welche der Figuren "
            "$A$ bis $H$ lassen sich aus genau diesen beiden Stücken legen? Die Stücke dürfen gedreht und "
            "gewendet werden. Wähle alle aus.",
            "Jede Figur besteht aus sechs Quadraten, die beiden Stücke zusammen auch. Suche in einer Figur "
            "einen Platz für das T-Stück und prüfe, ob die zwei übrigen Quadrate nebeneinanderliegen.\n"
            "Das gelingt bei {ok}.\n"
            "Bei {no} passt das T-Stück gar nicht hinein, oder die zwei übrigen Quadrate liegen nicht "
            "nebeneinander.",
        ),
        "en": (
            "At the top there are a T-piece of four squares and a piece of two squares. Which of the "
            "shapes $A$ to $H$ can be made from exactly these two pieces? The pieces may be turned and "
            "flipped. Select all of them.",
            "Each shape consists of six squares, and so do the two pieces together. In a shape, look for "
            "a place for the T-piece and check whether the two remaining squares lie side by side.\n"
            "This works for {ok}.\n"
            "For {no}, the T-piece does not fit at all, or the two remaining squares do not lie side by "
            "side.",
        ),
        "fr": (
            "En haut sont dessinées une pièce en T de quatre carrés et une pièce de deux carrés. "
            "Lesquelles des figures $A$ à $H$ peut-on former avec exactement ces deux pièces ? On peut "
            "tourner et retourner les pièces. Sélectionne-les toutes.",
            "Chaque figure est formée de six carrés, les deux pièces ensemble aussi. Dans une figure, "
            "cherche une place pour la pièce en T et vérifie si les deux carrés restants sont côte à "
            "côte.\n"
            "Cela réussit pour {ok}.\n"
            "Pour {no}, la pièce en T n'entre pas du tout, ou les deux carrés restants ne sont pas côte "
            "à côte.",
        ),
        "it": (
            "In alto sono disegnati un pezzo a T di quattro quadrati e un pezzo di due quadrati. Quali "
            "delle figure da $A$ a $H$ si possono comporre esattamente con questi due pezzi? I pezzi si "
            "possono ruotare e ribaltare. Selezionale tutte.",
            "Ogni figura è formata da sei quadrati, e così anche i due pezzi insieme. In una figura cerca "
            "un posto per il pezzo a T e controlla se i due quadrati rimasti sono uno accanto all'altro.\n"
            "Ci si riesce con {ok}.\n"
            "Con {no} il pezzo a T non ci sta affatto, oppure i due quadrati rimasti non sono uno accanto "
            "all'altro.",
        ),
    },
    "wuerfel": {
        "de": (
            "Der Körper besteht aus zehn gleich grossen Würfeln $A$ bis $J$; jeder Würfel trägt seinen "
            "Buchstaben, keiner ist versteckt. Der ganze Körper wird in Farbe getaucht: Alle "
            "Aussenflächen werden farbig, auch die Unterseite. Welche Würfel haben genau vier farbige "
            "Flächen? Wähle alle aus.",
            "Eine Würfelfläche bleibt ohne Farbe, wenn sie an einem anderen Würfel anliegt. Zähle bei "
            "jedem Würfel, wie viele Würfel ihn berühren (daneben, davor, dahinter, darüber oder "
            "darunter).\n"
            "Ein Würfel, der zwei Würfel berührt, hat $6 - 2 = 4$ farbige Flächen: {ok}.\n"
            "{three} berühren drei Würfel und haben drei farbige Flächen; {five} berühren nur einen "
            "Würfel und haben fünf.",
        ),
        "en": (
            "The solid is made of ten cubes of the same size, $A$ to $J$; each cube carries its letter "
            "and none is hidden. The whole solid is dipped in paint: every outer face is coloured, the "
            "underside too. Which cubes have exactly four coloured faces? Select all of them.",
            "A face of a cube stays unpainted when it lies against another cube. For each cube, count how "
            "many cubes touch it (beside, in front, behind, above or below).\n"
            "A cube that touches two cubes has $6 - 2 = 4$ coloured faces: {ok}.\n"
            "{three} touch three cubes and have three coloured faces; {five} touch only one cube and "
            "have five.",
        ),
        "fr": (
            "Le solide est formé de dix cubes de même taille, $A$ à $J$ ; chaque cube porte sa lettre et "
            "aucun n'est caché. On plonge le solide entier dans de la peinture : toutes les faces "
            "extérieures sont colorées, celles du dessous aussi. Quels cubes ont exactement quatre faces "
            "colorées ? Sélectionne-les tous.",
            "Une face d'un cube reste sans peinture si elle touche un autre cube. Pour chaque cube, "
            "compte combien de cubes le touchent (à côté, devant, derrière, au-dessus ou au-dessous).\n"
            "Un cube qui touche deux cubes a $6 - 2 = 4$ faces colorées : {ok}.\n"
            "{three} touchent trois cubes et ont trois faces colorées ; {five} ne touchent qu'un cube et "
            "en ont cinq.",
        ),
        "it": (
            "Il solido è formato da dieci cubetti uguali, da $A$ a $J$; ogni cubetto porta la sua lettera "
            "e nessuno è nascosto. Il solido intero viene immerso nella vernice: tutte le facce esterne "
            "si colorano, anche quelle di sotto. Quali cubetti hanno esattamente quattro facce colorate? "
            "Selezionali tutti.",
            "Una faccia di un cubetto resta senza vernice se è appoggiata a un altro cubetto. Per ogni "
            "cubetto conta quanti cubetti lo toccano (di fianco, davanti, dietro, sopra o sotto).\n"
            "Un cubetto che ne tocca due ha $6 - 2 = 4$ facce colorate: {ok}.\n"
            "{three} toccano tre cubetti e hanno tre facce colorate; {five} toccano un solo cubetto e ne "
            "hanno cinque.",
        ),
    },
    "netz-kanten": {
        "de": (
            "Aus dem Netz lässt sich ein Quader falten. Zwei Kanten sind dick gezeichnet und heissen $k$ "
            "und $m$. Welche beiden nummerierten Kanten treffen beim Falten auf $k$ und auf $m$? Wähle "
            "beide aus.",
            "Beim Falten treffen am Rand des Netzes immer zwei gleich lange Kanten aufeinander.\n"
            "Beginne dort, wo der Rand eine einspringende Ecke hat: Die beiden Kanten an dieser Ecke "
            "treffen aufeinander. Von dort schliesst sich der Rand wie ein Reissverschluss: Sobald an "
            "einer Ecke drei Flächen zusammenkommen, treffen auch die beiden nächsten Randkanten "
            "aufeinander.\n"
            "So trifft $k$ auf die Kante {k} und $m$ auf die Kante {m}.",
        ),
        "en": (
            "The net can be folded into a cuboid. Two edges are drawn thick and are called $k$ and $m$. "
            "Which two numbered edges meet $k$ and $m$ when the net is folded? Select both.",
            "When a net is folded, two edges of equal length on its outline always meet.\n"
            "Start where the outline has a corner pointing inwards: the two edges at that corner meet. "
            "From there the outline closes like a zip: as soon as three faces come together at a corner, "
            "the next two edges of the outline meet as well.\n"
            "In this way $k$ meets edge {k} and $m$ meets edge {m}.",
        ),
        "fr": (
            "Ce patron se plie en un pavé droit. Deux arêtes sont tracées en gras et s'appellent $k$ et "
            "$m$. Quelles sont les deux arêtes numérotées qui rejoignent $k$ et $m$ lors du pliage ? "
            "Sélectionne les deux.",
            "Lors du pliage, deux arêtes de même longueur du bord du patron se rejoignent toujours.\n"
            "Commence là où le bord forme un angle rentrant : les deux arêtes de cet angle se rejoignent. "
            "À partir de là, le bord se ferme comme une fermeture éclair : dès que trois faces se "
            "rencontrent en un sommet, les deux arêtes suivantes du bord se rejoignent aussi.\n"
            "Ainsi, $k$ rejoint l'arête {k} et $m$ l'arête {m}.",
        ),
        "it": (
            "Lo sviluppo si può piegare in un parallelepipedo. Due spigoli sono disegnati spessi e si "
            "chiamano $k$ e $m$. Quali due spigoli numerati combaciano con $k$ e con $m$ quando si piega "
            "lo sviluppo? Selezionali entrambi.",
            "Piegando uno sviluppo, sul suo contorno combaciano sempre due spigoli della stessa "
            "lunghezza.\n"
            "Comincia dove il contorno ha un angolo rientrante: i due spigoli di quell'angolo combaciano. "
            "Da lì il contorno si chiude come una cerniera lampo: appena in un vertice si incontrano tre "
            "facce, combaciano anche i due spigoli successivi del contorno.\n"
            "Così $k$ combacia con lo spigolo {k} e $m$ con lo spigolo {m}.",
        ),
    },
    "netz-ecken": {
        "de": (
            "Aus dem Netz lässt sich ein Quader falten. Der Punkt $Z$ wird dabei zu einer Ecke des "
            "Quaders. Welche nummerierten Punkte fallen beim Falten auf dieselbe Ecke wie $Z$? Wähle "
            "alle aus.",
            "In jeder Ecke eines Quaders stossen drei Flächen zusammen. Im Netz kann dieselbe Ecke "
            "deshalb an mehreren Stellen des Randes liegen.\n"
            "Verfolge von $Z$ aus die Randkanten, die beim Falten aufeinandertreffen: Ihre Endpunkte "
            "fallen zusammen. Die beiden Kanten an einer einspringenden Ecke treffen aufeinander, und "
            "von dort schliesst sich der Rand wie ein Reissverschluss.\n"
            "Auf dieselbe Ecke wie $Z$ fallen die Punkte {ok}.",
        ),
        "en": (
            "The net can be folded into a cuboid. The point $Z$ then becomes a corner of the cuboid. "
            "Which numbered points land on the same corner as $Z$ when the net is folded? Select all of "
            "them.",
            "Three faces meet at every corner of a cuboid. So in the net the same corner can lie at "
            "several places on the outline.\n"
            "Starting from $Z$, follow the edges of the outline that meet when the net is folded: their "
            "end points land on each other. The two edges at a corner pointing inwards meet, and from "
            "there the outline closes like a zip.\n"
            "The points {ok} land on the same corner as $Z$.",
        ),
        "fr": (
            "Ce patron se plie en un pavé droit. Le point $Z$ devient alors un sommet du pavé. Quels "
            "points numérotés arrivent sur le même sommet que $Z$ lors du pliage ? Sélectionne-les tous.",
            "En chaque sommet d'un pavé droit, trois faces se rencontrent. Dans le patron, un même sommet "
            "peut donc se trouver à plusieurs endroits du bord.\n"
            "À partir de $Z$, suis les arêtes du bord qui se rejoignent lors du pliage : leurs "
            "extrémités se superposent. Les deux arêtes d'un angle rentrant se rejoignent, et de là le "
            "bord se ferme comme une fermeture éclair.\n"
            "Les points {ok} arrivent sur le même sommet que $Z$.",
        ),
        "it": (
            "Lo sviluppo si può piegare in un parallelepipedo. Il punto $Z$ diventa così un vertice del "
            "parallelepipedo. Quali punti numerati finiscono sullo stesso vertice di $Z$ quando si piega "
            "lo sviluppo? Selezionali tutti.",
            "In ogni vertice di un parallelepipedo si incontrano tre facce. Nello sviluppo lo stesso "
            "vertice può quindi trovarsi in più punti del contorno.\n"
            "Partendo da $Z$, segui gli spigoli del contorno che combaciano nella piegatura: i loro "
            "estremi si sovrappongono. I due spigoli di un angolo rientrante combaciano, e da lì il "
            "contorno si chiude come una cerniera lampo.\n"
            "I punti {ok} finiscono sullo stesso vertice di $Z$.",
        ),
    },
    "keil-kanten": {
        "de": (
            "Oben siehst du einen Keil (ein Prisma mit dreieckiger Grundfläche), unten sein Netz. Die "
            "schräge Fläche ist in beiden Bildern grau. Im Netz sind zwei Kanten dick gezeichnet und "
            "heissen $k$ und $m$. Welche nummerierten Kanten des Keils sind das? Wähle beide aus.",
            "Das Netz zeigt die Aussenseite des Keils. An der grauen schrägen Fläche hängen zwei "
            "Rechtecke: der Boden (das längere) und die senkrechte Wand (das kürzere).\n"
            "$k$ ist die Kante der Wand, die der grauen Fläche gegenüberliegt. Am Keil steht die Wand mit "
            "dieser Kante auf dem Boden: Das ist die Kante {k}.\n"
            "$m$ ist die kurze Seite des Dreiecks, das am Boden hängt. Drehe das Netz in Gedanken so, "
            "dass der Boden vor dir liegt und die graue Fläche dahinter ansteigt: Das Dreieck liegt dann "
            "links. Am Keil ist das das vordere Dreieck, und seine kurze Seite ist die senkrechte Kante "
            "{m}.",
        ),
        "en": (
            "Above you see a wedge (a prism with a triangular base), below it its net. The sloping face "
            "is grey in both drawings. In the net two edges are drawn thick and are called $k$ and $m$. "
            "Which numbered edges of the wedge are they? Select both.",
            "The net shows the outside of the wedge. Two rectangles hang on the grey sloping face: the "
            "floor (the longer one) and the upright wall (the shorter one).\n"
            "$k$ is the edge of the wall opposite the grey face. On the wedge the wall stands on the "
            "floor with this edge: it is edge {k}.\n"
            "$m$ is the short side of the triangle that hangs on the floor. Turn the net in your mind so "
            "that the floor lies in front of you and the grey face rises behind it: the triangle is then "
            "on the left. On the wedge this is the front triangle, and its short side is the upright "
            "edge {m}.",
        ),
        "fr": (
            "En haut, tu vois une cale (un prisme droit à base triangulaire), en bas son patron. La face "
            "oblique est grise dans les deux dessins. Dans le patron, deux arêtes sont tracées en gras "
            "et s'appellent $k$ et $m$. De quelles arêtes numérotées de la cale s'agit-il ? Sélectionne "
            "les deux.",
            "Le patron montre l'extérieur de la cale. Deux rectangles sont attachés à la face oblique "
            "grise : le sol (le plus long) et la paroi verticale (le plus court).\n"
            "$k$ est l'arête de la paroi opposée à la face grise. Sur la cale, la paroi repose sur le "
            "sol par cette arête : c'est l'arête {k}.\n"
            "$m$ est le petit côté du triangle attaché au sol. Tourne le patron en pensée pour que le "
            "sol soit devant toi et que la face grise monte derrière lui : le triangle se trouve alors à "
            "gauche. Sur la cale, c'est le triangle de devant, et son petit côté est l'arête verticale "
            "{m}.",
        ),
        "it": (
            "In alto vedi un cuneo (un prisma a base triangolare), in basso il suo sviluppo. La faccia "
            "obliqua è grigia in entrambi i disegni. Nello sviluppo due spigoli sono disegnati spessi e "
            "si chiamano $k$ e $m$. Quali spigoli numerati del cuneo sono? Selezionali entrambi.",
            "Lo sviluppo mostra l'esterno del cuneo. Alla faccia obliqua grigia sono attaccati due "
            "rettangoli: il pavimento (il più lungo) e la parete verticale (il più corto).\n"
            "$k$ è lo spigolo della parete opposto alla faccia grigia. Nel cuneo la parete poggia sul "
            "pavimento con questo spigolo: è lo spigolo {k}.\n"
            "$m$ è il lato corto del triangolo attaccato al pavimento. Gira mentalmente lo sviluppo in "
            "modo che il pavimento sia davanti a te e la faccia grigia salga dietro: il triangolo si "
            "trova allora a sinistra. Nel cuneo è il triangolo davanti, e il suo lato corto è lo "
            "spigolo verticale {m}.",
        ),
    },
    "keil-ecken": {
        "de": (
            "Oben siehst du einen Keil (ein Prisma mit dreieckiger Grundfläche), unten sein Netz. Die "
            "schräge Fläche ist in beiden Bildern grau. Am Keil ist die Ecke $Z$ markiert. Welche "
            "nummerierten Punkte des Netzes werden beim Falten zur Ecke $Z$? Wähle alle aus.",
            "In der Ecke $Z$ stossen drei Flächen zusammen: das vordere Dreieck, die graue schräge "
            "Fläche und die senkrechte Wand. Im Netz gehört $Z$ deshalb zu jeder dieser drei Flächen "
            "einmal.\n"
            "Das Netz zeigt die Aussenseite. In der Mitte liegt der Boden; an ihm hängen die graue "
            "Fläche, die Wand und die beiden Dreiecke. Drehe das Netz in Gedanken so, dass der Boden vor "
            "dir liegt und die graue Fläche dahinter ansteigt: Das vordere Dreieck liegt dann links. Auf "
            "jeder der drei Flächen ist $Z$ die Ecke, die am weitesten vom Boden entfernt ist, auf der "
            "Seite des vorderen Dreiecks.\n"
            "Das sind die Punkte {ok}.",
        ),
        "en": (
            "Above you see a wedge (a prism with a triangular base), below it its net. The sloping face "
            "is grey in both drawings. The corner $Z$ is marked on the wedge. Which numbered points of "
            "the net become the corner $Z$ when the net is folded? Select all of them.",
            "Three faces meet at the corner $Z$: the front triangle, the grey sloping face and the "
            "upright wall. So in the net $Z$ belongs to each of these three faces once.\n"
            "The net shows the outside. The floor is in the middle; the grey face, the wall and the two "
            "triangles hang on it. Turn the net in your mind so that the floor lies in front of you and "
            "the grey face rises behind it: the front triangle is then on the left. On each of the three "
            "faces, $Z$ is the corner farthest from the floor, on the side of the front triangle.\n"
            "These are the points {ok}.",
        ),
        "fr": (
            "En haut, tu vois une cale (un prisme droit à base triangulaire), en bas son patron. La face "
            "oblique est grise dans les deux dessins. Le sommet $Z$ est marqué sur la cale. Quels points "
            "numérotés du patron deviennent le sommet $Z$ lors du pliage ? Sélectionne-les tous.",
            "Trois faces se rencontrent au sommet $Z$ : le triangle de devant, la face oblique grise et "
            "la paroi verticale. Dans le patron, $Z$ appartient donc une fois à chacune de ces trois "
            "faces.\n"
            "Le patron montre l'extérieur. Le sol est au milieu ; la face grise, la paroi et les deux "
            "triangles y sont attachés. Tourne le patron en pensée pour que le sol soit devant toi et "
            "que la face grise monte derrière lui : le triangle de devant se trouve alors à gauche. Sur "
            "chacune des trois faces, $Z$ est le sommet le plus éloigné du sol, du côté du triangle de "
            "devant.\n"
            "Ce sont les points {ok}.",
        ),
        "it": (
            "In alto vedi un cuneo (un prisma a base triangolare), in basso il suo sviluppo. La faccia "
            "obliqua è grigia in entrambi i disegni. Sul cuneo è segnato il vertice $Z$. Quali punti "
            "numerati dello sviluppo diventano il vertice $Z$ quando lo si piega? Selezionali tutti.",
            "Nel vertice $Z$ si incontrano tre facce: il triangolo davanti, la faccia obliqua grigia e "
            "la parete verticale. Nello sviluppo $Z$ appartiene quindi una volta a ciascuna di queste "
            "tre facce.\n"
            "Lo sviluppo mostra l'esterno. Il pavimento è al centro; vi sono attaccati la faccia grigia, "
            "la parete e i due triangoli. Gira mentalmente lo sviluppo in modo che il pavimento sia "
            "davanti a te e la faccia grigia salga dietro: il triangolo davanti si trova allora a "
            "sinistra. Su ciascuna delle tre facce, $Z$ è il vertice più lontano dal pavimento, dalla "
            "parte del triangolo davanti.\n"
            "Sono i punti {ok}.",
        ),
    },
}
