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


## Pannello browser: anteprima e registrazione

Avvia `Avvia-Browser-PokerStars.cmd` con doppio clic. Il comando usa Python
in `.venv`, oppure `.venv-training` se disponibile, e apre il pannello locale.
In alternativa esegui `python browser_capture.py` con le dipendenze del progetto.
Lascia la console aperta durante l'utilizzo; Ctrl+C chiude il server.

1. Apri il pannello in Chrome, Edge o Opera. Il gioco può essere in una scheda
   del browser oppure in un'applicazione desktop.
   Se si apre nel browser predefinito sbagliato, copia l'indirizzo della console
   nel browser desiderato.
2. Premi **Scegli sorgente** e seleziona **Scheda**, **Finestra** oppure
   **Schermo intero** nel selettore di condivisione del browser.
   Per PokerStars desktop scegli la finestra del gioco e massimizzala.
3. Controlla sorgente e anteprima, poi premi **2. Avvia scansione**.
   Il pannello mostra il fotogramma analizzato con riquadri verdi per le carte
   confermate e gialli per quelle incerte, oltre ai tempi di elaborazione.
4. **Registra video** include i riquadri del bot quando la scansione e
   l'opzione **Registra anche i riquadri del bot** sono attive. Disattiva
   l'opzione per salvare la sorgente originale. Il video e senza audio.
   Premi nuovamente il pulsante per terminare e usa il collegamento di download
   per salvare il WebM. Puoi registrare la sorgente originale anche prima di avviare la scansione.
5. **Ferma acquisizione** termina condivisione, scansione e registrazione.
   Puoi quindi scegliere un'altra scheda, finestra o schermo.

La registrazione rimane in memoria fino al download: usa sessioni brevi e
scarica i video prima di chiudere la pagina. L'elaborazione passa solo dal
server locale su `127.0.0.1`. La selezione della sorgente richiede un'azione
esplicita nel browser. Per mantenere la calibrazione del profilo PokerStars,
il tavolo deve occupare l'area acquisita senza pannelli laterali.
Con uno schermo intero, tieni il gioco massimizzato e il pannello del bot su
un altro monitor o fuori dalla vista del tavolo, per evitare sovrapposizioni.
Il tipo di sorgente selezionato viene indicato accanto al suo nome.


### Ordine delle carte comuni

Il pannello distingue le carte comuni dalle altre letture e mostra cinque
posizioni fisse: **Flop 1, Flop 2, Flop 3, Turn, River**. Le posizioni derivano
dalle annotazioni dei video 195129, 211955, 213508 e capture10. Il criterio usa
la posizione sul tavolo, non la confidenza o l'ordine restituito dal modello.
Una carta assente lascia il proprio spazio vuoto; una lettura incerta mostra
`?`. Non vengono conservate identita di fotogrammi precedenti. La geometria
segue la larghezza del gioco; controlli aggiuntivi in basso non spostano gli
spazi. Layout diversi, margini laterali o un tavolo non allineato richiedono
una nuova calibrazione. I riquadri del board riportano F1/F2/F3/Turn/River.

Dopo un aggiornamento del backend, termina e scarica eventuali registrazioni,
chiudi la console del bot con Ctrl+C, riavvia il launcher e ricarica il pannello.


### Conferma prudente e diagnosi live

Il pannello browser richiede almeno cinque osservazioni consecutive della stessa
carta nella stessa posizione, distribuite su almeno 300 ms. La finestra arriva
a otto secondi per consentire cinque cicli lenti; una pausa oltre due secondi
tra due campioni interrompe la conferma. Una lettura mancante, incerta o diversa interrompe la sequenza per
quella carta. Il filtro non conserva carte scomparse e non corregge errori
sistematici del modello. Gli altri comandi mantengono i parametri precedenti.

