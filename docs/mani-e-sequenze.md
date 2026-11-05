# Altre mani e conferma su fotogrammi consecutivi

Le annotazioni aggiuntive sono `datasets/table-211955-extra.json` e
`datasets/table-213508-extra.json`: 29 istanti verificati nei primi 300 secondi
dei due video, con carte comuni, mani del giocatore e schermate senza indici
scoperti. Non rappresentano 29 mani distinte. Il fotogramma coperto dal menu
Windows a 150s del primo video e escluso dalle nuove annotazioni.

Ogni annotazione di training viene estesa fino a cinque fotogrammi a 0,2s
di distanza, solo se tutti gli spazi degli indici, occupati o vuoti, rimangono
praticamente invariati. Il controllo degli spazi vuoti evita che una nuova carta
del turn venga inserita senza etichetta accanto a un flop invariato.
Il primo tentativo controllava solo gli indici annotati: quattro campioni sono
stati scartati nel controllo successivo e quel candidato non e stato installato.

Dataset definitivo: `artifacts/sequence-improvement/dataset-v2`, con 135 nuovi
fotogrammi, 495 immagini totali di training, 9 di validazione e 6 del precedente
test. Il replay sintetico e i precedenti split sono conservati. Il training
reale copre 45 identita; mancano esempi reali di 10S, 2H, 9S, KH, KS, QC e QS.
Queste classi hanno esempi sintetici e alcune rimangono nei campioni di verifica.
Gli hash delle sorgenti, le annotazioni e l'inventario sono nel manifest del
dataset. Non sono state usate letture del modello come etichette vere.

## Conferma temporale

`TemporalCards`, in `temporal_cards.py`, richiede che una lettura accettata del
fotogramma corrente abbia lo stesso codice e posizione di almeno una lettura
nei due fotogrammi precedenti, con sovrapposizione IoU >=0,30 e distanza nel
tempo non superiore a 650ms. Una stessa osservazione precedente non puo
confermare due indici distinti nello stesso fotogramma.

La conferma e automatica per video e cattura schermo con profilo PokerStars
a frequenza richiesta di almeno 2fps; funziona anche con quel profilo sulla
webcam. Per la webcam generale rimane opzionale. Le immagini singole e i flussi
automatici sotto 2fps mantengono il riconoscimento per singolo fotogramma.
`--temporal` la abilita esplicitamente, `--no-temporal` la disabilita.

La prima osservazione rimane in attesa. Con campionamento regolare a 5fps e
letture coerenti, la seconda arriva 200ms dopo. Il costo dell'inferenza e della
cattura si aggiunge a questa attesa; non viene garantito un massimo di un
secondo su qualsiasi PC. Se il tempo tra osservazioni supera 650ms, la vecchia
lettura scade e occorre confermare di nuovo.

Sono emesse esclusivamente carte presenti e gia accettate nel fotogramma
corrente: quelle scomparse non sono riproposte dalla memoria. Un cambio di
codice non viene sostituito con il vecchio codice. Riavvolgimento del video e
cambio delle dimensioni azzerano lo storico. Un errore persistente puo comunque
essere confermato: il filtro non sostituisce l'addestramento.

Nei log `raw_cards` conserva le letture originali; `cards` contiene il risultato
con la conferma. `frame_accepted`, `temporal_confirmed` e `temporal_support`
permettono di distinguere lettura neurale e conferma nel tempo.
`confirmation_span_ms` misura la distanza tra le osservazioni di supporto,
non la latenza completa dalla comparsa reale della carta.

## Verifica e riproduzione

I dieci istanti esclusi dal nuovo training sono confrontati senza filtro per
misurare i nuovi pesi; sono casi gia osservati durante lo sviluppo, non un test
mai visto. I vecchi ritagli etichettati controllano le regressioni. La verifica
temporale usa cinque fotogrammi consecutivi attorno a ciascun istante, solo se
coerenti con l'annotazione manuale, piu una nuova sequenza di fold annotata
manualmente a 5fps (`datasets/table-213508-sequence.json`). Tutti questi campioni
rimangono fuori dal training. La prima osservazione e conteggiata separatamente
per rendere visibile il costo di avvio del filtro.

