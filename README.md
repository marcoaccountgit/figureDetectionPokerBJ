# Riconoscimento di carte da registrazioni di casinò

Primo prototipo **Python + OpenCV**, eseguito interamente in locale, costruito
sulla registrazione `Screen Recording 2026-11-04 174316.mp4` (23:05, 1480×920,
30 fps). Non richiede GPU, servizi cloud o addestramento per essere provato.

La modalità webcam usa ora un **modello YOLO11 già addestrato sulle 52 classi**
valore+seme. Cerca direttamente gli indici, senza dipendere dal contorno della
carta, dal font dei riferimenti del video o dalla posizione sul tavolo.
Riconosce valore e seme delle immagini digitali e tenta il riconoscimento delle
carte fisiche del **tavolo principale**. Identifica automaticamente le due viste
Casino Stud Poker / Casino Hold’em attraverso il titolo dell’interfaccia.
Non attribuisce uno stato attivo/inattivo: riporta anche le carte che restano
visibili durante una disconnessione. La stessa carta fisica e la sua immagine
digitale sono due apparizioni distinte. Non deduce le carte coperte.

**Stato: prototipo sperimentale, non riconoscitore completo di tutte le carte.**
La lettura delle carte fisiche è ancora parziale; le carte piccole dei tavoli
sullo sfondo non sono gestite. In modalità video/tavolo, nuove inquadrature,
altri siti e cambi di layout richiedono calibrazione e nuovi riferimenti. Le zone di ricerca sono relative
all'intera immagine del gioco, normalizzata a 1480×920.
La modalità originale a riferimenti rimane disponibile con `--detector templates`.
La generalizzazione del modello su ogni mazzo non è garantita e va verificata.

È disponibile anche il profilo **`pokerstars`**, fine-tuned sul tavolo digitale
della registrazione `Screen Recording 2026-11-04 195129.mp4`. Riconosce solo le
carte, ignorando i pulsanti. Il modello della webcam rimane quello generale.
Procedura, dataset e limiti sono in [docs/training-pokerstars.md](docs/training-pokerstars.md).

Per vedere il risultato sull'ultima registrazione eseguire
**`Avvia-Video-PokerStars.cmd`**. Il modello aggiornato usa anche esempi reali
dei 10: sui dieci fotogrammi esclusi dal nuovo addestramento passa da 37/40 a
39/40 letture corrette, con una confusione residua tra 8S e 8C. Il controllo
usa casi gia osservati nello sviluppo e non dimostra copertura di tutte le 52
carte. Dataset, confronto e backup sono descritti in
[docs/miglioramento-carte.md](docs/miglioramento-carte.md).

L'ultimo aggiornamento aggiunge 135 fotogrammi reali da altre mani, portando
il training reale a 45 delle 52 identita. Nei flussi PokerStars a frequenza
richiesta >=2fps e attiva la conferma su letture consecutive: il primo
fotogramma attende conferma, le carte scomparse vengono rimosse subito.
Si puo disabilitare con `--no-temporal`. Dati, misure e limiti in
[docs/mani-e-sequenze.md](docs/mani-e-sequenze.md).

L'aggiornamento dalla nuova registrazione `screen-capture (10)` aggiunge 33
fotogrammi verificati al training. Nei quattro fotogrammi di test di sviluppo
passa da 18/20 a 20/20 indici corretti, correggendo due 10D letti QD. Il vecchio
errore 8S letto 8C rimane. La cattura cambia risoluzione e richiede decodifica
nativa e allineamento per queste verifiche; dettagli, backup e limiti in
[docs/improvement-capture10.md](docs/improvement-capture10.md).

## Installazione

Python 3.11–3.14. Su Windows, dalla cartella del progetto:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe download_model.py
```

I riferimenti in `assets/` sono già inclusi: non occorre il video per caricarli.
Nell'ambiente di sviluppo corrente le dipendenze sono anche presenti nella
cartella locale ignorata `.local-deps/`. Il video originale non viene copiato
nel repository né modificato.
Il download del modello è di circa 38 MB, con versione e checksum fissati in
`models/manifest.json`. Su questo PC i pesi sono già presenti. L'elaborazione
rimane locale: nessun fotogramma viene caricato online. Provenienza e licenza
AGPL-3.0 dei pesi sono documentate in [models/README.md](models/README.md).

## Prova su una porzione del video

```powershell
.\.venv\Scripts\python.exe recognize.py `
  --video 'C:\Users\jhonn\Videos\Screen Recordings\Screen Recording 2026-11-04 174316.mp4' `
  --start 330 --duration 15 --fps 10 --save-every 10 `
  --output artifacts/prova
```

Il comando produce:

