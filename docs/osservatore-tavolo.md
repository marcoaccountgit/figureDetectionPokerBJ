# Osservatore del tavolo PokerStars

Il pannello browser rileva bottone, posizioni, etichette delle azioni, stack,
puntate visibili, piatto, contributo mostrato e pulsanti disponibili. Non
calcola equity, non stima range o stili e non sceglie ne esegue azioni.

## Avvio e uso

Avviare `Avvia-Browser-PokerStars.cmd`, acquisire la scheda del gioco e
avviare la scansione. **Lettura tavolo** e sempre visibile nella colonna sinistra. L'area
mostra i dati confermati, distinguendo sempre i pulsanti disponibili dalle
azioni mostrate accanto ai giocatori. Un pulsante Fold non e un fold eseguito.

La lettura usa Windows.Media.Ocr e i pacchetti lingua gia presenti sul PC;
nei controlli e stata utilizzata la lingua en-GB. Non servono Torch, servizi
cloud, chiavi API o nuovi pacchetti Python. `windows_ocr_worker.ps1` gira
nascosto in un processo PowerShell dedicato: il parametro ExecutionPolicy
Bypass vale solo per quel processo, senza cambiare la policy globale.

Se Windows OCR non e disponibile, la sezione mostra l'errore; riconoscimento
delle carte, contatore e registrazione rimangono utilizzabili. Le immagini
OCR temporanee sono locali e vengono rimosse alla chiusura del processo.

## Metodo e calibrazione

- L'allineamento esistente rimuove le bande laterali nere. I ritagli vengono
  portati alla larghezza di riferimento 1762 e ingranditi in un mosaico OCR.
- Il bottone e riconosciuto tramite il riferimento del segnalino rosso/bianco
  estratto dal fotogramma capture10 a 80 s. Viene associato al posto vicino.
- Per check, call/Vedi, bet/Puntata, raise/Rilancia a, fold e all-in si leggono
  le etichette gialle dei posti. Le maschere delle sei azioni forniscono un
  secondo controllo quando l'OCR perde parole brevi. Un nome bianco come
  Check non e un'etichetta di azione. All-in puo apparire sulla riga dello stack.
- Origine, ritagli e hash dei riferimenti sono registrati in
  `assets/table-observer/provenance.json`. La calibrazione usa i video gia
  conservati; per all-in include anche lo screenshot 155720 gia fornito.
  Non sono stati modificati o riaddestrati i pesi YOLO delle carte.
- Numeri e azioni richiedono due osservazioni concordi distanti almeno
  100 ms. Le cinque letture delle carte e del contatore restano invariate.
  Usare cinque letture OCR rischierebbe di perdere etichette brevi.

Il servizio OCR lavora in background con al massimo un fotogramma in attesa,
senza una coda crescente. L'invio avviene al massimo una volta ogni 400 ms;
la frequenza effettiva dipende da scansione e OCR. Un risultato di un'altra
acquisizione o mano non viene pubblicato. Dopo due secondi dalla cattura
un risultato e scaduto e il pannello non ne mostra i vecchi valori.

## Posizioni e cronologia

BTN e la posizione del bottone osservato. Le altre posizioni sono calcolate
in senso orario sui partecipanti osservati all'apertura della mano del
giocatore, non sul numero di avversari rimasti dopo i fold. Sono gestiti
anche cinque/quattro/tre posti e heads-up (BTN/SB contro BB).

I ruoli sono verificati solo quando il bottone e confermato e tutti i posti
sono spiegati da partecipanti osservati, posti vuoti o sit out espliciti.
Altrimenti il pannello indica le posizioni candidate come **da verificare**.
Se il bottone cambia prima del nuovo ciclo del giocatore, il vecchio elenco
dei partecipanti non viene riutilizzato per assegnare nuove posizioni.

La cronologia registra soltanto etichette osservate e confermate. La stessa
etichetta persistente non produce eventi ripetuti, ne quando cambia la street
ne quando viene completato un importo inizialmente mancante. Una normale
etichetta del nome, confermata e senza giallo ambiguo, riarma il posto per
azioni successive. Le snapshot gia restituite non sono modificate retroattivamente.

`table_observation` nelle risposte e nelle diagnosi contiene:

- `status`, `age_ms`, `ocr_processing_ms` e `ocr_language`;
- `hand_id`, `street`, `button`, `positions_complete`;
- `seats` con nome letto, posizione, azione, stack, puntata e testi OCR grezzi;
- `pot`, `collected_pot`, `street_pots`, `contribution`, `available_actions` ed `events`;
- `history_complete: false`, per non dichiarare completa una storia campionata.

