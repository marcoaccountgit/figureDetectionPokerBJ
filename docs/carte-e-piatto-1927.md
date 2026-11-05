# Carte 192703/192744 e piatto per fase

## Correzione delle carte

Negli screenshot forniti la geometria del tavolo e corretta. Nel 192703 la
mano e 2D/3C: il modello proponeva il secondo indice ma non lo accettava,
e i riferimenti dei simboli non superavano soglia/margine. Nel 192744 la
mano e 4C/AS: il modello leggeva AC al posto di 4C e il controllo dei simboli
restava incerto. Non si tratta dello spostamento verticale corretto prima.

Sono stati aggiunti riferimenti visivi etichettati manualmente per i ranghi
3/4 e il seme C, estratti dagli screenshot alle scale nativa e canonica.
Sono in `assets/pokerstars-reviewed-symbols`, con sorgenti e hash nel file
`provenance.json`. Sono campioni di adattamento, non un test indipendente.

Il classificatore originale viene sempre provato per primo. I nuovi
riferimenti entrano solo quando la lettura originale non e sufficientemente
forte: non riducono il margine delle letture di picche gia affidabili. I
punteggi minimi 0.90, i margini e le cinque letture consecutive restano
invariati. Non sono stati modificati i pesi ONNX o i riferimenti di training
originali. Le diagnosi indicano `reviewed_symbol_references` quando usato.

Il percorso HTTP conferma 2D/3C e 4C/AS negli screenshot nuovi, oltre ai quattro
precedenti 190551, 190655, 155720 e 162911. In particolare rimangono corrette
le precedenti mani 4S/7H e 3S/4C. La verifica ripete le anteprime estratte:
non equivale a riprodurre tutta la cattura originale a piena risoluzione.

Il confronto su 35 fotogrammi conservati di tre registrazioni usa identita e
IoU >=0.30, applicando lo stesso allineamento prima/dopo. Il report e in
`artifacts/hand-fix-1927/regression.json` e si riproduce con:

```powershell
.venv-training/Scripts/python.exe evaluate_reviewed_symbols.py
.venv-training/Scripts/python.exe evaluate_alignment_screenshots.py
```

## Piatto totale e raccolto al centro

La lettura OCR locale distingue ora due valori indipendenti:

- `pot`: il totale esplicitamente mostrato da Pot nel riquadro centrale alto;
- `collected_pot`: il valore scritto accanto alle chips raccolte sotto il board.

Non vengono sommati: il primo puo gia includere le puntate ancora davanti
ai giocatori. Non vengono inferiti importi dal colore o dal numero delle
chips, ne sommati automaticamente piatti laterali. Piu etichette numeriche
nel ritaglio raccolto producono una lettura non disponibile, non una somma.
La calibrazione riguarda le BB visualizzate nei video. Non viene inventato
un valore in euro quando il grande buio in euro non e noto.

## Flop, turn e river

Per ogni mano `street_pots` conserva, separatamente per flop/turn/river:

- `first_total` e `first_collected`: prime letture confermate disponibili;
- `last_total` e `last_collected`: ultime letture confermate di quella fase;
- i timestamp monotoni delle singole letture in campi con suffisso `_at`.

La fase e confermata su due osservazioni OCR, come gli importi. I valori
iniziali non sono sovrascritti dalle puntate successive. La progressione non
torna indietro per una carta temporaneamente mancata; non sono inventate
fasi precedenti se la cattura inizia al turn o al river. Il cambio del numero
della mano azzera questi dati. Anche le snapshot gia restituite restano immutate.

La prima lettura confermata puo avvenire dopo l'effettivo passaggio di fase
se il tavolo e coperto o l'OCR non legge subito il valore: i timestamp
descrivono cio che e stato osservato, non una cronologia ricostruita.

Nel pannello **Lettura tavolo** sono visibili Piatto totale, Raccolto al centro
e la riga dei primi totali confermati per Flop / Turn / River. I valori
illeggibili o delle fasi non osservate restano vuoti.

Per rendere visibile il valore senza aprire i dettagli, un riquadro dedicato
**Piatto al centro** e sempre presente sopra l'anteprima. Mostra il raccolto
corrente accanto al totale del tavolo e l'ultimo raccolto confermato di ciascuna
fase. Non sostituisce un raccolto mancante con il totale: indica invece
**Importo al centro in lettura**. La riga nei dettagli mantiene la distinta
funzione di mostrare i primi totali di fase. Valori zero confermati sono
mostrati come zero, e non come letture mancanti.

## Verifiche

```powershell
.venv-training/Scripts/python.exe evaluate_table_observer.py
.venv-training/Scripts/python.exe -m unittest discover -s tests
node --test tests/test_browser_ui.cjs
```

La verifica OCR e estesa a 18 fotogrammi e 90 campi annotati dei video gia
caricati, inclusi importi del piatto nelle tre fasi. I casi sono selezionati
e in parte usati durante lo sviluppo: non sono un benchmark indipendente.
I test controllati coprono cambi fase, aggiornamenti di puntata, valori non
letti, azzeramento alla nuova mano e separazione dei due importi nel frontend.

Per caricare i riferimenti nuovi e il tracciamento dei piatti occorre
riavviare il server del bot e ricaricare il pannello dopo aver scaricato le
eventuali registrazioni ancora in memoria.

## Correzione successiva: screenshot 203254

La mano KSpade/JDiamond (KS/JD) era localizzata correttamente, ma il primo
indice rimaneva incerto: confidenza neurale circa 0.31 e punteggio del seme
circa 0.888 sul piccolo ritaglio nativo. Il recupero degli indici saltava
qualsiasi riquadro gia presente, anche se non accettato. Il ritaglio calibrato
a larghezza 1762 legge invece KS con entrambi i punteggi oltre 0.90.

Il recupero ora salta solo gli indici gia accettati. Le proposte incerte sono
ricontrollate; una lettura forte le sostituisce senza creare duplicati e
conservando candidato/confidenza neurale nella diagnosi. Se il controllo
rimane incerto, la proposta originale non viene modificata. Non sono stati
aggiunti riferimenti o abbassate soglie per questo screenshot.

Il valutatore HTTP delle anteprime ora copre sette screenshot: tutti i
risultati precedenti restano conformi e la nuova mano conferma KS/JD dopo
cinque letture. Il controllo su 35 fotogrammi precedenti resta a 111 indici
corretti senza falsi positivi con il recupero supplementare. Suite corrente:
110 test Python e 6 frontend superati. Sono verifiche su campioni conservati,
non una garanzia sull'intera cattura live.
