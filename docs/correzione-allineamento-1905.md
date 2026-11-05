# Correzione degli screenshot 190551 e 190655

## Diagnosi

Nell'anteprima 190551 la geometria del tavolo e spostata verso l'alto di circa
155 pixel alla larghezza canonica 1762 (74 pixel nell'anteprima estratta).
Il modello riconosceva 10C e QS, ma gli indici finivano in `other` perche le
coordinate non corrispondevano piu alla mano in basso. L'header rimane fisso
e una parte alta del tavolo e effettivamente tagliata: non e recuperabile
dall'immagine. Non basta eliminare le bande laterali nere.

Nel 190655 la geometria e normale e il modello legge 5C/3D/9C/6S dal singolo
fotogramma. La conferma poteva restare in attesa quando cinque letture non
rientravano nella vecchia finestra di due secondi. Inoltre il fold del
giocatore azzerava inutilmente anche le conferme delle carte comuni.
Gli screenshot non contengono i tempi completi della cattura originale:
la verifica dei cicli lenti usa quindi un orologio simulato, non un replay
della partita reale.

## Modifiche

- `CaptureAligner` usa due bordi del riquadro del giocatore come riferimenti:
  con carte esposte e dopo il fold. I riferimenti sono ricavati dai video gia
  caricati, con provenienza e hash in `assets/alignment/provenance.json`.
  Non dipendono dall'identita delle carte o dal testo delle azioni.
- Gli spostamenti verticali vengono compensati prima del modello, della
  separazione board/mano, del contatore, degli avversari e dell'OCR. I riquadri
  sono riportati nelle coordinate dell'anteprima originale. Le aree mancanti
  vengono riempite di nero, senza ricostruire o inventare il contenuto.
- Una nuova posizione verticale richiede tre riscontri concordi; jitter di
  pochi pixel e piccole differenze tipografiche non cambiano continuamente
  l'allineamento. Anche i bordi laterali sono stabilizzati entro tre pixel.
- Un posto avversario fuori dalla porzione effettivamente visibile e sconosciuto,
  non assente: non viene contato automaticamente come un fold.
- Restano cinque letture consecutive e un intervallo minimo di 300 ms.
  La memoria live e ora otto secondi; un salto oltre due secondi tra singoli
  campioni continua ad azzerarla. Codici discordanti, letture mancanti e carte
  scomparse interrompono sempre la sequenza, come prima.
- Il fold del giocatore non azzera piu le conferme del board e degli altri posti.
  Il contatore chiude comunque la mano del giocatore; la verifica degli
  avversari viene azzerata alla nuova distribuzione.
- La diagnosi include il riferimento verticale in `capture_alignment.vertical_anchor`
  e il ritaglio virtuale in `viewport` (top negativo indica riempimento in alto).

## Verifica

```powershell
.venv-training/Scripts/python.exe evaluate_alignment_screenshots.py
.venv-training/Scripts/python.exe -m unittest discover -s tests
node --test tests/test_browser_ui.cjs
```

Il valutatore estrae le due anteprime dagli screenshot forniti, le ripete e
le attraversa con il vero server HTTP e il modello. I timestamp simulano
cicli di 560 ms, quindi cinque campioni oltrepassano la vecchia finestra di
due secondi. Risultato confermato: 10C/QS nella mano del primo screenshot;
5C/3D/9C/6S negli slot del board del secondo, con mano del giocatore assente.
Report: `artifacts/alignment-1905/screenshots-http.json`.

Il confronto del riconoscitore prima/dopo su 35 PNG/JPEG precedenti, applicando
la rimozione delle bande in entrambi i casi e confrontando identita e IoU,
ha dato gli stessi risultati: 110 indici corretti, zero falsi positivi, uno
mancato. Nessuno spostamento verticale nuovo e stato applicato ai campioni
di quel controllo. Non e un benchmark indipendente o una prova di tutte le
transizioni live: gli input sono i fotogrammi di sviluppo gia conservati.

La suite comprende anche jitter dei bordi, cambio di allineamento, ripristino
delle coordinate, conferma con cicli lenti, pausa lunga e fold senza perdere
il board. Totale al momento della correzione: 104 test Python e 5 frontend.
