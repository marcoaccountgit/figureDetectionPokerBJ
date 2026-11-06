# Profilo PokerStars desktop a nove posti

## Sorgente e intervallo utilizzato

Video locale `Screen Recording 2026-11-06 125816.mp4`, 1918×1198 a 30 fps,
durata rilevata 1439,43 s. SHA-256:
`e5a00f508df0ca85528f62c94af02b8404a5f6dc7ccc160b37efc2a763b94aab`.
Tutti gli strumenti di preparazione, valutazione e audit di questo profilo
usano timestamp **0 ≤ t < 840 secondi**. Nessun fotogramma della disconnessione
dal minuto 14/15 in poi è stato usato per addestrare o calibrare.
Il calcolo dell'hash legge il file senza decodificare ulteriori fotogrammi.

## Modelli e integrazione

Il profilo `pokerstars-nine` è separato da `pokerstars`. I pesi ONNX e il
manifest del modello precedente non sono stati sostituiti; i relativi checksum
sono stati nuovamente verificati. La licenza del nuovo modello derivato da
Ultralytics resta AGPL-3.0. Nessuna nuova dipendenza di runtime.

- `table_profiles.py`: geometria, ordine dei nove posti e riconoscimento del client.
- `CaptureAligner`: riconosce l'intestazione della nuova grafica e conserva lo
  sfondo scuro del client, che non deve essere ritagliato come una banda nera.
  La presenza di un'icona aggiuntiva nella barra non sposta il tavolo.
- `TableCardDetector`: seleziona e carica pigramente i pesi indipendenti.
- `table_layout.py`: cinque slot del board e due della mano nelle nuove posizioni.
- `learned_detector.py`: indici piccoli, carte parzialmente nascoste dalla targhetta
  degli avversari e recupero composizionale da simboli reali del solo training.
- `OpponentDetector`: otto ritagli e riferimenti dei dorsi nelle diverse prospettive.
  Il conteggio mantiene cinque conferme consecutive su almeno 300 ms.
- `player_card_presence`: conta le mani del giocatore con la nuova geometria,
  senza trasformare il sit out in una mano giocata.
- `TableVisualReader`: riutilizza Windows OCR e il tracker esistenti. Nuovi ritagli
  di nomi, stack, puntate, piatto, raccolto e pulsanti; azioni ciano e all-in bianco.
- `table_number_reader.py`: cifre apprese da ritagli etichettati del training,
  come recupero di letture numeriche mancanti. In caso di disaccordo sullo stack
  fra OCR e modello delle cifre, il valore resta non confermato.
- UI e `EquityService`: capacità fino a otto avversari per questa grafica;
  il vecchio profilo resta limitato a cinque. Le unità CHIPS sono mostrate come fiches.

## Importi e azioni

Questa grafica mostra quantità intere in fiches virtuali. `1.500` significa
1500 fiches, non 1,5 BB o euro. Il parser specifico accetta raggruppamenti
coerenti, inclusi alcuni separatori riconosciuti come spazi/virgole, e confusioni
OCR O/0 in una stringa numerica. Il parser del profilo precedente continua
a richiedere BB/EUR espliciti. Non si deducono cifre mancanti dagli stack.

I ritagli delle puntate escludono i numeri stampati sulle fiches: una scritta
500 su una chip non è automaticamente una puntata da 500. Il piatto totale
e il raccolto centrale restano distinti. Si riconoscono Fold, Chiama/Vedi,
Check, Puntata, Rilancia e All-in. Il testo sul posto è distinto dai pulsanti
disponibili; non viene mai eseguita un'azione. I valori vengono poi confermati
dal tracker prima dell'uso nella valutazione della decisione.

## Dati di addestramento

Annotazioni e provenienza: `datasets/nine-seat-125816.json`,
`datasets/nine-seat-observations.json`, manifest dei dataset e cartelle
`assets/table-nine/`, `models/pokerstars-nine-symbols/`.

Sono stati esaminati 28 istanti distribuiti nei primi 14 minuti. Le mani sono
separate per training/validazione/test; i fotogrammi vicini si propagano solo
nel training, quando gli indici rimangono sostanzialmente invariati.

- 91 fotogrammi reali di training, incluse scene senza carte.
- 4 fotogrammi di validazione e 5 di controllo, da mani escluse dai pesi.
- 156 immagini di replay sintetico iniziale.
- 416 immagini aggiuntive con tutte le 52 combinazioni valore/seme alla
  dimensione nativa, ricavate esclusivamente da simboli e sfondo del training.
- 40 riferimenti di cifre per gli stack e 78 per gli importi: provengono solo
  da timestamp di training, con inventario JSON a fianco dei ritagli.

Sono stati eseguiti quattro cicli GPU con arresto anticipato: 13, 7, 7 e 7
epoche. Checkpoint finale: `artifacts/training/pokerstars-nine-final-125816/weights/best.pt`.
Il dataset finale ha un nuovo namespace delle cache e le etichette riviste:
il re a 420 s è di picche, verificato a piena risoluzione. Questo evita che
una precedente etichetta manuale errata resti nella cache di training.
I dieci di cuori/fiori ecc. sono classi distinte: non si inferisce il seme
dal valore o dalle altre carte visibili.

