# Valutazione probabilistica della decisione

Il pannello della mano include una valutazione aggiornata su ogni risposta
del server. Le indicazioni sono numeriche: non analizzano lo stile di gioco,
non interpretano un rilancio come prova di forza e non assegnano probabilità
arbitrarie al bluff. Non eseguono azioni sul tavolo.

## Dati e formule

`poker_advice.analyze_decision(equity, table_observation, hand_id)` è una funzione
pura, chiamata dal server dopo lo snapshot del servizio equity. L'output viene
aggiunto a `/frame` come `poker_advice`, separato dalla cache delle simulazioni:
cambiamenti di importi o pulsanti aggiornano quindi il consiglio anche con
carte e numero di avversari invariati.

Si usano esclusivamente:

- `equity.metrics.equity`: quota attesa del piatto, con intervallo Monte Carlo.
- `table_observation.pot`: totale mostrato dal tavolo, puntate già incluse.
- Importo esplicito del pulsante `call` in `available_actions_confirmed`.
- Identità della mano, fase, stato e anzianità della lettura.

Il piatto raccolto al centro non viene sommato al totale. Contributi del
giocatore, stack e puntate visibili non sono sostituiti al costo aggiuntivo
per vedere. Il parser supporta anche pulsanti su una riga, come `Vedi 12 BB`,
ma richiede un'unità esplicita. I pulsanti sono confermati su due osservazioni
OCR concordi distanti almeno 100 ms; vengono riverificati al cambio di fase,
di importo o di mano. Non sono trasformati in azioni eseguite.

```text
P = piatto prima della tua chiamata, inclusa la puntata avversaria
C = costo aggiuntivo della chiamata
e = equità stimata
Soglia richiesta = C / (P + C)
Margine = e - soglia
Valore atteso semplificato = e × (P + C) - C
```

Il modello confronta una chiamata con il passare adesso, senza sottrarre
nuovamente fiches già versate. Usa l'equità multiway con quote frazionarie
dei pareggi, senza sostituirla alla sola probabilità di vittoria.

## Indicazioni

- **VEDI**: limite inferiore dell'intervallo di equità sopra la soglia.
- **PASSA**: limite superiore sotto la soglia.
- **MARGINE INCERTO**: la soglia attraversa o tocca l'intervallo.
- Se è confermata l'opzione gratuita, viene indicata la possibilità di
  passare il turno senza pagare. Non viene inventato un importo da puntare.
- Importi assenti, unità diverse, pulsanti ambigui, lettura scaduta, mano/fase
  diversa, chiamata superiore allo stack letto o piatti secondari segnalati
  producono attesa, senza numeri economici residui della situazione precedente.

Sono indicazioni condizionate al confronto semplificato, non probabilità che
la decisione sia corretta. Una stima progressiva viene marcata provvisoria.
Un intervallo Monte Carlo stretto non certifica le ipotesi economiche.

La spiegazione espandibile riporta vittoria, sconfitta, pareggi, forza attuale,
probabilità di essere dietro e miglioramenti; la distribuzione delle categorie
rimane nella sezione dedicata. Queste probabilità non vengono mediate, sommate
o moltiplicate in un unico punteggio. Al preflop i confronti attuali restano
indisponibili, mentre l'equità finale e il confronto col prezzo sono utilizzabili.

## Ipotesi visibili

Il confronto riguarda un piatto comune interamente contendibile, senza
commissioni né ulteriori costi. Al flop/turn non assume che la chiamata compri
automaticamente tutte le carte successive. In multiway segnala che altri
giocatori possono ancora agire. Non certifica l'assenza di piatti secondari
o il diritto a incassare l'intero piatto; i pulsanti visibili possono essere
opzioni preselezionabili e non dimostrano da soli che sia il turno dell'utente.
Le carte avversarie restano uniformemente casuali come richiesto per il motore.

## Verifiche

Test in `tests/test_poker_advice.py`: formule e valore atteso, mancato doppio
conteggio del piatto, esiti sopra/sotto soglia, intervallo incerto, dati scaduti,
mano/fase diversa, importi invalidi o non finiti, unità diverse, stack insufficiente,
piatti secondari, opzione gratuita, pareggi multiway, pulsanti sulla stessa riga
e conferma temporale. Test HTTP e JavaScript verificano il collegamento e la
rimozione dei suggerimenti quando lo stato diventa incompleto.

Non sono richieste nuove dipendenze. Il calcolo della valutazione è immediato
e non rilancia le simulazioni Monte Carlo. Per riprodurre i controlli:

```powershell
.\.venv-training\Scripts\python.exe -m unittest discover -s tests
node --test tests/test_browser_ui.cjs
.\.venv-training\Scripts\python.exe evaluate_browser_layout.py --equity-open --output artifacts/equity-layout
```
