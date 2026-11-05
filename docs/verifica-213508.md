# Verifica indipendente 213508

Nota successiva: per il nuovo addestramento (`miglioramento-carte.md`) il tratto
fino a 300s entra nel training e il fotogramma a 540s nella validazione. Questo
documento conserva i risultati della versione precedente. La registrazione non
e piu una verifica indipendente della nuova versione.

Video di 775,53 secondi, 1778 x 982, 30 fps. Annotazioni manuali e hash
della sorgente in `datasets/table-213508.json`. Tredici campioni a intervalli
di un minuto, con quattro schermate senza carte scoperte. Nessuna modifica a
pesi, simboli, soglie o ritaglio in seguito alla lettura di questa registrazione.
Rimane quindi un controllo indipendente del profilo attuale; i singoli campioni
non rappresentano l'accuratezza sull'intero video.

Il profilo PokerStars riconosce correttamente 26 delle 28 apparizioni di indici.
Le due letture errate riguardano entrambe il 10 di quadri: a 120 secondi viene
letto QD; a 540 secondi viene letto JD. Non ci sono ulteriori carte mancate o
false letture. Nei quattro campioni senza carte non sono rilevati indici.
Precisione e richiamo sul campione: entrambi 92,86%. Il modello generale su
immagine intera riconosce 15/28 indici, con tre false letture.

Confronto per identita esatta e IoU del box dell'indice almeno 0,30. I box sono
stati controllati sul layout attuale (circa +2 pixel in x e -1 in y rispetto
alla registrazione 211955). I fotogrammi JPEG servono alla revisione umana;
l'inferenza e eseguita sui fotogrammi decodificati direttamente dal video.

Solo riconoscimento su CPU: mediana 374 ms, percentile95 394 ms. Sono esclusi
cattura e anteprima; non e una garanzia sulla latenza massima live.

Questo video non richiede un ritaglio manuale. Fornisce esempi reali del 10
utili a un successivo addestramento. Se usato per addestrare o correggere la
pipeline, non dovra piu essere presentato come verifica indipendente della
versione risultante.

Report con confronti e immagini annotate: `artifacts/table-213508/evaluation/`.
Per riprodurre:

```powershell
py evaluate_table_model.py "C:\Users\jhonn\Videos\Screen Recordings\Screen Recording 2026-11-04 213508.mp4" --annotations datasets/table-213508.json --split test --output artifacts/table-213508/evaluation
```

Per l'anteprima:

```powershell
.\Avvia-Video-PokerStars.cmd "C:\Users\jhonn\Videos\Screen Recordings\Screen Recording 2026-11-04 213508.mp4"
```