Quando una carta appare sbagliata, **Salva diagnosi lettura** scarica un JSON
con il fotogramma JPEG effettivamente analizzato, la sorgente, le letture grezze,
quelle confermate e gli slot del board. Il file rimane sul PC e permette di
controllare errore di identita, posizione e calibrazione sullo stesso campione.

Controllo diagnostico della modifica: 81 rilevazioni board confrontate con le
annotazioni in JPEG/PNG conservati di 211955, 213508 e capture10, nessuna
identita confermata errata nel campione. Questo conteggio non misura le carte
mancate, non e una prova sulla partita live e non garantisce assenza di errori.
Dati del controllo: `artifacts/board-diagnosis/baseline.json`.


### Bande nere nella scheda acquisita

Il server browser elimina le bande laterali quasi nere prima del modello e
prima di assegnare gli slot del board. Le coordinate di carte, poligoni e slot
vengono poi riportate all'immagine originale per mantenere i riquadri allineati.
Un cambiamento del ritaglio azzera la conferma temporale. La diagnosi include
`capture_alignment` con dimensioni originali e area del gioco utilizzata.
Questo corregge le bande nere laterali, non pannelli laterali colorati o altri
layout del tavolo.

Lo screenshot 153812 ha permesso di riprodurre il risultato errato
`?, 4D, 4H, 4H` e ottenere `5S, 2D, 2H, AH` dopo l'allineamento. Il controllo
usa l'anteprima estratta dallo screenshot con la parte inferiore mancante
riempita di nero: non equivale a una prova completa della cattura live.
Report locale: `artifacts/board-diagnosis/screenshot-153812.json`.


### Mano del giocatore

Le due carte scoperte in basso sono mostrate nella sezione **Mano del giocatore**,
in due posizioni fisse da sinistra a destra. La geometria deriva dagli indici
`hole` annotati nelle registrazioni 195129, 211955, 213508 e capture10, inclusa
la seconda carta leggermente piu in basso per la sovrapposizione.
Le carte del board e quelle degli avversari restano separate dalla mano.

La risposta JSON contiene `player_hand` con due slot e ogni rilevazione della
mano ha `table_group: player_hand` e `hand_slot: 0|1`. La conferma live rimane
almeno cinque letture consecutive su almeno 300 ms. Una carta scomparsa lascia
il suo spazio vuoto; una lettura incerta mostra `?`, senza recuperare identita
precedenti. Nell'anteprima e nella registrazione con riquadri le etichette sono
**Mano SX** e **Mano DX**. La correzione delle bande nere vale anche per la mano.

Verifica: test di assegnazione su tutte le annotazioni delle quattro registrazioni
a tre scale; inferenza sui PNG conservati di capture10 a 70/80s (8C,2C) e
160/970s (nessuna mano), risultati conformi alle annotazioni. Sono campioni di
sviluppo e non dimostrano l'accuratezza su nuove partite. Report:
`artifacts/player-hand/review.json`.


### Controllo dei simboli anche sulle letture sicure

Nel profilo PokerStars il confronto con i riferimenti di rango e seme viene
eseguito anche quando il modello ha gia accettato la carta. In precedenza era
solo un recupero per letture incerte: il modello poteva quindi confermare AS
con confidenza 0.9145 anche se i simboli riconoscevano 4S. Restano le soglie
esistenti: lettura dei simboli accettata e punteggi di rango/seme almeno 0.90.
Quando questo controllo produce una lettura forte, essa viene usata prima
della conferma temporale. Non sono stati cambiati pesi o numero di letture.
Le diagnosi registrano `neural_candidate`, `neural_confidence` e
`symbol_corrected` per rendere visibili eventuali correzioni.

Riproduzione screenshot 155720, anteprima ritagliata e bande rimosse:
prima AS/7H, dopo 4S/7H, conformemente alle carte visibili. Il confronto sui
fotogrammi conservati di 211955, 213508 e capture10 resta a 109 indici corretti,
un falso positivo e due indici mancati, usando identita e IoU >=0.30.
Nessuna regressione misurata in questo campione di sviluppo; il controllo
non garantisce accuratezza su partite nuove. Report:
`artifacts/player-hand/symbol-crosscheck.json`.


