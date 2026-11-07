# Addestramento desktop dal video 200950

Sorgente: `Screen Recording 2026-11-06 200950.mp4`, 1920×1140, 30 fps,
719,93 secondi. SHA-256:
`55afc3eaf2c9ee584b96a991ee5f73b05f3da655e3f10620701316c495df5b75`.
È stata esaminata l'intera registrazione. Le apparizioni dell'editor, della
lobby e dei dialoghi non sono considerate nuove mani con carte sconosciute.
Il limite dei primi 14 minuti riguarda esclusivamente il video precedente.

## Dati e addestramento

Le annotazioni in `datasets/desktop-200950.json` sono state trascritte dalle
immagini originali, senza usare le predizioni del modello come verità di
riferimento. Sono presenti 48 fotogrammi annotati, con 42 identità di carte
reali complessivamente visibili. Le mani sono separate tra train, validazione
e test prima della preparazione delle immagini; nessuna mano attraversa i set.

Quaranta fotogrammi di training producono 200 esempi a cinque risoluzioni.
Si conservano i 663 esempi di replay precedenti, comprese le combinazioni
sintetiche delle 52 classi. Il dataset finale contiene 863 immagini train,
8 val e 9 test, includendo i precedenti holdout. Il nuovo training reale
comprende 36 identità: il video non fornisce esempi reali di tutte le 52 carte.
Le immagini di validazione e test non alimentano i riferimenti dei simboli.

Sono stati eseguiti quattro cicli GPU di 8, 8, 5 e 4 epoche, continuando dal
checkpoint desktop locale verificato. I passaggi successivi affrontano
risoluzioni inferiori, il 4C e il KC durante l'all-in. Runtime locale OpenCV
DNN, stesso modello YOLO11n a 52 classi, licenza derivata AGPL-3.0 e nessuna
nuova dipendenza necessaria per usare il bot. I pesi desktop sono condivisi
dai profili desktop a sei e nove posti. I pesi del vecchio profilo browser
`pokerstars` sono rimasti invariati, verificandone gli hash.

## Correzioni della pipeline

- Il bordo del pannello centrale, con riferimenti normali e illuminati,
  distingue sei e nove posti anche durante Check/Call e altri evidenziamenti.
  La scomparsa temporanea dei pannelli avversari mantiene il profilo confermato.
- La perdita dei riferimenti sospende l'analisi anche dopo una cattura desktop
  nativa, che non aveva richiesto un viewport adattivo.
- Il ritaglio dello stack del giocatore a sei posti comprende la parte alta
  delle cifre e della scritta All-in. Prima il taglio del riquadro più alto
  rimuoveva parte del testo.
- Per indici desktop poco sicuri è disponibile un confronto aggiuntivo del
  seme nel ritaglio calibrato. Richiede lo stesso valore, forti corrispondenze
  dei simboli e margine tra i semi. Corregge il KC interpretato KS quando il
  riquadro della rete include un pixel aggiuntivo. Non deduce la carta corretta
  dalla presenza di un duplicato.

## Verifica e limiti

Il confronto runtime usa 1918, 1280 e 960 pixel di larghezza. Controlla 1008
slot, dei quali 525 contengono carte visibili. Validazione e test nuovi
comprendono 87 letture di carte visibili alle tre risoluzioni. Si confrontano
anche nove fotogrammi holdout precedenti e le fixture di regressione a sei e
nove posti, incluso l'A♣ dello screenshot precedentemente non riconosciuto.
Le quattro carte avversarie scoperte al secondo 705 sono JH, JD, 4H e 6H.

Il controllo monetario e delle azioni copre 21 campi trascritti in cinque
fotogrammi: piatto, contributo, importo raccolto, stack, Check, Fold e All-in.
I 90 campi del precedente confronto OCR browser rimangono corretti.
I pulsanti offerti non sono confusi con azioni già eseguite.

Una scansione operativa ogni cinque secondi controlla anche la registrazione
al di fuori delle annotazioni. Questo controllo segnala indici bianchi senza
lettura e carte duplicate; non è una misura etichettata di precisione su tutto
il video. I casi con distribuzione ancora animata e il dialogo Buy-in richiedono
attesa: non sono carte da completare per deduzione. Le misure di latenza di
questa scansione riguardano allineamento e carte, senza OCR o simulazioni equity.

Le metriche includono casi osservati durante lo sviluppo e la selezione del
modello. Non costituiscono una stima indipendente su altri video né garantiscono
che ogni fotogramma e ogni mazzo siano leggibili. I dorsi non rivelano l'identità
delle carte avversarie; layout distinti a dieci posti richiedono ancora riferimenti.

Risultati dell'ultima esecuzione:

| Controllo | Risultato |
| --- | --- |
| Carte visibili annotate, tre risoluzioni | 525/525 |
| Slot complessivi, comprese le posizioni vuote | 1008/1008 |
| Layout osservabili | 138/138 |
| Fotogrammi holdout precedenti | 9/9 |
| Campi monetari e azioni del nuovo video | 21/21 |
| Campi OCR del browser precedente | 90/90 |
| Campionamento operativo | 138 analizzati, 6 sospesi, zero duplicati |

Il campionamento operativo segnala due attese previste: distribuzione al
secondo 80 e dialogo Buy-in al secondo 715. Tempo mediano di allineamento e
lettura carte: circa 107 ms; percentile 95 circa 184 ms, sulla macchina locale.

## File e comandi

`inspect_video_200950.py` estrae i fotogrammi e i fogli di revisione.
`prepare_desktop_200950.py` costruisce il dataset senza sovrascriverne uno
esistente; `augment_desktop_200950.py` aggiunge le risoluzioni inferiori soltanto
al train. `train_table_model.py` resta il comando di addestramento ed esportazione.
Gli script di valutazione sono `evaluate_desktop_200950.py`,
`evaluate_desktop_observations.py` e `audit_desktop_200950.py`.

Esempi con l'ambiente di training già presente:

```powershell
.\.venv-training\Scripts\python.exe evaluate_desktop_200950.py --output artifacts/desktop-200950/runtime-evaluation.json
.\.venv-training\Scripts\python.exe evaluate_desktop_observations.py
.\.venv-training\Scripts\python.exe -m unittest discover -s tests
node --test tests/test_browser_ui.cjs
```

I rapporti completi e i checkpoint sono in `artifacts/desktop-200950` e
`artifacts/training/desktop-200950-v*`. Gli hash del modello pubblicato localmente
sono in `models/pokerstars-nine.manifest.json`. Il backup iniziale è in
`artifacts/desktop-200950/previous-model`; quello intermedio è in
`artifacts/desktop-200950/previous-model-v3`. La promozione confronta l'hash del
candidato con quello del rapporto di valutazione prima di installarlo.

Dopo l'aggiornamento riavviare il processo del bot e ricaricare il pannello.
