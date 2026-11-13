# Correzioni ricavate dagli screenshot degli interventi manuali

Fonte: immagini già salvate in `artifacts/manual-interventions`; nessun nuovo video o acquisizione. I pesi del modello non sono stati riaddestrati.

- Allineamento desktop: se i massimi individuali dei riferimenti del bordo non concordano, verifica almeno due riferimenti nella stessa posa. I due screenshot del 13 novembre alle 11:53 UTC ora restituiscono correttamente 7S AS QD all'avvio da zero.
- Rivalidazione: dopo 40 controlli della cache con mano attiva e carte del giocatore fisicamente presenti, avvia otto letture complete. La memoria sostituisce un'identità solo dopo tre letture accettate consecutive della nuova carta; il filtro temporale richiede già cinque osservazioni coerenti. Letture mancanti o contraddittorie interrompono la conferma. Le correzioni manuali conservano la precedenza.
- Duplicati: due slot con la stessa carta vengono entrambi esclusi dalla situazione confermata e sbloccati per la rilettura. Non si sceglie il vincitore in base alla confidenza. La normalizzazione considera TC e 10C equivalenti. Anche un inserimento manuale che duplica una carta già confermata viene rifiutato.

## Verifica

81 test passati nelle suite di disposizione delle carte, memoria e conferma temporale, cache, allineamento, profili, acquisizione browser, regressioni desktop e nuove regressioni sulle immagini manuali. Il test dell'intervento manuale è stato rieseguito dopo l'aggiunta del controllo dei duplicati.

I quattro screenshot conservati nei fixture verificano 9S mancante, due re precedentemente confusi e i due avvii desktop problematici. Lo screenshot dei re verifica anche la correzione di una lettura 4C bloccata in memoria in 4S attraverso entrambi i filtri.

Questi casi sono regressioni note, non una misura indipendente dell'accuratezza generale. Un fermo immagine non certifica il corretto conteggio delle transizioni fra mani. La rivalidazione aggiunge letture del modello a intervalli limitati: la latenza reale dipende dal computer.

Riavviare il processo del bot per caricare il codice aggiornato.
