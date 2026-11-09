# Revisione degli interventi manuali dell'8 novembre 2026

Revisione eseguita il 9 novembre. Sorgenti: tutte le 12 coppie
`screenshot.png` / `analysis.json` in `artifacts/manual-interventions/20261108*`.
Gli orari della tabella sono locali (Europe/Rome); i nomi delle cartelle usano UTC.

Sono stati confrontati lo screenshot, lo stato `before` e una nuova lettura
del modello sullo screenshot allineato. Un intervento non costituisce da solo
un'etichetta corretta: due correzioni riguardano carte assenti nell'immagine.
La grafia `10C` del modello e `TC` delle correzioni indica lo stesso 10 di fiori.

| Ora | Intervento | Stato salvato e riscontro visivo |
| --- | --- | --- |
| 13:52:58 | Carta personale sinistra = 10 quadri | Nessuna carta personale visibile; il board 4D 6D 9D 5H 5S era corretto. La correzione non prova un errore del modello. |
| 13:57:25 | Nuova mano | Board salvato vuoto, ma nell'immagine sono presenti 4H 4D 5D; la nuova lettura li rileva. |
| 14:44:08 | Turn = 10 fiori | Il bot aveva gia letto 10C: correzione equivalente a TC. |
| 14:44:28 | Nuova mano | Stato precedente con solo il turn manuale e allineamento perso. Lo screenshot contiene JC 3C QS 10C AS, tutti rilevati dalla nuova lettura. Carte avversarie scoperte escluse dalla mano personale. |
| 19:56:09 | Nuova mano | AD KH 6C corretti e nessuna carta personale visibile: nessun errore di identita dimostrato. |
| 19:56:42 | Nuova mano | Mano salvata vuota; JS 5C visibili e rilevati dalla nuova lettura. |
| 20:19:54 | Nuova mano | 10D 9H e board 3C QC 8D 5H corretti, ma ciclo inattivo: il controllo di presenza della carta sinistra era incerto. |
| 20:20:59 | Flop 3 = K fiori | Nessuna carta sul tavolo o nella mano nello screenshot. Non usare KC come etichetta di addestramento. |
| 20:22:57 | Nuova mano | Memoria QH 4H e board precedente, mentre sono visibili AH 3C e board vuoto. Il reset automatico era gia in attesa, con una sola osservazione: lo snapshot non dimostra che non si sarebbe risolto dopo altre scansioni. |
| 20:24:10 | Carta personale destra = 4 fiori | Salvati solo 9C e board vuoto. Sono visibili 9C 4C e flop 9S 7H JH: confermati nella riproduzione della pipeline attuale. |
| 20:27:42 | Nuova mano | Memoria 10H 8H e board 2S 4H KH 6H; nell'immagine AS 9C e nuovo flop 5H 9D 8D. Errore riproducibile del cambio mano quando l'intervallo senza board non viene osservato. |
| 20:32:29 | Nuova mano | Memoria 10C 3C e board 3D 7S 8C; nell'immagine JC 9D e board vuoto. Il controllo di presenza sinistro incerto impediva il riavvio automatico. |

## Correzioni

- `live_card_cache.py`: verifica il reset fisico del board prima delle uscite
  per mano non confermata. Anche il ritorno al panno verde in uno slot di
  turn/river precedentemente confermato avvia la verifica del cambio mano:
  il nuovo flop puo essere gia presente. Una copertura scura non vale come
  rimozione fisica. La conferma del cambio mano richiede ancora cinque letture.
- `hand_counter.py`: sui tavoli desktop integra il controllo di presenza
  usando anche fasce di mezza altezza dell'indice. Richiede bianco nella
  fascia, poco panno verde e contesto verde esterno alla carta. Recupera il
  10 rosso e il J parzialmente coperti dal pannello senza cambiare le soglie
  del classificatore di valori e semi.
- Quattro screenshot originali sono conservati in
  `tests/fixtures/compact-*.png`. Il test HTTP usa il modello reale, verifica
  le identita, il contatore e il ritorno alla cache dopo la conferma.
  Riproduce consecutivamente mano con turn, nuovo flop e nuovo preflop;
  verifica anche 9C 4C con il suo flop in una sessione separata.

Il confronto degli avversari sugli screenshot non ha mostrato nuovi falsi
positivi fra carte coperte e showdown. Diversi conteggi salvati erano `null`,
quindi ancora non confermati; non sono stati trattati come conteggi sbagliati.

Validazione finale: `python -m unittest discover -s tests`, **227 test
superati**. `evaluate_hand_counter.py`: **35/35** fotogrammi di presenza e
**12/12** della sequenza di fold corretti. I test delle carte parzialmente
coperte verificano anche ridimensionamenti a 0,8 e 1,5 volte l'originale e
il rifiuto di una schermata interamente bianca.

## Limiti della verifica

Ogni intervento conserva un solo screenshot e lo stato precedente del bot,
non il video delle scansioni che hanno portato a quello stato. La ripetizione
degli screenshot verifica che la pipeline converga dopo osservazioni stabili;
non misura quanto tempo abbia impiegato nel gioco originale. Se il bot salta
un'intera transizione da flop a flop senza vedere rimozioni fisiche o fold,
queste immagini da sole non permettono di identificare il cambio mano.

Non e stato riaddestrato il modello: le nuove letture non hanno evidenziato
errori persistenti di valore o seme su queste immagini. I difetti riprodotti
sono nella conferma della presenza e nell'invalidazione della memoria.
