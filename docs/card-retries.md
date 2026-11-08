# Recupero delle carte incerte

Il riconoscitore conserva la lettura normale e il confronto separato fra numero
e seme. Se resta una previsione neurale rifiutata, controlla che il ritaglio
contenga una faccia bianca, ingrandisce il solo indice e riprova i riferimenti
dei due simboli. Restano richiesti i punteggi e i margini precedenti.

Se il confronto dei simboli non basta, esegue al massimo una seconda inferenza
su un ritaglio locale. Una proposta viene accettata soltanto con le soglie
normali, sovrapposizione con l'indice originale e accordo sull'identità fra
le due inferenze. Le letture già accettate non attivano il secondo passaggio.

Una cache limitata a 2048 coppie di simboli evita di ripetere confronti identici.
La chiave contiene i due glifi normalizzati e il colore dell'inchiostro;
ogni fotogramma deve comunque fornire i propri simboli. Non vengono memorizzate
predizioni per posizione, e le risposte restituite sono copie indipendenti.

Il singolo fotogramma che richiede una seconda inferenza può costare di più.
Il vantaggio sulla scansione continua va misurato includendo la conferma
temporale e la memoria: una carta recuperata può evitare inferenze ripetute
nei fotogrammi successivi.

## Verifica riproducibile

`evaluate_card_retries.py` confronta una copia del riconoscitore precedente
con quello corrente, alternando l'ordine di esecuzione. Usa le annotazioni di
`datasets/desktop-200950.json`, limita i timestamp all'intervallo revisionato
e misura anche i tentativi aggiuntivi. L'opzione `--reviewed-frames` usa i
fotogrammi già estratti dallo stesso video, evitando il costo delle ricerche
nel file video. Decodifica e allineamento sono esclusi dai tempi del rilevatore.

Il confronto comprende fotogrammi già impiegati per l'addestramento: non è una
stima indipendente dell'accuratezza sull'intero video. Il report conserva
risultati, tempi e aspettative per ogni campione, così da poter individuare
recuperi, regressioni e carte accettate erroneamente.

La fixture `tests/fixtures/six-8c5c-uncertain.png` riproduce il caso reale
8C/5C. I test verificano anche l'assenza di tentativi sui soli sfondi,
il rifiuto delle inferenze discordanti e l'invalidazione della cache quando
cambiano i simboli.

## Risultati del 7 novembre 2026

Video: `Screen Recording 2026-11-06 200950.mp4`, 48 fotogrammi annotati
a 960 e 1280 pixel, due passaggi per misurare i tempi (192 rilevazioni per versione).
Sono stati usati i JPEG già estratti dal video in `artifacts/desktop-200950/review`.

| Misura | Prima | Dopo |
| --- | ---: | ---: |
| Carte visibili corrette, un passaggio | 350/350 | 350/350 |
| Carte accettate erroneamente | 0 | 0 |
| Fotogrammi interamente corretti | 96/96 | 96/96 |
| Tempo medio del riconoscitore | 464,2 ms | 434,3 ms |
| Mediana | 405,6 ms | 372,4 ms |
| 95° percentile | 815,2 ms | 871,4 ms |

La media migliora del 6,4%; il percentile alto peggiora. Questi sono tempi
misurati sulla macchina con il bot attivo, non una garanzia sul singolo frame.
Nessuno dei campioni del video ha richiesto una seconda inferenza: su questo
insieme non c'è un miglioramento misurabile di accuratezza, già completa.
Report dettagliato: `artifacts/card-retry/comparison.json`.

Caso reale 8C/5C, ripetuto per 20 scansioni attraverso conferma temporale e memoria:

| Misura | Prima | Dopo |
| --- | ---: | ---: |
| Mano finale | 8C, carta incerta | 8C, 5C |
| Fotogrammi che eseguono il riconoscitore | 20/20 | 5/20 |
| Prima conferma di entrambe le carte | mai | quinto fotogramma |
| Tempo medio della scansione | 323,4 ms | 195,7 ms |

Su questo caso la media migliora del 39,5%. È una prova su un'immagine reale
stabile, non un replay di 20 fotogrammi diversi del video. Il risparmio deriva
dalla possibilità di usare la memoria dopo aver recuperato il 5C.
Report: `artifacts/card-retry/live-comparison.json`.