- `detections.jsonl`: un risultato per fotogramma analizzato, con timestamp,
  vista riconosciuta, poligoni, rettangoli e punteggi dei simboli.
- `frame-*.jpg`: anteprime annotate; **D** indica immagine digitale, **P** carta
  fisica; verde indica lettura accettata, giallo e `?` una lettura incerta.
- `summary.json`: conteggi e percentili dei tempi di elaborazione.

Esempio di carta riconosciuta:

```json
{
  "domain": "digital",
  "card": "JH",
  "rank": "J",
  "suit": "H",
  "accepted": true,
  "bbox": [919, 722, 953, 770]
}
```

Semi: `H` cuori, `D` quadri, `C` fiori, `S` picche. `10` rappresenta il dieci.
Quando `accepted` è falso, `card` vale `null`: `rank` e `suit` sono soltanto il
miglior candidato scartato. I punteggi di correlazione **non sono probabilità**.
I rettangoli sono `[sinistra, alto, destra, basso]` nelle coordinate originali
dell'immagine di ingresso. I conteggi indicano apparizioni nei fotogrammi,
non carte uniche o mani giocate.

Su una singola immagine:

```powershell
.\.venv\Scripts\python.exe recognize.py --image screenshot.png --output artifacts/immagine
```

Per scandire tutto il video velocemente, con un campione al secondo:

```powershell
.\.venv\Scripts\python.exe recognize.py `
  --video 'C:\Users\jhonn\Videos\Screen Recordings\Screen Recording 2026-11-04 174316.mp4' `
  --fps 1 --save-every 60 --output artifacts/full-video
```

Il campionamento a 1 fps serve all'ispezione: non prova una latenza live sotto
un secondo. Il programma sovrascrive i risultati nella cartella di output
se la si riutilizza; usare cartelle distinte per esecuzioni da conservare.

## Prova con la webcam

Su questo PC basta fare doppio clic su **`Avvia-Webcam.cmd`**, oppure eseguire
dalla cartella del progetto:

```powershell
.\Avvia-Webcam.cmd
```

Il programma apre la webcam numero 0 e una finestra con il risultato live.
Il launcher usa l'ambiente `.venv` se presente, altrimenti il Python locale
già utilizzato per sviluppare il progetto. Con un ambiente appena installato:

```powershell
.\.venv\Scripts\python.exe recognize.py --camera 0 --output artifacts/webcam
```

Ogni avvio conserva una cartella separata `artifacts/webcam/session-.../`, per
non sovrascrivere le prove precedenti. Il percorso completo appare nella console.

Per la prima prova:

1. Mostrare chiaramente **valore e seme**. Non è più necessario che il contorno
   completo sia visibile; evitare comunque dita sugli indici e riflessi.
2. Tenerla verticale e abbastanza vicina da occupare circa un terzo dell'immagine.
   Si può anche inquadrare una singola carta ingrandita sul monitor.
3. Verde con un codice come `JH` significa identità confermata; giallo con `?`
   significa indice proposto ma lettura non sufficientemente affidabile.
4. **Salva fotogramma** conserva originale PNG, immagine annotata e JSON in
   `artifacts/webcam/session-.../`. **Esc**, la X o il pulsante Chiudi fermano il programma.

Il modello restituisce un rettangolo per **indice**, non per carta intera:
la tua carta con quattro indici può avere quattro rettangoli con lo stesso codice.
Il contatore `Indici` e i log contano queste apparizioni; non carte uniche.
La barra mostra i codici distinti letti, senza fondere i risultati nei log.
Una proposta richiede score almeno 0,60 e margine 0,15 sulla seconda classe per
essere confermata. Gli score del modello non sono probabilità calibrate.
Se `Indici` resta a zero, premere **Salva fotogramma** mentre la carta è visibile:
il file `snapshot-...-raw.png` permette di diagnosticare il problema reale di
inquadratura senza affidarsi soltanto al log. Indici troppo piccoli, sfocati,
coperti o con una grafica fuori dal dataset possono ancora non essere riconosciuti.

Per default non vengono salvate automaticamente immagini della webcam:
rimangono il log dei risultati e il riepilogo. Il salvataggio automatico può
essere abilitato esplicitamente con `--save-every 10`.

Se la webcam corretta non è la prima, cambiare indice:

```powershell
.\.venv\Scripts\python.exe recognize.py --camera 1 --output artifacts/webcam
```

Il vecchio rilevatore geometrico resta disponibile con `--detector templates`.
Solo in quella modalità si sceglie `--card-layout corner` (indice classico,
default) o `--card-layout casino` (grafica del video).

