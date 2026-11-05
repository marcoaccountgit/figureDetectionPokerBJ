# Aggiornamento del riconoscitore PokerStars

Nuovo addestramento GPU completato in 11 epoche, ripartendo dal checkpoint
precedente e conservando i suoi esempi. Modello installato:
`f87f44d12591494799e22b32eb178e5112509e876f027d0ce0d42b2656c52c81`.
Il modello generale della webcam non cambia.

La preparazione aggiunge 56 fotogrammi reali verificati dai tratti iniziali
(fino a 300s) delle registrazioni 211955 e 213508. Il glifo reale del 10 di
fiori a 300s del video 211955 sostituisce il vecchio font di ripiego nei
156 esempi sintetici delle 52 classi. Entrambe le cifre del 10 sono conservate.
Il dataset finale contiene 360 immagini di training, 9 di validazione e
6 del vecchio test. Inventario, hash e sorgenti in
`artifacts/table-improvement/dataset/manifest.json`.

Validazione per scegliere il checkpoint: gli 8 vecchi fotogrammi piu il
fotogramma 213508 a 540s (10D e 5S), che non entra nel training. Il checkpoint
installato e quello dell'epoca 11, con 35/35 letture corrette nella validazione
neurale alle soglie di produzione. Il training usa F1 micro con singola classe
per proposta e input quadrato, coerenti con l'inferenza. Nei pareggi viene
registrata l'ultima epoca, come nel salvataggio di Ultralytics.

## Confronto prima e dopo

Stessi fotogrammi grezzi e stesse soglie per entrambe le versioni; matching per
identita e box dell'indice con IoU >=0,30.

| Gruppo | Prima | Nuovo | False letture prima / nuove |
|---|---:|---:|---:|
| Fotogrammi di adattamento, 12 | 20/23 | 23/23 | 3 / 0 |
| Validazione aggiunta, 1 | 1/2 | 2/2 | 1 / 0 |
| Fotogrammi esclusi dal nuovo training, 10 | 37/40 | 39/40 | 1 / 1 |
| Vecchi ritagli di validazione e test, 14 | 46/46 | 46/46 | 0 / 0 |

I gruppi di adattamento e validazione non misurano generalizzazione.
I dieci fotogrammi esclusi sono quelli del video 211955 da 480s e del video
213508 da 360s, escluso 540s. Non sono entrati nel nuovo addestramento, ma
erano gia stati osservati durante lo sviluppo: non sono un benchmark mai visto.
Le apparizioni includono carte ripetute e non coprono tutte le 52 identita.
La sorgente originale 195129 non e piu disponibile: il controllo precedente
usa i ritagli etichettati conservati, senza verificare i tile degli avversari.

I 10C e 10H del training e i due 10D verificati ora sono corretti. Il caso
ancora errato e 8S letto 8C a 780s nel video 211955. Risolte le mancate letture
di QS a 660s e KS a 720s nello stesso video.

Nel confronto sui dieci fotogrammi esclusi: mediana 396ms, percentile95 407ms
per il solo riconoscimento CPU. Cattura e visualizzazione escluse; nessuna
garanzia sulla latenza massima live. 36 test automatici superati.

## Uso e riproduzione

`Avvia-Video-PokerStars.cmd` apre ora la registrazione 213508 con il modello
aggiornato. Il riconoscimento live con `--profile pokerstars` usa gli stessi
pesi. Nessun pulsante viene letto o azionato.

```powershell
py prepare_improvement_dataset.py "$env:USERPROFILE\Videos\Screen Recordings"
.\.venv-training\Scripts\python.exe train_table_model.py --dataset artifacts/table-improvement/dataset --warm-start artifacts/training/pokerstars-1951292/weights/best.pt --epochs 16 --learning-rate 0.0005 --output-dir artifacts/table-improvement/candidate --run-name pokerstars-improved
py evaluate_improvement.py "$env:USERPROFILE\Videos\Screen Recordings"
```

La preparazione rifiuta di sovrascrivere un dataset esistente. Per ripetere
l'esperimento scegliere un nuovo `--output` e passarlo come `--dataset`.
I candidati non sostituiscono automaticamente il modello installato.
Report dettagliato e immagini: `artifacts/table-improvement/evaluation/`.
Backup della versione precedente: `artifacts/table-improvement/previous-model/`.