### Avversari nella mano corrente e pannello compatto

Il pannello mostra il numero degli avversari che hanno una **coppia di carte
coperte visibile**, verificando i cinque posti del layout PokerStars a sei
posti presente nelle registrazioni. Non conta nomi o avatar: un posto occupato
senza carte, incluso il sit out, non basta per essere contato. Aggiorna il
conteggio a ogni scansione: dopo un fold o una nuova distribuzione verifica
di nuovo i posti cambiati. Durante la verifica mostra un trattino, non uno
zero. Il numero di giocatori con carte visibili aggiunge il giocatore in basso
solo quando entrambi gli indici della sua mano sono rilevati.

La presenza e l'assenza richiedono entrambe cinque osservazioni consecutive
su almeno 300 ms. Una lettura ambigua, un cambio di sessione/allineamento o
una pausa oltre due secondi interrompe la conferma. I riquadri azzurri mostrano
le coppie confermate. I dati `opponents.seats` registrano punteggio, posizione
e stato di ogni posto; `opponents.count` vale null finche il conteggio non e
confermato. Anche le diagnosi includono questi dati.

Questa aggiunta e un rilevatore visivo calibrato sui video esistenti mediante
un riferimento di due dorsi rossi sovrapposti, non un nuovo addestramento dei
pesi YOLO delle carte. Riferimento: `assets/opponents/covered-pair.png`;
provenienza e ritaglio in `assets/opponents/provenance.json`. Le etichette
visive dei fotogrammi conservati sono in `datasets/opponents-reviewed.json`.
Verifica riproducibile:

```powershell
.venv-training/Scripts/python.exe evaluate_opponents.py
.venv-training/Scripts/python.exe -m unittest discover -s tests
node --test tests/test_browser_ui.cjs
```

Un fotogramma usato come riferimento e 37 fotogrammi di sviluppo da 211955,
213508 e capture10: conteggio concorde in 37/37 controlli, 185/185 posti.
Sono campioni esaminati durante lo sviluppo, non una misura indipendente
sull'intera partita. Report con hash dei fotogrammi:
`artifacts/opponents/report.json`. Il rilevatore conta i dorsi rossi visibili:
carte coperte da finestre, animazioni, carte scoperte allo showdown o altri
layout/grafiche richiedono ulteriori verifiche e non sono inferiti dai nomi.

Il frontend affianca board, mano e conteggio. L'anteprima e limitata a 820 px
senza ridurre la risoluzione inviata al riconoscitore o al video registrato.
Ogni codice carta e affiancato da un'icona SVG del seme, con colore e nome
accessibile; le icone compaiono anche sui riquadri registrati. Le istruzioni
estese sono raccolte sotto la guida espandibile.


### Recupero degli indici della mano non proposti dal modello

Nel profilo PokerStars, dopo il modello e il controllo dei simboli, il bot
controlla i due ritagli degli indici del giocatore dalle annotazioni precedenti.
Se manca una proposta in uno slot, cerca rango e seme nel ritaglio a larghezza
di riferimento 1762: questo evita di perdere un indice stretto/occluso che il
modello non ha localizzato. Le soglie dei simboli restano invariate (almeno
0.90 per rango e seme, piu margini gia richiesti), e segue la stessa conferma
live di cinque letture. Non duplica riquadri esistenti e non deduce identita
dalla posizione. I ritagli privi di sfondo bianco o di lettura forte non
producono carte. La diagnosi indica `fixed_player_index_recovery` come origine.