Le puntate sono **totali della street**, non necessariamente incrementi:
`amount_kind: street_total`. Un rilancio a 8 BB non significa spendere altri
8 BB se il giocatore aveva gia puntato. Check/fold non usano il vecchio importo
delle chips rimaste davanti al posto (`not_applicable`). Un numero illeggibile
resta null, non diventa zero. I test coprono BB, separatori decimali e varianti
OCR dei suffissi; gli euro sono riconosciuti con suffisso EUR/€. La calibrazione
video riguarda la modalita BB: cambi di formato monetario richiedono verifica.

## Verifica

```powershell
.venv-training/Scripts/python.exe -m unittest discover -s tests
node --test tests/test_browser_ui.cjs
.venv-training/Scripts/python.exe evaluate_table_observer.py
```

Il valutatore confronta 90 campi annotati in 18 fotogrammi conservati di
211955, 213508 e capture10, comprese due porzioni di sequenza. Risultato:
90/90 campi e 18/18 casi concordi. Alcuni campioni sono anche riferimenti
di calibrazione; non e un benchmark indipendente o dell'intero video.
Report con hash e dati grezzi: `artifacts/table-observer/report.json`.

Una prova completa HTTP con JPEG qualita 92, modello carte e OCR Windows
ha riconosciuto nel fotogramma capture10 a 70 s: mano 8C/2C, bottone sinistra
bassa, piatto 3 BB, SB alto, BB destra alta e CO per il giocatore. Confermati
anche l'isolamento dei risultati dopo l'inizio della prima mano e la chiusura
del worker. Report: `artifacts/table-observer/http-native-smoke.json`.
Questa prova ripete uno stesso fotogramma e verifica l'integrazione, non la
copertura delle azioni di una partita live completa.

Il raccolto scritto sotto il board e separato dal totale Pot; i due numeri
non vengono sommati. Le prime e ultime letture confermate di flop, turn e
river vengono archiviate per mano in `street_pots`. Dettagli ed esempi di
calibrazione: [Carte e piatto 1927](carte-e-piatto-1927.md).

## Limiti

Etichette piu brevi dell'intervallo di campionamento, OCR imperfetto, finestre
che coprono il tavolo e inizio della cattura a mano gia avviata possono lasciare
dati mancanti. Non vengono dedotti check/call/raise dal solo cambiamento del
piatto o dalla scomparsa delle carte. L'identita OCR di un nome non e ancora
un identificativo persistente dell'avversario. I layout diversi dal tavolo
calibrato richiedono nuovi riferimenti e controlli.

Per un futuro motore di calcolo, le carte confermate saranno trattate come
dati certi secondo l'indicazione dell'utente. Questo non rende automaticamente
certi OCR di importi/azioni e non elimina l'errore campionario di Monte Carlo.

## Dashboard compatta

Su desktop la colonna sinistra mostra, nell'ordine: stato essenziale con
contatore mani, Board (carte sul tavolo), mano del giocatore, solo il numero
degli avversari e la tabella di lettura sempre aperta. La tendina Affidabilita
mostra posti verificati e prove del conteggio, non una percentuale di accuratezza
stimata. Sorgente, tempi e altre letture sono nella tendina Dettagli; opzioni
di registrazione e diagnosi sono nel menu Opzioni.

La colonna destra contiene un'anteprima larga al massimo 680 px, adattata
anche all'altezza disponibile, e il piatto. La dimensione visiva e separata
dalla risoluzione dei canvas di acquisizione/registrazione. Le tendine si
aprono sopra il layout, senza spostare i pannelli principali. Sotto 981 px
di larghezza viene usata una disposizione verticale leggibile con scorrimento.

Verifica nativa con Edge senza finestra visibile:

```powershell
.venv-training/Scripts/python.exe evaluate_browser_layout.py
node --test tests/test_browser_ui.cjs
```

Sono state richieste finestre 1366x768, 1280x720 e 1100x650: nei viewport
misurati, fino a 1074x557, tutti i pannelli e le sei righe del tavolo rientrano
senza scorrimento della pagina o della tabella. Il controllo verifica anche
le proporzioni dell'anteprima e la dimensione originale del canvas. Fixture
e dati sono dimostrativi; non rappresentano lo stato live dell'utente.
Screenshot e rapporti sono in `artifacts/dashboard-layout/`.