## Verifiche

Rapporto: `artifacts/nine-seat-125816/evaluation-final/report.json`.
Gli stessi 28 istanti sono stati controllati a larghezza 1918 e 1280 pixel:

| Controllo | Corrispondenze |
| --- | ---: |
| Selezione del profilo | 56/56 |
| Slot di board e mano, inclusi slot vuoti | 392/392 |
| Carte effettivamente visibili negli slot | 136/136 |
| Board completo del campione | 56/56 |
| Presenza/assenza dei dorsi nei posti annotati | 80/80 |
| Gruppi di quattro carte avversarie scoperte | 2/2, una prova per risoluzione |
| Piatto totale | 27/27 |
| Bottone annotato | 5/5 |
| Azioni annotate, tutte e sei le categorie | 17/17 |
| Stack annotati | 19/19 |
| Puntate annotate | 23/23 |

Le quantità sono apparizioni/campi annotati, non 136 carte diverse.
L'OCR degli importi è confrontato alla risoluzione nativa. Il riconoscimento
delle carte e dei posti è controllato anche alla seconda risoluzione.
Una parte dei campioni coincide con training o calibrazione; i test dei pesi
escludono le relative mani, ma il tuning dell'inferenza ha visto alcuni esiti.
Quindi **non è una stima indipendente dell'accuratezza sull'intero video**.

Regressione vecchio layout: 90/90 campi OCR su 18 fotogrammi conservati.
Suite automatica: 148 test Python e 14 frontend superati, inclusi nuovi test
di geometria, capacità, unità, separazione delle mani e caricamento dei modelli.

`smoke_nine_http.py` ha verificato il percorso completo JPEG → HTTP → routing
→ modello → conferma temporale → nove posti → OCR → processo equity:
mano KD/JS, sei avversari rilevati, un ciclo del giocatore e piatto 4250 fiches.
L'equità preflop è stata effettivamente completata. È un test di integrazione
su un'immagine ripetuta, non una prova di accuratezza temporale live.

L'audit `audit_nine_video.py` campiona ogni cinque secondi prima di 14:00,
registrando copertura delle azioni, piatti non letti e duplicati nelle carte
principali. Senza annotazioni su questi istanti, misura coerenza e copertura,
non accuratezza. Rapporto: `artifacts/nine-seat-125816/timeline-audit.json`.

Audit completato su 168 istanti da 0 a 835 s: profilo sempre riconosciuto,
nessuna duplicazione delle carte principali accettate, tutte e sei le categorie
di azione osservate. In tre istanti il piatto è rimasto illeggibile: è stato
lasciato vuoto. Il numero di azioni lette non rappresenta un conteggio completo
degli eventi, perché il campionamento ogni cinque secondi può perderne o ripeterne.

## Uso e riproduzione

Riavviare `Avvia-Browser-PokerStars.cmd`, ricaricare il pannello e selezionare
la scheda/finestra che contiene il tavolo. Il profilo viene scelto automaticamente
per le due grafiche calibrate. Non è una calibrazione universale per qualsiasi
tema o disposizione del client desktop.

```powershell
.\.venv-training\Scripts\python.exe evaluate_nine_seat.py 'C:/Users/jhonn/Videos/Screen Recordings/Screen Recording 2026-11-06 125816.mp4'
.\.venv-training\Scripts\python.exe smoke_nine_http.py 'C:/Users/jhonn/Videos/Screen Recordings/Screen Recording 2026-11-06 125816.mp4'
.\.venv-training\Scripts\python.exe audit_nine_video.py 'C:/Users/jhonn/Videos/Screen Recordings/Screen Recording 2026-11-06 125816.mp4'
.\.venv-training\Scripts\python.exe recognize.py --video 'C:/Users/jhonn/Videos/Screen Recordings/Screen Recording 2026-11-06 125816.mp4' --detector model --profile pokerstars-nine --duration 840 --fps 5 --output artifacts/nine-seat-preview
```

Gli script di preparazione rifiutano cartelle già esistenti. Per una nuova
preparazione usare directory nuove, conservando gli esperimenti precedenti.
`prepare_nine_seat.py`, `prepare_nine_native_replay.py` e
`train_nine_numbers.py` documentano il processo locale; `train_table_model.py`
accetta `--profile pokerstars-nine --spec datasets/nine-seat-125816.json`.

## Limiti e prossimi video

Il giocatore resta quasi sempre in sit out. Sono state verificate le due carte
personali iniziali, ma non una raccolta indipendente di mani personali e azioni
effettivamente disponibili al giocatore. L'utente fornirà altri video in seguito.
Le 52 classi sono coperte dai dati sintetici, non da 52 carte reali indipendenti.

Carte coperte/occluse non vengono inventate. I dorsi sono conteggiati, senza
assegnare identità. Un posto fuori dalla cattura resta incerto. Un'etichetta
molto breve può cadere fra due campionamenti OCR. Nomi o importi non leggibili
restano vuoti; il suggerimento economico non sostituisce un costo mancante con
un valore stimato. L'equità conserva il modello uniforme già concordato.
