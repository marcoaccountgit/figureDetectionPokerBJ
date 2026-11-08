# Addestramento dal video del 7 novembre, 21:23:05

Sorgente locale: `Screen Recording 2026-11-07 212305.mp4`, 932 × 680 pixel,
30 fps, durata 599,2 secondi. L'hash SHA-256 è registrato in
`artifacts/desktop-212305/inspection.json` e `datasets/desktop-212305.json`.

## Revisione e dati

Prima dell'addestramento il bot installato, con i recuperi dei ritagli incerti,
è stato eseguito su 120 punti distribuiti nell'intero video, ogni 5 secondi.
Le immagini sono state esaminate e trascritte separatamente dalle predizioni.
109 fotogrammi utilizzabili contengono 364 carte personali o comuni visibili.
Il confronto iniziale alla risoluzione originale è già completo su questi
campioni: il training non dimostra, da solo, un aumento dell'accuratezza.

Gli 11 punti esclusi comprendono editor, dialoghi, distribuzioni parziali e
animazioni per cui i riquadri fissi non costituiscono etichette attendibili.
Al secondo 365 il giocatore ha già foldato: si annota soltanto il flop,
senza propagare KC/QC dal fotogramma precedente. Le carte scure visibili
nell'anteprima dopo il fold ai secondi 480–490 sono annotate dai pixel visibili.

Le mani complete sono assegnate a un solo insieme. Sono presenti 79 fotogrammi
train, 9 val e 21 test. Si selezionano stati diversi delle carte, le immagini
più difficili e i due punti consecutivi del fold; si evita di moltiplicare
ogni fotogramma sostanzialmente identico. Quattro risoluzioni solo per il train
producono inizialmente 136 nuovi esempi; il caso limite al secondo 215 aggiunge
quattro esempi, per un totale di 140. Le nuove immagini train coprono 34 identità reali,
non tutte le 52 carte.

Il replay precedente rimane nel dataset, inclusi i suoi holdout e le 52 classi
sintetiche. Totali finali: 1.003 immagini train, 17 val, 30 test. I riferimenti dei
simboli provengono esclusivamente dal train.

## Addestramento e runtime

Si continua dal checkpoint locale `desktop-200950-v4/weights/best.pt`:
sei epoche GPU sulla RTX 4050, learning rate 0,00015, seguite da tre epoche
di affinamento a 0,0001 sul caso limite. Architettura YOLO11n
e input 640 invariati. Il candidato viene esportato in una cartella separata.
Il processo del bot già aperto mantiene il modello caricato in memoria.

Il candidato esporta 2.994 riferimenti di simboli. Eliminando soltanto i glifi
binari identici della stessa classe si conservano 1.650 riferimenti distinti.
La massima correlazione per classe e i margini fra classi restano invariati.
Il modello precedente ne caricava 2.030, con duplicati.
Il candidato finale dopo l'affinamento esporta 3.050 riferimenti, ridotti
a 1.659 distinti con lo stesso criterio di equivalenza esatta.

La prima valutazione ha rilevato una regressione 7D→JD al secondo 215:
una proposta neurale più debole da un ritaglio aggiuntivo sopprimeva una
lettura dei simboli corretta. La fusione ora ordina tutte le proposte
accettate per confidenza, senza un bonus riservato alla rete. È presente
un test specifico con due proposte sovrapposte e discordanti.

Alla larghezza di 762 pixel, il filtro geometrico precedente perdeva
13 river già riconosciuti correttamente: il piccolo errore di scala
si accumulava nell'ultimo slot. La tolleranza desktop passa da 33 a 40
pixel canonici, restando inferiore alla metà della distanza fra gli slot.
Un test verifica anche il rifiuto dei rilevamenti a metà fra due slot.
Queste correzioni riguardano la pipeline, non i soli pesi addestrati.

La valutazione confronta il candidato e il modello precedente sugli stessi
fotogrammi del video nuovo a 932 e 762 pixel e del video precedente a 960 e
1280 pixel, alternando l'ordine dei due modelli. Misura le carte accettate,
gli errori, il contributo dei recuperi e il tempo di riconoscimento completo.
Decodifica e allineamento sono esclusi dai tempi comparativi. Il rapporto
conserva anche i risultati delle mani di validazione e test separati.

Un secondo controllo riusa le tre risoluzioni e i precedenti holdout del
valutatore `evaluate_desktop_200950.py`. La promozione richiede assenza di
regressioni nei rapporti, corrispondenza degli hash e tempo medio ponderato
non superiore al precedente. Si conserva il backup in
`artifacts/desktop-212305/previous-model` e si installa una banca di simboli
con un nome distinto; i pesi del vecchio profilo browser restano invariati.

Questi risultati riguardano campioni rivisti e includono esempi train.
Non costituiscono una misura indipendente di accuratezza sull'intero video.

## Artefatti

- Annotazioni: `datasets/desktop-212305.json`.
- Revisione e predizioni iniziali: `artifacts/desktop-212305`.
- Checkpoint: `artifacts/training/desktop-212305-reviewed-v1` e `desktop-212305-reviewed-v2`.
- Candidato finale: `artifacts/desktop-212305/candidate-v2`.
- Confronto runtime: `artifacts/desktop-212305/runtime-comparison.json`.
- Regressioni precedenti: `artifacts/desktop-212305/legacy-evaluation.json`.
- Modello effettivamente installato: `artifacts/desktop-212305/promotion.json`.

Dopo l'installazione, il processo già aperto deve essere riavviato per caricare
i nuovi pesi e i nuovi riferimenti.

## Confronto finale fra i pesi

Entrambi i modelli sono valutati con le correzioni finali della pipeline:

| Campioni | Precedente | Candidato finale |
| --- | ---: | ---: |
| Nuovo video, 932 e 762 pixel | 728/728 | 728/728 |
| Video 200950, 960 e 1280 pixel | 350/350 | 350/350 |
| Carte accettate erroneamente | 0 | 0 |
| Carte nelle mani val/test, entrambi i video | 206/206 | 206/206 |
| Tempo medio nuovo video | 314,3 ms | 316,4 ms |
| Tempo medio video precedente | 341,7 ms | 332,7 ms |
| Tempo medio ponderato, 314 fotogrammi | 322,7 ms | 321,4 ms |

Il tempo complessivo è sostanzialmente invariato; la piccola differenza non
costituisce una garanzia di accelerazione. Sul nuovo video il candidato ha
richiesto tre ritagli neurali aggiuntivi su 218 fotogrammi. Il confronto iniziale
con la pipeline precedente, conservato in `runtime-comparison-v1.json`, aveva
13 river esclusi dal filtro geometrico a 762 pixel. Il recupero di questi
river deriva dalla correzione della pipeline e non va attribuito ai soli pesi.

Il controllo aggiuntivo del video precedente alle tre risoluzioni conferma
525/525 carte visibili, 1.008/1.008 slot e 9/9 holdout storici. Dopo la
promozione passano 77 test su riconoscitore, layout, sei/nove posti,
HTTP, avversari, memoria e cicli delle mani. Gli hash dei pesi installati
sono stati verificati; quelli del vecchio profilo browser sono invariati.
