# Fine-tuning sul tavolo digitale PokerStars

Sorgente locale: `Screen Recording 2026-11-04 195129.mp4`, 450,17 secondi,
1762×840, 30 fps. Obiettivo: riconoscere **solo le carte**; nessuna lettura o
interazione con pulsanti, puntate o controlli del gioco.

Il profilo `pokerstars` usa un YOLO11n specifico per gli indici di questa grafica.
Il modello generale della webcam, LGD Cards Gen 3, resta separato.
Gli indici restituiti sono riferiti alle coordinate dell'intera immagine;
non sono carte uniche né uno stato della mano.

## Dati e separazione

Le annotazioni riviste sono in `datasets/table-195129.json`. Le etichette
individuano valore e seme visibili, mai i dorsi. Le coordinate descrivono
l'indice, non la carta intera. Per questa registrazione sono calibrate due zone:
carte comuni e carte del giocatore, nel ritaglio `[560,380,1200,840]`.

- Training: **148 fotogrammi reali**, comprendenti esempi senza carte.
- Replay sintetico: **156 immagini**, tre per ciascuno dei 52 codici.
- Validazione: **8 fotogrammi**, appartenenti a una mano distinta, 33 indici.
- Controllo finale: **6 fotogrammi**, altra mano esclusa dal training, 15 indici
  nel fotogramma completo (13 nelle aree comuni/giocatore e 2 dell'avversario),
  incluso il popup finale senza carte leggibili.

I fotogrammi vicini a un'annotazione entrano solo nel training e solo se gli
indici risultano praticamente identici. Le divisioni avvengono per mano, non
distribuendo casualmente fotogrammi consecutivi. Il replay usa i glifi estratti
esclusivamente dalle mani di training per comporre altri valori/semi; non usa
pixel delle mani di validazione/test. I fotogrammi reali di training coprono
27 codici e 12 valori: il dieci usa un font sintetico Arial. I 52 codici sono
quindi coperti nel dataset, ma **non da 52 carte reali indipendenti**.

Il primo esperimento aveva una divisione diversa e replay con soli font di
sistema. È stato scartato dopo la verifica dell'app: la metrica standard YOLO
con più etichette per indice sovrastimava le letture utili. Nel secondo esperimento
la mano a 370–390 s è passata al training; il test a 400–450 s è rimasto escluso
da entrambi gli esperimenti.

## Addestramento

Ambiente isolato `.venv-training`, Python 3.12, PyTorch 2.8.0 CUDA 12.8,
Ultralytics 8.3.200, ONNX 1.18.0, RTX 4050 Laptop da 6 GB.

Base YOLO11n già addestrata sulle 52 classi:

- Repository: `shrimantasatpati/yolov11_playing_cards_detection` su Hugging Face.
- Revisione: `7b8e6a71f0392544624dfc0b67730e679ece19ee`.
- File: `detect/yolo11n_playing_cards/weights/best.pt`.
- SHA-256: `2617719f994cbb91e974c9f3c3a7f63e83a5cd0d9004342636099c79260260b6`.

Fine-tuning dei livelli successivi al backbone congelato: AdamW, batch 32,
immagini 640×640, massimo 20 epoche, patience 6, seed 195129. Nessuna inversione
speculare, mosaic o rotazione dei simboli. Export ONNX FP32, opset 12, input
statico quadrato coerente con l'app.

`training_validator.py` seleziona il checkpoint tramite **F1 micro delle letture
effettive**: una sola identità per indice, score ≥0,60, margine ≥0,15,
NMS tra classi e tutte le false letture conteggiate. La validazione usa lo stesso
padding quadrato dell'app, invece di una variante rettangolare.

I report standard del framework restano disponibili, ma non sostituiscono la
verifica delle identità nell'applicazione.

L'inferenza estende il ritaglio centrale con tile ad alta risoluzione quando
compaiono carte scoperte in altre posizioni, come la mano dell'avversario.
Per indici incerti può usare anche il confronto separato di valore e seme con
glifi composti dai soli esempi sintetici del training: richiede correlazione
almeno 0,90 per entrambi e il margine fra classi del riconoscitore a simboli.
Non sovrascrive una lettura neurale già confermata. `decision_source` distingue
`model` da `training_symbol_references`; i relativi score non sono probabilità
calibrate e non vanno confrontati come tali.

Questa parte dell'inferenza è stata corretta dopo aver esaminato un primo esito
del controllo finale. Le mani sono rimaste fuori dall'addestramento dei pesi,
ma il controllo non è più un benchmark intatto: serve una registrazione nuova
per misurare una generalizzazione indipendente.

## Riprodurre il training

I pacchetti CUDA per Windows occupano alcuni GB; servono spazio e una GPU NVIDIA
compatibile. Nell'ambiente di questo PC sono già installati.

```powershell
uv venv --python 3.12 --managed-python .venv-training
uv pip install --python .venv-training/Scripts/python.exe torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv-training/Scripts/python.exe -r requirements-training.txt
```

Usare una cartella dataset nuova: lo script non sovrascrive dati già preparati.

```powershell
py prepare_table_dataset.py 'C:\Users\jhonn\Videos\Screen Recordings\Screen Recording 2026-11-04 195129.mp4' --output artifacts/table-195129/dataset-v2
.\.venv-training\Scripts\python.exe train_table_model.py --dataset artifacts/table-195129/dataset-v2 --epochs 20
py evaluate_table_model.py 'C:\Users\jhonn\Videos\Screen Recordings\Screen Recording 2026-11-04 195129.mp4' --split val
py evaluate_table_model.py 'C:\Users\jhonn\Videos\Screen Recordings\Screen Recording 2026-11-04 195129.mp4' --split test
```

Il checkpoint iniziale viene scaricato dalla revisione fissata e verificato.
I video e i fotogrammi non vengono caricati online. Il runtime dell'app non
richiede PyTorch, CUDA o Ultralytics: usa OpenCV DNN su CPU.

I pesi esportati sono `models/pokerstars.onnx`, con classi e checksum nel
manifest dedicato. I pesi restano locali ed esclusi da Git. Sono derivati da
Ultralytics YOLO11: si applicano le condizioni AGPL-3.0; non sono un modello
originale addestrato da zero.

## Usare il risultato

`Avvia-Video-PokerStars.cmd` apre la registrazione con annotazioni; Esc interrompe.
Si può trascinare un altro percorso video come primo argomento, ma la
calibrazione rimane specifica per questo layout.

```powershell
py recognize.py --video 'PERCORSO_VIDEO.mp4' --detector model --profile pokerstars --preview --fps 5 --output artifacts/pokerstars-video
```

Per lo schermo, selezionare l'area di gioco con gli stessi limiti e proporzioni
della registrazione, escludendo browser e barre del desktop:

```powershell
py recognize.py --screen --select-region --detector model --profile pokerstars --no-preview --output artifacts/pokerstars-live
```

Se si abilita `--preview` durante la cattura schermo, tenere la finestra fuori
dall'area acquisita, ad esempio su un secondo monitor: altrimenti copre il gioco.
Un layout differente o carte fuori dall'area calibrata richiedono un'altra verifica.
I pulsanti della registrazione sono tagliati in basso: non è una prova del
riconoscimento delle carte sotto qualsiasi sovrapposizione di controlli.

## Risultati del controllo applicativo

Training completato in 18 epoche, con arresto anticipato e checkpoint scelto
tramite F1 micro. La verifica delle letture usa score e margini di produzione,
identità esatta e IoU dell'indice almeno 0,30 (box annotati con margine).

| Controllo | Prima, modello generale su tutta l'immagine | Profilo finale | False letture del profilo finale |
|---|---:|---:|---:|
| Validazione, 8 fotogrammi | 14/33 | 33/33 | 0 |
| Controllo finale, 6 fotogrammi | 5/15 | 14/15 | 0 |

Le quantità sono apparizioni di indici, con carte ripetute tra fotogrammi,
non carte tutte diverse. Rimane non confermato un indice sovrapposto del 3 di
fiori dell'avversario. Le letture dell'asso di fiori sono recuperate dal
riconoscitore composizionale dei glifi di training, non dal solo output neurale.

La prima verifica neurale aveva perso l'asso di fiori e il ritaglio escludeva
le carte dell'avversario. Le correzioni dell'inferenza sono state valutate sugli
stessi casi: non presentare queste percentuali come accuratezza su un video nuovo.
Per quella misura serve una registrazione indipendente con lo stesso layout.

Report e immagini sono in `artifacts/table-195129/final-evaluation/`.
Il tempo del solo riconoscimento nel controllo finale è stato circa 0,39 s
mediano e 0,66 s al 95° percentile su CPU; esclude cattura e visualizzazione.
Il numero di tile può aumentare quando compaiono altre mani: non è una garanzia
di latenza massima sotto un secondo su ogni fotogramma o su ogni PC.