Per usare il modello anche su un'immagine salvata o su un video, specificare
`--detector model`; negli altri comandi il default resta quello a riferimenti:

```powershell
.\.venv\Scripts\python.exe recognize.py --image screenshot.png --detector model --output artifacts/modello
```

L'anteprima usa Tkinter/Pillow e funziona anche con OpenCV headless. Python deve
includere Tcl/Tk, normalmente presente nell'installazione Windows ufficiale.
`--no-preview --duration 10` permette una prova senza finestra, scrivendo solo i
risultati. Se la webcam non si apre, chiudere app come Fotocamera/Teams e controllare
Impostazioni Windows → Privacy e sicurezza → Fotocamera → accesso per app desktop.

L'acquisizione usa un solo fotogramma in attesa: quelli vecchi vengono sostituiti
mentre il riconoscitore lavora. La webcam chiede 1280×720 a 30 fps, ma il formato
effettivo dipende dal dispositivo. Il limite richiesto è 10 analisi/s; gli fps
effettivi diminuiscono se l'inferenza richiede più tempo. Sui tre fotogrammi reali
salvati il modello ha impiegato circa 0,38–0,42 secondi per immagine su CPU.

**Verifica reale disponibile:** il 10 di quadri è stato letto correttamente in
tutti e tre i fotogrammi salvati nella sessione `20261104-191635-868923`, con
quattro indici per immagine; nessun indice è stato aggiunto ai riferimenti né è
stato effettuato fine-tuning su queste immagini. Risultati e anteprime sono in
`artifacts/webcam-model-check/`. È una prova su **una sola carta**, non sulle
altre 51 classi o su tutti i mazzi. La nuova modalità va ancora provata live.

## Cattura live dello schermo

```powershell
.\.venv\Scripts\python.exe recognize.py --screen --fps 10 --duration 30 --output artifacts/live
```

Se il gioco non riempie lo schermo, indicare il rettangolo del contenuto di gioco
con `--bbox LEFT TOP RIGHT BOTTOM`. Il ritaglio deve corrispondere all'intera
area di gioco della registrazione, incluso il titolo in alto; non solo alle
carte. Margini del browser o proporzioni diverse spostano le zone calibrate.
La cattura usa Pillow ImageGrab su Windows; è implementata ma non è stata
collaudata in una sessione di gioco live. `Ctrl+C` interrompe il comando.
Il ciclo cattura un nuovo fotogramma dopo l'elaborazione, senza una coda di
fotogrammi arretrati. Se l'elaborazione supera il periodo richiesto, gli fps
effettivi diminuiscono.

## Funzionamento della modalità a riferimenti

1. Normalizzazione delle dimensioni e lettura della vista dal titolo visibile.
2. Ricerca delle piccole carte digitali tramite colore chiaro e geometria.
3. Per le carte fisiche, ricerca di contorni nelle fasce calibrate del tavolo
   principale, stima del numero di carte della fila e correzione prospettica.
   Una seconda soglia di luminosità recupera i bordi in ombra solo quando il
   ritaglio alternativo coincide con una carta già individuata: non crea doppioni.
4. Estrazione separata di valore e seme, pulizia e normalizzazione dei simboli.
5. Confronto vettoriale con i riferimenti del video, anche sul verso ruotato
   delle carte fisiche. Per queste ultime si riutilizzano anche i riferimenti
   digitali, oltre ai campioni fotografici.
6. Verifica del colore dell'inchiostro: cuori/quadri rossi, fiori/picche neri.
   Accettazione soltanto sopra soglia e con margine rispetto alla seconda
   classe compatibile con il colore. Letture accettate ma discordanti dei due
   versi o ritagli della stessa carta producono `conflicting_readings` e
   rimangono incerte. Ogni fotogramma è indipendente: nessuna memoria della mano,
   deduplicazione o assegnazione di attività.

Le soglie sono conservative. Una carta gialla può essere leggibile per una
persona ma non abbastanza simile ai riferimenti per questo algoritmo.
Le file di carte non perfettamente allineate possono produrre ritagli errati:
è il limite principale della parte fotografica attuale.

## Verifica e risultati

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe evaluate.py `
  'C:\Users\jhonn\Videos\Screen Recordings\Screen Recording 2026-11-04 174316.mp4'
```