```powershell
py extend_table_dataset.py "$env:USERPROFILE\Videos\Screen Recordings" --annotations datasets/table-211955-extra.json datasets/table-213508-extra.json --replay artifacts/table-improvement/dataset --output artifacts/sequence-improvement/dataset-v2
.\.venv-training\Scripts\python.exe train_table_model.py --dataset artifacts/sequence-improvement/dataset-v2 --warm-start artifacts/training/pokerstars-improved/weights/best.pt --epochs 8 --learning-rate 0.0002 --output-dir artifacts/sequence-improvement/candidate-v2 --run-name pokerstars-sequences-clean
py evaluate_improvement.py "$env:USERPROFILE\Videos\Screen Recordings" --previous artifacts/sequence-improvement/previous-model --candidate artifacts/sequence-improvement/candidate-v2 --output artifacts/sequence-improvement/evaluation --extra-annotations datasets/table-211955-extra.json datasets/table-213508-extra.json
py evaluate_sequences.py "$env:USERPROFILE\Videos\Screen Recordings" --model-dir artifacts/sequence-improvement/candidate-v2
```

La preparazione rifiuta di sovrascrivere un dataset esistente: per ripetere
scegliere un nuovo percorso di output e usarlo nel training.
Backup dei pesi precedenti: `artifacts/sequence-improvement/previous-model/`.

## Risultati della versione installata

Training corretto terminato dopo 7 epoche, checkpoint scelto dalla validazione
con 35/35 indici corretti. SHA-256 del modello installato:
`38cedc3f660d6168a5bac71426925dd791be34e8cfaedbb0105721f42d91d915`.
48 test automatici superati e prova del comando effettivo con tre fotogrammi:
prima osservazione in attesa, due successive confermate, letture 10D e 3D.

| Confronto dei soli pesi | Prima | Nuovo |
|---|---:|---:|
| 29 nuove annotazioni, indici stazionari leggibili | 85/86 | 86/86 |
| 10 istanti esclusi dal nuovo training | 39/40 | 39/40 |
| 14 vecchi ritagli di validazione e test | 46/46 | 46/46 |

Le nuove annotazioni sono dati di adattamento, non una misura indipendente.
Per il controllo delle carte degli avversari usare il supplemento
`datasets/table-213508-extra-eval.json` al posto di `table-213508-extra.json`
nel comando di valutazione. Il supplemento non modifica le etichette del
training. Include sei indici fuori dal ritaglio; una carta vista di taglio
durante la rotazione a 90s non e valutata perche l'indice e troppo compresso.
Il report definitivo e in `artifacts/sequence-improvement/evaluation-complete/`.

Sui 62 fotogrammi consecutivi esclusi dal training, prima della conferma
temporale le letture corrette passano da 203/216 a 211/216. Le false letture
e le mancate letture sono conteggiate separatamente nel report.
Escludendo il primo fotogramma di ciascuna sequenza (in attesa per scelta),
la versione nuova conferma 170/174 apparizioni, contro 163/174 con i vecchi
pesi. Restano quattro letture errate ripetute di 8S come 8C: in queste sequenze
il filtro temporale non le corregge. Nei quattro fotogrammi successivi al fold
non vengono emesse carte scomparse.
Report: `artifacts/sequence-improvement/sequences/report.json` e confronto
precedente in `sequences-before/report.json`.

Il filtro aggiunge al massimo 0,20ms nel campione. Il tempo del riconoscimento
su CPU nella verifica delle sequenze e circa 395ms mediano e 414ms al
percentile95; questi valori escludono cattura, decodifica e attesa di campionamento.
Una prova separata di replay cadenzato a 5fps, con un solo modello caricato,
misura 336, 344 e 342ms dalla prima acquisizione alla prima conferma completa
di cinque carte. Include decodifica, inferenza, filtro e attese; esclude caricamento
del modello, cattura reale dello schermo e visualizzazione. E una prova su una
scena stabile, non una garanzia per ogni mano o PC.
Dettagli: `artifacts/sequence-improvement/latency-replay.json`.

Per provare il video con conferma temporale:

```powershell
.\Avvia-Video-PokerStars.cmd
```

Per il gioco live selezionare l'intera area del tavolo, allineata all'origine
del ritaglio previsto dal profilo:

```powershell
py recognize.py --screen --select-region --detector model --profile pokerstars --fps 5 --no-preview --output artifacts/pokerstars-live
```

Se si usa `--preview`, tenerla fuori dall'area acquisita. Il programma riconosce
solo le carte; non aziona controlli del tavolo.