Screenshot 162911: la carta 3S mancava completamente nelle proposte del
modello; il recupero legge 3S e mantiene 4C. Il controllo usa l'anteprima
ridotta estratta dallo screenshot, non il fotogramma live originale. Confronto
su 35 fotogrammi conservati: invariati 109 indici corretti, un falso positivo
e due mancate letture; nessuna regressione misurata nel campione.
Report: `artifacts/player-hand/missing-index-recovery.json`.

### Posizioni, azioni e importi

Il pannello include la sezione espandibile **Lettura tavolo**, sotto
l'anteprima: bottone, BTN/SB/BB e altre posizioni, check/call/bet/raise/fold/all-in,
stack, piatto, contributo visualizzato, puntate in BB e pulsanti disponibili.
Le azioni mostrate dai giocatori sono distinte dalle opzioni ancora da premere.
Le posizioni iniziali restano fisse dopo i fold; quelle non completamente
verificate sono indicate esplicitamente. Gli importi illeggibili restano vuoti.

La lettura usa OCR Windows locale in background e riferimenti visivi estratti
dai materiali gia caricati. La scansione delle carte continua durante l'OCR;
nessun dato viene inviato a servizi esterni. Range e profili degli avversari
non sono inclusi. Per attivarla dopo un
aggiornamento, riavviare il bot e ricaricare il pannello.

Verifica sui materiali conservati: 90/90 campi annotati in 18 fotogrammi,
con sovrapposizione parziale ai riferimenti di calibrazione. Una prova HTTP
con modello carte e OCR nativo ha verificato anche il percorso JPEG completo.
Dettagli, requisiti, limiti e riproduzione: [Osservatore del tavolo](docs/osservatore-tavolo.md).

### Poker Equity Prediction

Il pannello **PROBABILITÀ ED EQUITÀ DELLA MANO**, sempre aperto sotto Lettura tavolo, mostra probabilità
allo showdown, equity, forza attuale, miglioramenti e distribuzione delle mani.
Permette di scegliere Veloce (5.000), Bilanciato (50.000) o
Accurato (250.000 simulazioni). Il conteggio automatico degli avversari usa
le coppie di carte coperte confermate dal rilevatore visivo e viene mostrato
esplicitamente. Attivando "Imposta gli avversari manualmente" si può inserire
un intero da 1 a 5 sul vecchio tavolo, oppure fino a 8 sul nuovo tavolo a nove posti.
La sezione "Ripetibilità della simulazione" spiega il
seme casuale facoltativo, che permette di ripetere lo stesso campionamento.

Riavviare `Avvia-Browser-PokerStars.cmd` e ricaricare il pannello. Il calcolo
è locale in un processo separato; dati incerti producono uno stato di attesa.
Le stime sono riferite a carte avversarie casuali uniformi e a un piatto comune,
senza side pot o rake. Nessuna azione viene eseguita sul tavolo.

Il calcolo Monte Carlo usa automaticamente il motore Rust su un solo core
quando la libreria è compilata; il pannello indica il motore utilizzato.
Per compilarla con Rust/Cargo già installato:

```powershell
.\.venv-training\Scripts\python.exe build_native_equity.py
```

In assenza della libreria resta disponibile il motore Python. Il numero di
simulazioni e la precisione statistica sono gli stessi.

Il confronto facoltativo **Confronta anche un modello fisso delle puntate**
mostra una seconda equità e il valore atteso della chiamata sotto un'ipotesi
esplicita sugli importi confermati. Non costruisce profili dei giocatori né
prevede azioni future. Il modello non è calibrato su dati di gioco; pesi e
importi usati sono visibili nel pannello. Se gli importi non sono affidabili,
resta disponibile la stima contro mani casuali.

API, schema dati, test, benchmark e limiti: [Motore equity](docs/poker-equity.md).

La sezione **Valutazione della decisione** confronta equità, piatto totale e
costo esplicito del pulsante Vedi dopo conferma temporale. Mostra soglia minima,
margine e valore atteso semplificato, con indicazioni condizionate di vedere,
passare o margine incerto. Senza importi validi e coerenti rimane in attesa.
Le ipotesi e le metriche incrociate sono nella spiegazione espandibile.
Non determina puntate ottimali e non esegue azioni: il modello esclude costi
successivi, commissioni e piatti secondari e assume mani avversarie uniformi.