I dieci test del riconoscitore originale controllano sfondo vuoto, rifiuto di carte coperte, riconoscimento di
un esempio con rimappatura delle coordinate, cambio di vista, presenza di tutti
i valori e semi, campionamento temporale del video, colore dei simboli, rifiuto
delle letture discordanti, recupero dei bordi in ombra e conservazione dei
riferimenti in caso di errore nella rigenerazione. Non attestano l'accuratezza
su nuove registrazioni.
Dieci test aggiuntivi coprono la modalità webcam: carta fuori dalle posizioni del
tavolo con prospettiva, carta capovolta, carta bianca senza simboli, scena vuota,
errore di apertura, scarto dei fotogrammi arretrati e comando con anteprima,
salvataggio e chiusura della sorgente, sfondo chiaro, carte piccole e angoli
arrotondati. Sei ulteriori test controllano preelaborazione RGB/letterbox del
modello, coordinate originali, soppressione dei duplicati senza fondere indici
separati, letture ambigue e output non valido. Totale: **26 test**. I test webcam usano
immagini sintetiche e dispositivi simulati, senza accendere la fotocamera.
Otto test aggiuntivi coprono il profilo del tavolo, la separazione delle mani,
le coordinate dei ritagli, le carte dell'avversario e i bordi sovrapposti.
Totale corrente: **34 test**. I risultati a riferimenti nelle tabelle seguenti
restano distinti dal profilo fine-tuned del nuovo video.

Le tabelle seguenti riguardano esclusivamente il rilevatore **a riferimenti**,
non il modello YOLO. `evaluation_cases.json` contiene un controllo manuale a 01:30, 05:30 e 20:30.
I due fotogrammi con carte contengono 13 apparizioni digitali e 13 fisiche:

| Tipo | Identità corrette confermate | Rimaste senza lettura | Identità errate confermate |
|---|---:|---:|---:|
| Digitali | 13/13 | 0 | 0 |
| Fisiche | 8/13 | 5 | 0 |

È un **piccolo controllo diagnostico usato durante lo sviluppo**, dalla stessa
registrazione dei riferimenti. Non è una misura indipendente di accuratezza.
La verifica confronta i conteggi delle identità per dominio, non la precisione
dei rettangoli. Il rapporto dettagliato e le immagini annotate sono in
`artifacts/evaluation/`.

Un controllo aggiuntivo su sette fotogrammi, non aggiunti ai riferimenti,
è riproducibile con:

```powershell
.\.venv\Scripts\python.exe evaluate.py `
  'C:\Users\jhonn\Videos\Screen Recordings\Screen Recording 2026-11-04 174316.mp4' `
  --cases evaluation_holdout.json --output artifacts/holdout
```

| Tipo | Identità corrette confermate | Rimaste senza lettura | Identità errate confermate |
|---|---:|---:|---:|
| Digitali | 37/41 | 4 | 0 |
| Fisiche | 15/39 | 24 | 0 |

Anche questi fotogrammi provengono dalla stessa registrazione: non sono un
test su una sessione indipendente. Il controllo include mani sovrapposte alle
carte e carte fisiche svelate prima dell'aggiornamento delle immagini digitali.
La lettura fisica non usa l'identità mostrata nell'interfaccia come scorciatoia.

Una prova a 10 campioni/s su 20 secondi di video (200 fotogrammi, da 20:20)
ha misurato circa **19 ms mediani e 133 ms al 95° percentile** per l'algoritmo;
report in `artifacts/resume-speed/summary.json`. Il salto dal valore mediano
riflette variabilità della macchina e dei fotogrammi: sono misure locali.

`processing_ms` misura solo l'algoritmo: esclude attesa del campione, cattura,
decodifica e scrittura dei file. Non equivale al tempo tra comparsa della carta
e risultato live. I report non provano il riconoscimento entro un secondo di
tutte le carte: la copertura delle carte reali è ancora insufficiente.

## Riferimenti e ispezione

```powershell
.\.venv\Scripts\python.exe inspect_video.py 'PERCORSO_VIDEO.mp4' --step 60
.\.venv\Scripts\python.exe build_assets.py `
  'C:\Users\jhonn\Videos\Screen Recordings\Screen Recording 2026-11-04 174316.mp4'
```

`inspect_video.py` salva fotogrammi e tavole con timestamp, senza upload.
`build_assets.py` è specifico per questa registrazione: usa le etichette lette
manualmente ai timestamp nel sorgente. Prepara e verifica tutti i riferimenti
in una cartella temporanea prima di sostituire i propri piccoli file PNG e
la provenienza in `assets/provenance.json`: un video illeggibile o annotazioni
incompatibili lasciano intatti i riferimenti precedenti. Non è un addestratore generico e
non va usato su un video diverso senza aggiornare le annotazioni.

Il modello preaddestrato è un punto di partenza per ampliare la copertura.
Per misurarla servono altre carte, mazzi e sessioni annotate; un eventuale
fine-tuning deve essere valutato su una registrazione distinta dal training.
Il confronto con i riferimenti resta utilizzabile per la grafica digitale nota.
