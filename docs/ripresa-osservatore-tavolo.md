# Punto di ripresa — osservatore del tavolo

Aggiornamento alla ripresa: implementazione e revisione finale completate.
Stato corrente, configurazione e verifiche sono in `docs/osservatore-tavolo.md`.
Il resto di questo documento conserva il checkpoint storico della sospensione.

Lavoro sospeso su richiesta dell'utente il 5 novembre 2026, per chiudere e
spostare il PC. Riprendere da questo stato senza ricominciare lo sviluppo.

## Obiettivo corrente

Rilevare bottone, posizioni, check/call/bet/raise/fold/all-in, importi delle
puntate, piatto, contributo visualizzato, stack e pulsanti disponibili.
Nessuna equity, strategia, range o valutazione del comportamento avversario
in questa fase. Per i futuri calcoli, l'utente considera certe al 100% le
carte confermate e controlla personalmente eventuali errori: non confondere
questo assunto con l'errore statistico intrinseco delle simulazioni Monte Carlo.

## Stato Git

Ultimo commit precedente: 361d008, pannello live e conteggio delle mani.
Le aggiunte dell'osservatore sono salvate sul disco ma non ancora committate.
La richiesta del commit precedente e gia stata completata: non creare
automaticamente un nuovo commit al riavvio.

## Implementazione salvata

- `table_observer.py`: OCR nativo Windows persistente, preparazione a mosaico
  dei ritagli ingranditi, parser con unita BB/EUR, classificazione delle
  etichette gialle, template del bottone, posizioni da partecipanti iniziali,
  tracker delle osservazioni e servizio asincrono con coda di un fotogramma.
- `windows_ocr_worker.ps1`: Windows.Media.Ocr tramite WinRT. Sul PC e installata
  la lingua en-GB; funziona per i testi/valori controllati. Avvio nascosto da
  Python con ExecutionPolicy Bypass limitata al processo, senza cambiare le
  impostazioni globali. Nessun invio delle immagini a servizi esterni.
- `assets/table-observer/`: bottone e sei maschere di azioni calibrate sui
  vecchi fotogrammi; `provenance.json` registra sorgenti e hash. L'all-in usa
  anche lo screenshot gia fornito 155720; le altre etichette usano i video.
- `browser_capture.py`: riceve il servizio opzionale; main lo avvia e lo chiude.
  L'OCR lavora in background. Gli altri test possono usare handler senza OCR.
- `browser_ui.html`: sezione espandibile Lettura tavolo con posti, posizioni,
  stack, puntate, piatto, contributo, pulsanti disponibili e azioni osservate.
  Nessun consiglio di gioco. I pulsanti disponibili non sono azioni eseguite.
- `datasets/table-observations-reviewed.json` e `evaluate_table_observer.py`:
  controllo riproducibile di 14 fotogrammi selezionati dai materiali precedenti.
- `tests/test_table_observer.py`: 11 test del parser, posizioni anche heads-up,
  conferma, deduplicazione, separazione pulsanti/azioni, template e scarto dei
  risultati asincroni appartenenti a un'altra acquisizione.

## Verifiche gia eseguite

- 11 test dell'osservatore superati.
- OCR Windows effettivamente eseguito sulle immagini conservate.
- Valutatore: 14/14 fotogrammi e 74/74 campi annotati concordi.
  Alcuni campioni coincidono con la calibrazione: non e una misura indipendente
  sull'intero video. Non sono valutati tutti i campi di ogni fotogramma.
- Fold recuperato dai template quando Windows OCR omette la parola.
- All-in riconosciuto anche nella seconda riga del posto, al posto dello stack.
- Alcuni nomi o stack non letti restano null; non sono inventati importi.
- I test completi precedenti erano 82 Python + 3 frontend, ma non sono stati
  ancora rieseguiti dopo l'integrazione corrente dell'osservatore.

## Da completare alla ripresa

1. Revisione finale del tracker e test di integrazione API/frontend:
   - riarmare un'azione dopo un nome normale solo se NON resta un'etichetta
     gialla ambigua, per evitare duplicazioni dopo un errore OCR;
   - `positions_complete` non deve essere true prima di confermare il bottone;
   - copiare i dizionari degli eventi nei risultati per non modificare vecchie
     snapshot quando un importo viene completato successivamente;
   - testare che un utente chiamato Check, con testo bianco, non sia un'azione;
   - verificare handler con servizio finto e rendering frontend dei nuovi dati.
2. Rieseguire suite Python completa, test Node e valutatore delle osservazioni.
3. Documentare configurazione, calibrazione, limiti e riproduzione in README/docs.
4. Controllare diff e fornire un risultato conclusivo all'utente. Il commit
   richiede una nuova richiesta dell'utente.

## Limiti deliberati

Le posizioni diverse da BTN sono verificate solo con partecipanti iniziali
completi; altrimenti sono stime esplicite. Non ricalcolare SB/BB dopo i fold.
Le puntate mostrate sono totali della street, non automaticamente il costo
incrementale dell'azione. Check/fold non consumano la vecchia puntata mostrata.
Le etichette troppo brevi possono sfuggire al campionamento: la cronologia
ha `history_complete: false`, senza ricostruire azioni non osservate.
Le carte confermate continuano a usare il filtro esistente a cinque letture.

Non sono stati lasciati in esecuzione servizi OCR di sviluppo: i processi
delle prove sono stati chiusi nei rispettivi blocchi finally. Non chiudere
automaticamente il bot eventualmente avviato dall'utente.
