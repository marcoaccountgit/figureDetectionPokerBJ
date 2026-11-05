# Cambio della mano del giocatore

Stato: implementato nel pannello browser con `hand_counter.py`.

## Regola concordata

Per il bot fold e conclusione del piatto chiudono entrambi la mano del giocatore.
La nuova coppia di carte in basso avvia il ciclo successivo, anche se le
identita sono uguali a quelle della mano precedente.

Il contatore parte da zero a ogni nuova acquisizione e aumenta quando le due
carte fisiche risultano presenti per almeno cinque osservazioni consecutive
distribuite su almeno 300 ms. La prima coppia confermata porta il totale a uno,
anche se l'acquisizione viene avviata nel mezzo di quella mano. Il totale e
locale alla sessione, non e il numero assoluto della mano PokerStars.

La presenza usa il bianco delle facce, il verde del panno e la geometria dei
due indici calibrata sui video. Non dipende dalla lettura di rango/seme: due
carte ancora visibili ma non riconosciute non chiudono il ciclo e possono
comunque aprire la prima mano. Il verde attorno ai ritagli aiuta a scartare
finestre bianche o schermate nere che coprono l'immagine.

La chiusura richiede che il panno torni visibile in entrambi i ritagli per
cinque campioni e almeno 300 ms. Non cambia il totale: abilita l'incremento
alla distribuzione successiva. Una sola carta mancante, un fotogramma ambiguo
o un semplice cambio di identita non chiudono la mano.

Un cambio di allineamento o una pausa oltre due secondi interrompe le prove
in corso ma conserva totale e ciclo gia aperto. Non vengono inventate mani
non osservate durante le pause. Dopo una mano persa interamente nella pausa,
il contatore puo sottostimare: per osservare ogni distribuzione occorre
mantenere la cattura continua. Una nuova sessione di acquisizione riparte da zero.

A ogni apertura/chiusura si azzera la verifica degli avversari. Dopo il ritiro
si azzera anche la memoria temporale delle identita. Il frontend aggiunge solo
**Mani rilevate: N**; stati tecnici, prove e transizioni restano nella diagnosi
JSON `hand_cycle`. Fermare l'acquisizione conserva il totale a video; scegliere
una nuova scheda avvia un nuovo contatore.

## Verifica sui materiali precedenti

- 35 PNG/JPEG annotati di 211955, 213508 e capture10: 35/35 concordanze sulla
  presenza/assenza delle due carte, comprese carte non riconosciute dal modello.
- 12 fotogrammi consecutivi della sequenza 213508 a 698.0-700.2 s:
  12/12 concordanze. Il contatore aumenta una sola volta. La sequenza include
  solo quattro campioni dopo il fold; la chiusura resta correttamente in attesa
  del quinto campione, non aggiunto artificialmente alla verifica del video.
- Test controllati verificano anche il ciclo completo presenza/ritiro/nuova
  distribuzione, carte identiche, letture mancanti, finestre bianche/nere,
  campioni troppo ravvicinati e nuove sessioni. Questi test non sono nuovi video.
- Il codice AAMS e l'ID di partecipazione restano uguali tra mani diverse nei
  campioni 213508 da 0 a 420 s: non sono utilizzati come contatori.

```powershell
.venv-training/Scripts/python.exe evaluate_hand_counter.py
.venv-training/Scripts/python.exe -m unittest discover -s tests
node --test tests/test_browser_ui.cjs
```

Report riproducibile: `artifacts/hand-counter/report.json`, con hash dei
fotogrammi e replay temporale. I dati sono campioni di sviluppo del layout
gia calibrato, non una verifica indipendente di ogni mano dell'intero video.
Non sono stati modificati o riaddestrati i pesi YOLO.