Formule, criteri dei suggerimenti e test: [Valutazione della decisione](docs/poker-advice.md).

**Piatto per fase:** la sezione distingue il totale Pot dal raccolto scritto
sotto il board. Registra e mostra il primo totale confermato di flop, turn
e river, senza sovrascriverlo con le puntate successive. Gli importi restano
nelle unita visualizzate, senza una conversione automatica BB/euro.
Sono inoltre aggiunti riferimenti per recuperare 3C/4C nelle mani degli
screenshot 192703/192744, mantenendo le decisioni forti dei riferimenti
originali e le soglie esistenti. Dettagli e verifiche:
[Carte e piatto 1927](docs/carte-e-piatto-1927.md).


### Contatore delle mani del giocatore

**Mani rilevate** parte da zero a ogni nuova acquisizione. Una coppia di carte
fisicamente presente in basso, confermata per cinque campioni su almeno 300 ms,
incrementa il totale una sola volta. Il ritiro confermato di entrambe le carte
(fold o fine piatto) abilita la successiva mano. Una carta non riconosciuta o
un cambiamento del suo codice non azzerano il ciclo. Le coppie successive
possono anche avere le stesse identita della coppia precedente.

Il totale resta visibile allo stop e riparte da zero scegliendo una nuova
sorgente. Stati e transizioni sono disponibili soltanto in `hand_cycle` nelle
diagnosi; il frontend mostra solo il numero. La calibrazione del bianco delle
carte e del panno deriva dai fotogrammi gia caricati: 35 fotogrammi annotati
piu 12 della sequenza fold, senza errori di presenza nel campione. I test
controllati coprono il ciclo completo; la breve sequenza fold reale contiene
solo quattro osservazioni dopo il ritiro e quindi non attesta la conferma
finale della chiusura. Dettagli, limiti e riproduzione in
`docs/rilevazione-cambio-mano.md`.

### Tavolo desktop a nove posti

Il pannello browser riconosce automaticamente anche la grafica del client desktop
del video `Screen Recording 2026-11-06 125816.mp4`, mantenendo il profilo browser
a sei posti. Il nuovo profilo `pokerstars-nine` ha pesi, riferimenti e geometria
separati: carte comuni/personali/scoperte degli avversari, otto posti avversari,
bottone, posizioni, stack, puntate e azioni. Gli importi senza unità di questa
grafica sono fiches virtuali, senza conversione automatica in euro o BB.
Il motore di equità e l'input manuale consentono fino a otto avversari.

Riavviare il bot e ricaricare il pannello. Per il video sono stati utilizzati
solo fotogrammi precedenti a 14:00. Risultati, limiti della verifica delle carte
personali e comandi: [Profilo a nove posti](docs/tavolo-nove-posti.md).

Il modello desktop condiviso dai tavoli a sei e nove posti è stato inoltre
aggiornato con il video `Screen Recording 2026-11-06 200950.mp4`: nuovi esempi
reali, risoluzioni inferiori e controlli su assi, semi neri e carte scoperte.
Sono corretti anche il cambio di profilo durante le azioni evidenziate e il
ritaglio dello stack del giocatore. Dati, verifiche e limiti:
[Addestramento desktop 200950](docs/training-desktop-200950.md).

L'ulteriore addestramento sul video `Screen Recording 2026-11-07 212305.mp4`
comprende una revisione preliminare delle letture del bot, esempi a bassa
risoluzione e un affinamento sui casi limite. Sono inclusi controlli sulla
fusione dei rilevamenti sovrapposti e sul river nelle finestre piccole.
Dati e verifiche: [Addestramento desktop 212305](docs/training-desktop-212305.md).
