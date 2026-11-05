# Verifica registrazione 211955

Nota successiva: il tratto iniziale fino a 300s viene ora usato per il nuovo
addestramento descritto in `miglioramento-carte.md`. Le misure sotto documentano
la versione precedente; il video completo non e piu un test indipendente della
nuova versione.

Registrazione di 13 minuti e 25 secondi, 1764 x 984. Annotazioni manuali e
SHA-256 della sorgente in `datasets/table-211955.json`.

Il tavolo mantiene posizione e scala della precedente registrazione, ma aggiunge
controlli in basso. Il ritaglio normalizzato sull'intera altezza tagliava i valori
delle carte comuni. Il profilo ora usa le dimensioni di riferimento 1762 x 840
e scala entrambe le coordinate con la larghezza. Serve acquisire il tavolo
allineato all'origine, senza margini aggiunti sopra o lateralmente. Non e un
localizzatore universale di finestre. I profili senza dimensioni di riferimento
mantengono il comportamento precedente.

Nessun aggiornamento dei pesi o dei riferimenti dei simboli. Prima della modifica
sono stati salvati manifest e predizioni in `artifacts/table-211955/baseline*`.
Il tratto fino a 300 secondi serve alla diagnosi del layout; i quattro campioni
da 480 secondi sono stati valutati dopo aver fissato la correzione, senza usarli
per altre modifiche. Le etichette sono state lette manualmente prima della prova.

| Campioni | Prima: corretti / attesi | Dopo: corretti / attesi | Dopo: false letture |
|---|---:|---:|---:|
| 6 iniziali, inclusi 2 senza carte | 2/19 | 17/19 | 2 |
| 4 successivi | 8/18 | 15/18 | 1 |

Confronto per identita esatta e sovrapposizione del box dell'indice >= 0,30.
Le 37 apparizioni includono carte ripetute: non sono 37 carte distinte e non
misurano l'accuratezza sull'intero video. Nei campioni negativi nessun pulsante
e stato letto come carta.

Errori rimasti: a 300s i due 10 diventano Q; a 660s manca QS; a 720s manca KS;
a 780s 8S viene letto 8C. Servono esempi reali dei 10 e maggiore copertura dei
semi per un successivo addestramento, conservando un nuovo controllo separato.
Questa registrazione e utile e non richiede ulteriori ritagli manuali.

Mediana del solo riconoscimento sul controllo successivo: 361 ms, percentile95
368 ms, CPU. Cattura e visualizzazione escluse; nessuna garanzia di latenza
massima sotto un secondo.

35 test automatici superati, incluso il controllo che l'aggiunta dei pulsanti
in basso non sposti il ritaglio. La ripetizione del controllo sul vecchio video
195129 non e stata possibile: il file non e piu presente nel percorso originale.

Report riproducibili (per il tratto iniziale sostituire `test` con `val`):

```powershell
py evaluate_table_model.py "C:\Users\jhonn\Videos\Screen Recordings\Screen Recording 2026-11-04 211955.mp4" --annotations datasets/table-211955.json --split test --output artifacts/table-211955/evaluation
```

Anteprima del video con il profilo corretto:

```powershell
.\Avvia-Video-PokerStars.cmd "C:\Users\jhonn\Videos\Screen Recordings\Screen Recording 2026-11-04 211955.mp4"
```
