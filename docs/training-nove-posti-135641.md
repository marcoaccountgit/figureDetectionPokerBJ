# Video del 9 novembre: tavolo a nove posti

Video: `Screen Recording 2026-11-09 135641.mp4`, 960 x 700, 30 fps,
793,4 secondi. Elaborazione e addestramento locali; nessun caricamento esterno.

## Revisione preliminare

Prima di allenare sono stati estratti 159 fotogrammi, uno ogni cinque secondi,
con proposte del modello originale e tavole visive separate per carte e dorsi.
La trascrizione manuale copre 111 fotogrammi: valori e semi del board e della
mano, presenza delle carte negli otto posti avversari e bottone del dealer.
Gli altri 48 campioni comprendono distribuzioni parziali, animazioni,
statistiche sovrapposte e la parte finale fuori dal tavolo.

Le annotazioni sono in `datasets/nine-135641.json`, con hash del video e
suddivisione per gruppi di mani contigue: 68 fotogrammi train, 17 validation,
26 test. Il gruppo 4 include piu mani durante un intervallo spesso coperto dal
pannello; rimangono tutte nello stesso split. Le immagini test non entrano
nei pesi o nei riferimenti dei simboli/dorsi. I casi test sono stati anche
usati come regressioni durante lo sviluppo del codice: i risultati sono
verifiche di questi casi conosciuti, non una stima indipendente di accuratezza
su futuri video.

## Difetti riprodotti e interventi

- Alcuni avatar e pannelli coprivano il fondo dei dorsi: punteggi circa
  0,67-0,71 lasciavano incerto anche un solo posto, bloccando il totale.
  Sono stati appresi **34 riferimenti dei bordi superiori delle coppie**, da
  otto posti e solo da fotogrammi train. Piccole variazioni di scala e margini
  di ricerca evitano di tagliare le carte alle risoluzioni compatte.
  Le soglie di presenza 0,72 e di conferma temporale non sono state ridotte.
- Un avatar verde poteva collegarsi al panno e allargarne il contorno.
  Quando il rapporto larghezza/altezza e anomalo, la stima geometrica elimina
  questi collegamenti sottili prima di cercare il bordo del tavolo.
  Il controllo non viene applicato ai contorni normali, per conservare la
  geometria dei precedenti casi a sei posti.
- I due pannelli superiori del tavolo a nove posti ora prevalgono su una
  somiglianza accidentale con un bordo del tavolo a sei posti.
- Il pannello statistiche viene riconosciuto dalle intestazioni fisse.
  L'analisi si sospende e gli avversari rimangono sconosciuti: i posti coperti
  non diventano posti senza carte. Il riferimento deriva dal secondo 140,
  appartenente al gruppo train 4.
- Il bottone del posto a destra al centro poteva essere attribuito al posto
  in basso a destra. L'associazione considera la posizione interna sul panno
  rispetto ai pannelli dei giocatori.
- Nella riproduzione continua un **2 di picche veniva memorizzato come 2 di
  fiori**. I ritagli fissi possono tagliare il fondo del simbolo quando
  l'allineamento varia di pochi pixel. Il recupero prova piccoli spostamenti,
  richiede almeno due letture forti concordanti per il recupero e blocca una
  lettura neurale con seme contraddetto da un riscontro forte. Il controllo
  aggiuntivo sulle identita gia accettate riguarda il tavolo a nove posti;
  i precedenti jack di fiori a sei posti restano verificati.

## Addestramento e installazione

Sono state eseguite **6 epoche** su RTX 4050, partendo dal checkpoint
`desktop-212305-reviewed-v2`. Il dataset conserva gli esempi precedenti e
aggiunge 88 campioni train a diverse scale, piu sette validation.
L'addestramento usa 1.091 immagini train e 24 validation complessive.

La variante con nuovi riferimenti dei simboli e stata confrontata con la
precedente; la versione installata conserva la banca dei simboli gia
validata e usa i nuovi pesi neurali. La selezione finale richiede assenza di
regressioni sulle registrazioni precedenti, assenza di nuove carte sbagliate
accettate e correttezza dei conteggi nei casi test del nuovo video.

Pesi installati: `models/pokerstars-nine.onnx`.
SHA-256: `a3a4892dec1410bea79c9b93c07fc0ff454da592b1ada9f16acda63e7f10a904`.
Il tavolo desktop a sei posti usa ora pesi indipendenti in
`models/pokerstars-desktop-six.onnx`: sono quelli precedenti, conservati dopo
che il modello nuovo ha letto come 6H un 8H in una vecchia fixture a sei
posti con una pila di fiches. La separazione evita questa regressione senza
limitare l'addestramento del tavolo a nove posti. I pesi del profilo browser
restano quelli precedenti.
Il backup completo e in `artifacts/nine-135641/previous-model`.

