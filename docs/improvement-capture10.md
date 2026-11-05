# Miglioramento dalla registrazione screen-capture (10)

Registrazione di circa 22 minuti fornita il 5 novembre 2026. L'originale WebM
rimane intatto; la copia MP4 navigabile contiene lo stesso flusso H.264 senza
ricompressione. Le identita annotate sono state lette visivamente, mai generate
dalle predizioni del modello. Non e una verifica esaustiva di tutto il video.

## Acquisizione e annotazioni

La risoluzione codificata cambia durante la registrazione. Il lettore OpenCV
locale restituisce fotogrammi neri nei campioni estratti dalla copia MP4.
FFmpeg riesce invece a decodificare le immagini alla loro risoluzione nativa.
La sola conversione del contenitore non risolve questo limite di OpenCV.

`prepare_capture_improvement.py` decodifica ogni timestamp con FFmpeg, elimina
le colonne nere laterali, ridimensiona uniformemente l'area del gioco a 1762px
di larghezza e aggiunge nero sotto fino a 1100px. Le coordinate delle annotazioni
sono riferite a questa immagine canonica, non al video originale. Questa
preparazione e specifica per la registrazione verificata, non un nuovo
allineamento automatico della cattura live. I PNG completi rimangono nella
sottocartella `reviewed` del dataset per valutare anche falsi indici fuori ROI.

`datasets/table-capture10.json` contiene 12 istanti annotati:

- Training: 7 istanti, con 8C nella prima carta del giocatore e sul board,
  8S sul board e nella seconda carta del giocatore, piu una scena vuota.
- Validazione: una mano distinta a 260s.
- Test di sviluppo: 740/750s e 960/970s, appartenenti a due mani distinte dal
  training e dalla validazione. I campioni sono stati esaminati nello sviluppo:
  non sono un benchmark intatto.

I vicini temporali vengono aggiunti solo al training quando tutti gli slot
degli indici, anche vuoti, rimangono stabili. Aggiunti 33 fotogrammi di training;
due vicini instabili scartati. Conservati tutti gli split e il replay precedente:
528 immagini train, 10 val, 10 test. I fotogrammi vicini non sono mani indipendenti.

## Risultato e versione installata

Warm-start dal checkpoint `pokerstars-sequences-clean`, learning rate 0.0002,
12 epoche richieste, arresto anticipato dopo 7. Selezione tramite la validazione
applicativa esistente. Nessuna modifica alle soglie o al filtro temporale.

| Controllo con identita esatta e IoU >=0.30 | Prima | Aggiornato |
|---|---:|---:|
| Nuovi istanti di training, 22 indici | 22/22 | 22/22 |
| Nuova validazione, 4 indici | 4/4 | 4/4 |
| Quattro fotogrammi di test, 20 indici | 18/20 | 20/20 |
| Dieci vecchi istanti esclusi, JPEG conservati | 38/40 | 38/40 |
| Vecchi ritagli di validazione/test, 46 indici | 46/46 | 46/46 |

Nella nuova registrazione gli 8S e 8C controllati erano gia corretti dopo
l'allineamento. Il miglioramento misurato corregge il **10D letto QD** a 960s
e 970s: due false letture prima, zero dopo nei quattro fotogrammi di test.

**Rimane il vecchio errore 8S letto 8C a 780s della registrazione 211955.**
Rimane anche una mancata lettura di 2S nel JPEG a 660s. Il nuovo training non
risolve quindi tutti i problemi degli otto. Nei controlli confrontabili non
sono emerse regressioni.

I video precedenti non sono piu presenti nella cartella originale. Per il
controllo precedente sono stati utilizzati i JPEG non annotati conservati in
`artifacts/table-211955/inspection` e `artifacts/table-213508/inspection`.
Il report registra gli hash dei JPEG: questi risultati non equivalgono a una
nuova esecuzione sui video sorgenti e non sono direttamente confrontabili con
il vecchio 39/40 ottenuto sui fotogrammi decodificati dai video. Non e stata
ripetuta la verifica delle vecchie sequenze temporali.

Installati i pesi verificati e l'esatto insieme di riferimenti del candidato.
Il nuovo export esclude otto vecchi PNG sintetici dei dieci non piu generati
dal replay attuale; i restanti 208 PNG sono identici. Il confronto precedente
usa il vecchio insieme completo, quello del candidato il nuovo insieme.
SHA-256 ONNX installato:
`167040b71c82e089f52690d7e418fb918c6881a75a8ab38d609c94528b44d850`.

Backup completo precedente: `artifacts/capture10-improvement/previous-model`.
Report: `artifacts/capture10-improvement/evaluation-new/report.json` e
`artifacts/capture10-improvement/evaluation-regression-jpeg/report.json`.
51 test automatici superati; comando reale `recognize.py --image` verificato
sul PNG canonico a 970s: 5S, 8C, 10D, 6S confermati. Nessuna garanzia aggiunta
sulla latenza live o sul riconoscimento di tutte le 52 carte.

## Riproduzione

Installare le dipendenze runtime e, per la sola preparazione della cattura,
`python -m pip install -r requirements-media.txt`. FFmpeg puo essere indicato
anche tramite `--ffmpeg`. Il training richiede l'ambiente GPU gia documentato.
Usare directory di output nuove: la preparazione e il nuovo valutatore
rifiutano di sovrascrivere un esperimento esistente.

```powershell
python prepare_capture_improvement.py 'C:\Users\jhonn\Downloads\screen-capture (10)-navigabile.mp4' --annotations datasets/table-capture10.json --replay artifacts/sequence-improvement/dataset-v2 --output artifacts/capture10-improvement/dataset
.venv-training/Scripts/python.exe train_table_model.py --dataset artifacts/capture10-improvement/dataset --warm-start artifacts/training/pokerstars-sequences-clean/weights/best.pt --epochs 12 --learning-rate 0.0002 --output-dir artifacts/capture10-improvement/candidate --run-name pokerstars-capture10
python evaluate_capture_improvement.py --annotations datasets/table-capture10.json --dataset artifacts/capture10-improvement/dataset --previous artifacts/capture10-improvement/previous-model --candidate artifacts/capture10-improvement/candidate --output artifacts/capture10-improvement/evaluation-new
python evaluate_improvement.py 'C:\Users\jhonn\Videos\Screen Recordings' --previous artifacts/capture10-improvement/previous-model --candidate artifacts/capture10-improvement/candidate --output artifacts/capture10-improvement/evaluation-regression-jpeg --saved-frames artifacts
```

I candidati non sono installati automaticamente dagli script. Per ripristinare
la versione precedente occorre ripristinare insieme ONNX, classi, manifest e
l'intera cartella `pokerstars-symbols` dal backup, con l'applicazione chiusa.
