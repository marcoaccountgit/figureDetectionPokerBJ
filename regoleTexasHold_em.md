# Regole Texas Hold'em — riferimento per il progetto

Fonte principale: [PokerStars Italia — Texas Hold'em](https://www.pokerstars.it/poker/texas-holdem?language=it).
Fonte integrativa per gli spareggi: [Regolamento Texas Hold'em PokerStars](https://www.pokerstars.it/content/dam/new-dam/italy/website/documenti/poker/Poker%20Texas%20Hold%27em.pdf).
Consultazione: 6 novembre 2026. Sintesi operativa, non trascrizione integrale.

## Stato del lavoro

Il valutatore segue queste regole. L'utente ha successivamente autorizzato
l'implementazione del motore probabilistico; architettura, API e limiti sono
documentati in [Poker Equity Engine](docs/poker-equity.md).
Questo documento non definisce range o strategie.

## Carte e risultato

Ogni giocatore riceve due carte personali. Il board arriva a cinque carte:
tre al flop, una al turn e una al river; il preflop precede il board.
Allo showdown si confrontano le migliori cinque carte disponibili per ciascuno,
utilizzando zero, una o due carte personali. Le carte eccedenti non spareggiano.
I semi hanno pari valore. Mani vincenti identiche dividono il piatto.
Se tutti gli altri passano, il giocatore rimasto vince senza showdown.

## Ordine delle combinazioni, dalla più forte

1. Scala reale: scala colore da dieci ad asso.
2. Scala colore.
3. Poker.
4. Full.
5. Colore.
6. Scala.
7. Tris.
8. Doppia coppia.
9. Coppia.
10. Carta alta.

## Spareggi

Il regolamento integrativo specifica il confronto dei valori all'interno
della combinazione e poi dei kicker pertinenti. Nel full conta prima il tris,
poi la coppia; nel colore si confrontano in ordine le cinque carte.
L'asso può chiudere la scala massima oppure aprire A-2-3-4-5:
quest'ultima è una scala al cinque.

## Svolgimento

Il bottone identifica il dealer; piccolo e grande buio precedono la distribuzione.
Le azioni procedono in senso orario: preflop da dopo il grande buio,
postflop dal primo giocatore attivo dopo il bottone. Le opzioni comprendono
check, puntata, fold, call e rilancio, secondo la situazione.

La fonte distingue Limit, No Limit e Pot Limit. La struttura di puntata
del tavolo andrà mantenuta esplicita nella futura specifica.

## Assunto del progetto

Per precedente indicazione dell'utente, le carte confermate sono considerate
certe. È un assunto sugli input, distinto dall'eventuale errore campionario
di una futura simulazione Monte Carlo. Le altre scelte del motore restano aperte.
