# Cattura e allineamento della finestra

Il riconoscitore riceve i fotogrammi della sorgente selezionata con «Scegli
sorgente». Non fotografa la pagina HTTP né il suo pannello di anteprima.
`copySourceFrame` copia il video in un canvas non visualizzato, conservando
le proporzioni, e invia quel buffer al server. La dimensione CSS
dell'anteprima non modifica l'immagine analizzata.

Selezionando la finestra del gioco si può consultare un'altra finestra mentre
la cattura continua. Selezionando lo schermo intero si acquisisce invece ciò
che appare su quello schermo. La disponibilità dei fotogrammi di una finestra
minimizzata dipende dal sistema: lasciare aperta la finestra del gioco.

## Correzione del layout desktop a sei posti

Lo screenshot fornito il 6 novembre alle 14:06:38 mostrava un tavolo desktop
a sei posti, precedentemente interpretato con le coordinate del tavolo browser.
Il problema riprodotto dipendeva dall'allineamento e dal profilo geometrico.

`table_profiles.py` identifica il bordo del tavolo, ne stima scala e posizione
e distingue i desktop a sei e nove posti. `capture_alignment.py` ricostruisce
il viewport anche quando una parte si trova fuori dalla cattura, aggiungendo
margini senza deformare le carte. Il profilo `pokerstars-desktop-six` riusa il
modello di carte desktop già disponibile e ha cinque posizioni avversarie.

Gli spostamenti successivi richiedono tre rilevamenti coerenti. Quando si
perdono i riferimenti dopo una registrazione valida, le nuove letture e le
probabilità vengono sospese. L'interfaccia mostra lo stato di allineamento.
Il sistema riprende quando ritrova il tavolo; non garantisce il riconoscimento
di temi diversi, finestre coperte o immagini prive di dettaglio sufficiente.

## Verifiche

`tests/fixtures/themis-window.png` deriva dall'anteprima nello screenshot
fornito dall'utente, non dal flusso originale della cattura. Riproduce quindi
anche la perdita di dettaglio dell'anteprima. Il test riconosce 3C, KS, AH
sul board, 2C e 2D in mano e due avversari con carte coperte. Verifica inoltre
ridimensionamenti, spostamenti, perdita dei riferimenti e ripristino.

Le regressioni sulle registrazioni precedenti conservano 136/136 carte
visibili e 392/392 slot nel desktop a nove posti e 90/90 campi OCR nei casi
browser selezionati. Sono casi di sviluppo già osservati, non una misura
indipendente della precisione su qualsiasi finestra. La suite Python contiene
155 test; la suite dell'interfaccia ne contiene 16.

Dopo questo aggiornamento riavviare il processo Python e ricaricare la pagina:
ricaricare soltanto il browser non aggiorna il codice del server già avviato.

## Animazione delle carte vincenti a nove posti

Una successiva verifica dal vivo ha riprodotto uno sfarfallio delle letture
allo showdown. Il client alza e abbassa le carte vincenti: nell'esempio il 5H
si sposta di 21 pixel, riducendo la sovrapposizione degli indici sotto la
soglia del filtro temporale. Il modello riconosce ancora la carta, ma la
conferma delle cinque letture consecutive riparte da zero.

Il server ora assegna lo slot prima della conferma temporale. Lo stesso
codice nello stesso slot può confermarsi durante l'animazione; rimangono
necessari il riconoscimento attuale, cinque letture consecutive e l'intervallo
minimo previsto. Non vengono conservate carte scomparse o con codice cambiato.
I rilevamenti fuori dagli slot mantengono il confronto tramite sovrapposizione.

Le fixture `nine-showdown-rest.png` e `nine-showdown-raised.png` provengono
dalla finestra del tavolo durante questa verifica, senza interazioni di gioco.
Il test con il modello reale verifica il board 4D, 5H, JH, 10C, QD durante
l'alternanza delle due posizioni. Un test HTTP verifica anche l'ordine delle
operazioni nel server. Sono regressioni specifiche, non una certificazione
della lettura di tutte le carte in qualunque condizione.

## Numero variabile di avversari

Il conteggio conferma le coppie di carte coperte nelle posizioni riconosciute;
non equivale al numero di posti occupati né alla capienza massima. Un tavolo
a nove posti con cinque giocatori non richiede un profilo diverso se conserva
la stessa disposizione grafica. Dopo un fold il conteggio richiede nuovamente
le cinque osservazioni previste; una posizione incerta mantiene il conteggio
in attesa anziché inventare un valore.

Il tracker accetta da una a nove posizioni avversarie (tavoli da due a dieci
posti), senza posizioni duplicate, e azzera la conferma quando cambiano le
posizioni monitorate. UI ed equity usano `opponents.max_opponents`, fornito dal
rilevatore, invece di limitarsi ai due massimi fissi precedenti.

Questo estende la gestione dei dati, non aggiunge geometrie mai osservate:
la lettura grafica automatica rimane calibrata sui layout browser a sei posti,
desktop a sei posti e desktop a nove posti. Un layout distinto a cinque,
otto o dieci posti richiede riferimenti reali per le posizioni di carte e HUD.
Le carte avversarie scoperte allo showdown sono una limitazione distinta dal
conteggio delle coppie coperte: non si deve presentare questo conteggio come
un riconoscimento universale di tutti i giocatori seduti.