## Risultati sui fotogrammi annotati

Alla risoluzione originale 960 x 700:

| Controllo | Prima | Dopo |
| --- | ---: | ---: |
| Tutti gli otto posti corretti, train | 48/68 | 68/68 |
| Tutti gli otto posti corretti, validation | 7/17 | 16/17 |
| Tutti gli otto posti corretti, test | 7/26 | 26/26 |
| Tutti gli otto posti corretti, totale | 62/111 | 110/111 |
| Carte visibili corrette nei rispettivi slot | 353/360 | 357/360 |
| Carte sbagliate accettate | 1 | 0 |
| Profilo corretto | 110/111 | 111/111 |

La posizione del bottone corrisponde alle annotazioni in tutti i 111 casi,
inclusi i due campioni dove il marker non e ancora visibile e rimane sconosciuto.
Questo verifica il marker e l'assegnazione dei posti; non certifica tutti i
campi OCR, gli importi o la ricostruzione di tutte le posizioni poker quando
la distribuzione iniziale e coperta.

Il conteggio test e corretto anche a larghezza 768 e 1280. Sui 75 slot con
carte visibili nei fotogrammi test, le letture corrette sono 73 a 960, 75 a
768 e 74 a 1280; nessuna carta sbagliata accettata. L'animazione al secondo
120 lascia ancora incerto un posto avversario nella validation.

I controlli precedenti conservano **314/314** fotogrammi esatti sui video
desktop 200950 e 212305 e **56/56** sulla prima registrazione a nove posti:
**370/370**, senza nuove carte sbagliate accettate. I dieci campioni annotati
degli avversari della prima registrazione restano corretti.

La suite finale passa **234 test** con i pesi a nove posti aggiornati e i
pesi desktop a sei posti separati. Comprende anche i test HTTP con il modello
reale, il caso della pila di fiches, i semi neri, i ridimensionamenti, i fold,
le carte scoperte allo showdown e il pannello statistiche.

Durante questo controllo e stata rivista anche una vecchia etichetta del
dealer al secondo 240 della prima registrazione: il marker e sopra
`hunterSauve1959`, nel posto `middle_left`, non sopra il giocatore
`upper_left` che mostra Check. La correzione manuale e documentata nella
revisione 3 di `datasets/nine-seat-observations.json`.

## Riproduzione continua e limiti

Il video e stato riprodotto a cinque scansioni al secondo usando i timestamp
reali, allineamento, memoria, contatore mani e conferma degli avversari.
Nel confronto ai 111 istanti annotati: 95 conteggi gia corretti, 16 ancora in
attesa di conferma, **nessun conteggio confermato sbagliato**. Gli slot delle
carte corrispondono interamente in 99/111 istanti; gli scostamenti residui
comprendono inizializzazione, nuove carte e fold ancora in conferma.
La sequenza finale conserva correttamente 10S e 2S dopo la conferma.

I risultati sui fotogrammi isolati e quelli della riproduzione hanno scopi
diversi: i primi misurano la lettura dei pixel, i secondi includono il ritardo
intenzionale di cinque osservazioni. A cinque scansioni/secondo servono almeno
0,8 secondi per raccogliere cinque osservazioni. Non e una verifica di tutti
i 30 fotogrammi/secondo, ne una garanzia che qualunque transizione sia letta
senza ritardo. Nessun occupante viene dedotto dietro una sovrapposizione.

## Artefatti e riproduzione

In `artifacts/nine-135641/` sono conservati:

- `baseline.json`, screenshot e tavole visive prima dell'addestramento;
- `dataset/`, `candidate/` e il modello precedente;
- `evaluation-validated.json`, confronti a 960, 768 e 1280;
- `legacy-validated.json`, `original-nine-validated.json` e
  `original-observer-validated.json`;
- `replay-before-candidate.json`, `replay-final.json`,
  `replay-last-hand.json` e `promotion.json`.

Gli script `inspect_nine_135641.py`, `prepare_nine_135641.py`,
`train_nine_opponents.py`, `prepare_nine_135641_training.py`,
`evaluate_nine_135641.py`, `evaluate_nine_legacy_135641.py`,
`evaluate_nine_observer_135641.py`, `replay_nine_135641.py` e
`promote_nine_135641.py` conservano il procedimento. L'addestramento dei pesi
usa `train_table_model.py`; la relativa configurazione e nel run
`artifacts/training/nine-135641-v1`.

Per caricare i nuovi pesi serve un nuovo processo del bot. In questa sessione
Windows ha bloccato l'eseguibile Python dell'ambiente virtuale; l'interprete
globale ha eseguito correttamente il runtime e i test. Avvio disponibile:
`python browser_capture.py` dalla cartella del progetto, poi ricaricare il
pannello browser.
