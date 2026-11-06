# Poker Equity Prediction Engine

Implementazione del 6 novembre 2026. Regole: [Texas Hold'em](../regoleTexasHold_em.md).

## Analisi e architettura

Il repository comprende riconoscimento Python/OpenCV e modello ONNX, conferma
temporale, allineamento del tavolo, server HTTP standard Python, UI HTML/JS,
OCR nativo Windows separato per azioni/importi, strumenti di training e valutazione,
dataset e asset locali. Non erano presenti valutatori poker o dipendenze dedicate.
Le dipendenze esistenti restano invariate: il nuovo motore usa la libreria standard.
Non serve installare pacchetti o collegare API esterne.

Flusso browser:

```text
LearnedCardDetector → TemporalCards → arrange_table
  player_hand[2] / board[5] + OpponentTracker + HandCounter
    → OCRGameState → EquityService → processo multiprocessing spawn
      → calculate_equity → risposta HTTP /frame → renderEquity
```

`TemporalCards` richiede già cinque letture consecutive e almeno 300 ms.
Il nuovo adattatore usa `accepted` e `card`, non la sola presenza `detected`.
`HandCounter` rileva i cicli fisici indipendentemente dai valori delle carte.
Il conteggio degli avversari usa coppie coperte confermate e rimuove i posti
che non hanno più carte, compresi i fold confermati visivamente. Non vengono
reinterpretate vecchie etichette OCR di azione come eventi nuovi.

Il server serializza l'accesso allo stato esistente con il proprio lock.
`EquityService.submit` viene chiamato sotto quel lock; non è un'API concorrente.
Il calcolo CPU gira in un processo separato anche su Windows: nessuna scansione
attende la fine delle simulazioni. I risultati sono raccolti al successivo frame.
La chiusura del server cancella il lavoro e chiude il processo.

## File

Nuovi:

- `poker_equity.py`: normalizzazione, validazione, valutatore e simulatore.
- `equity_service.py`: adattatore OCR, debounce, processo, cache e generazioni.
- `benchmark_equity.py`: benchmark riproducibile per street, profilo e avversari.
- `tests/test_poker_equity.py`: test matematici, adattatore e processo reale.
- `docs/poker-equity.md`: questo documento.

Aggiornati:

- `browser_capture.py`: integrazione opzionale nel handler e lifecycle nel main.
- `browser_ui.html`: pannello espandibile, impostazioni e presentazione metriche.
- `tests/test_browser_capture.py`: verifica del contratto HTTP verso il servizio.
- `tests/test_browser_ui.cjs`: rendering e rimozione dei risultati obsoleti.
- `evaluate_browser_layout.py`: opzione `--equity-open` per verificare il pannello.
- `README.md`, `regoleTexasHold_em.md`: uso e stato dell'implementazione.

## API matematica

```python
from poker_equity import calculate_equity

result = calculate_equity(
    hero_cards=['AS', '10H'],
    community_cards=['2c', '7d', 'Jh'],
    opponents_count=3,
    simulations=50000,
    random_seed=2026,
)
```

Parametri ulteriori: `exact_threshold=2000`, `max_opponents=9`,
`cancelled=None` (callback bool), `progress=None` (callback snapshot cumulativo).
`exact_threshold=0` forza Monte Carlo. Le simulazioni accettate vanno da 2 a
1.000.000. Il limite standard è nove avversari; la UI del tavolo a sei posti
ne ammette cinque; il nuovo profilo desktop a nove posti ne ammette otto.
È sempre verificata anche la capienza del mazzo. Dettagli del nuovo layout:
[Tavolo a nove posti](tavolo-nove-posti.md).
Input invalidi sollevano `ValueError`; una cancellazione restituisce `None`.

`normalize_card` accetta `AS`, `As`, `10H`, `Th`, `A♥`, ignorando spazi esterni.
La rappresentazione interna è un intero 0..51 (rango × 4 + seme); il codice
canonico in uscita è `As`, `Th`, ecc. Carte sconosciute e duplicati sono errori.
`evaluate` accetta 5..7 interi distinti e restituisce una tupla confrontabile:
categoria 0..8 seguita dai valori di spareggio. Il confronto diretto sceglie
la mano maggiore. La scala reale è `(8, 14)`, con etichetta speciale nella UI.
Il valutatore usa conteggi e maschere, senza enumerare le 21 sottocombinazioni
durante ogni simulazione; i test lo confrontano con un oracolo indipendente che
valuta tutte le sottocombinazioni di cinque carte.

## Campionamento ed enumerazione

Ogni iterazione estrae senza reinserimento dal mazzo residuo, campionando
congiuntamente runout e mani di tutti gli avversari. L'ordine di estrazione
runout/avversari non cambia la distribuzione uniforme delle assegnazioni legali.
Le carte note sono escluse prima del ciclo. Nessun prodotto di probabilità
heads-up viene usato per il multiway.

Il costo esatto conta i runout non ordinati e le coppie per avversari etichettati:

```text
C(D, m) × prodotto per i=0..opponents-1 di C(D-m-2i, 2)
D = 52 - numero carte note; m = 5 - numero carte comuni note
```

Sotto la soglia si enumerano tutte queste distribuzioni. Al river heads-up
sono 990; con più avversari la crescita combinatoria impedisce normalmente
l'enumerazione. Non viene dichiarato esatto un campionamento Monte Carlo.

## Schema output

Tutte le probabilità sono fra 0 e 1; la UI le converte in percentuali.

```text
status: ready
method: monte_carlo | exact
hero_cards: [codice, codice]
community_cards: [] | [3, 4 o 5 codici]
street: preflop | flop | turn | river
opponents_count: intero
current_category / current_label: testo | null
metrics: {nome: {value, standard_error, ci95: [min,max]} | null}
categories: {nome categoria: {value, standard_error, ci95}}
simulations: distribuzioni completate
requested_simulations: budget richiesto
legal_deals: dimensione spazio esatto
complete: bool
random_seed: seed | null
processing_ms: tempo cumulativo del calcolo
```

Metriche:

| Nome | Significato |
| --- | --- |
| `win` | Vittoria esclusiva allo showdown |
| `lose` | Almeno un avversario strettamente migliore allo showdown |
| `tie` | Primo posto condiviso, senza avversari migliori |
| `equity` | Quota media di piatto: 0 oppure 1 / numero vincitori |
| `current_strength` | Vittoria esclusiva sul board attualmente visibile |
| `currently_behind` | Almeno un avversario attualmente migliore |
| `current_tie` | Primo posto condiviso sul board attuale |
| `category_improvement` | Categoria finale superiore a quella attuale |
| `same_category_value_improvement` | Tupla finale maggiore, categoria invariata |
| `kicker_improvement` | Sottoinsieme precedente con punto principale invariato e kicker migliori |

Per carta alta, i kicker migliorano mantenendo invariata la carta più alta;
per coppia, doppia coppia, tris e poker il punto principale deve restare uguale.
Scale, colori e full non hanno kicker separati. Un colore maggiore rientra
nel miglioramento del valore nella stessa categoria, non nei soli kicker.

Le sei metriche attuali/di miglioramento e la categoria sono `null` al preflop.
Non esiste ancora una mano di cinque carte da confrontare. Al river i due
miglioramenti e quello dei kicker valgono zero. Win + lose + tie = 1;
la distribuzione delle nove categorie finali somma a 1. Anche forza attuale,
pareggio attuale e probabilità di essere dietro formano una partizione.

Ogni SE usa la varianza campionaria con denominatore n−1, divisa per n e
portata alla radice. Per l'equity le osservazioni sono le quote frazionarie
effettive, non indicatori binari. Gli IC sono media ± 1,96 SE, limitati a [0,1].
Nell'enumerazione completa SE=0 e IC=[valore,valore] perché non c'è campionamento.

## Collegamento OCR, cache e aggiornamenti

`EquityService.submit(result, session, profile='FAST', manual_opponents=None,
random_seed=None)` restituisce uno snapshot JSON serializzabile. Per collegare
altre sorgenti basta fornire lo stesso contratto, senza ripetere riconoscimento:

```python
result = {
    'hand_cycle': {'count': 12, 'active': True},
    'player_hand': [
        {'card': 'AS', 'accepted': True, 'detected': True},
        {'card': 'KH', 'accepted': True, 'detected': True},
    ],
    'board': [  # sempre cinque slot ordinati; qui preflop
        {'card': None, 'accepted': False, 'detected': False} for _ in range(5)
    ],
    'opponents': {'count': 2, 'pending': False},
}
```

Il servizio applica 250 ms di debounce dopo il flop; prima del flop il calcolo
parte appena sono confermate entrambe le carte personali e il numero degli
avversari, senza attendere anche `hand_cycle.active`. La conferma temporale delle
carte resta obbligatoria. Un evento `hand_cycle.ended` blocca il ciclo concluso
fino al nuovo ciclo fisico, evitando il riutilizzo di carte residue.
Frame identici non rischedulano il lavoro.
La chiave comprende sessione/ciclo, carte, avversari, profilo e seed. Una nuova
chiave invalida immediatamente il risultato corrente e cambia la generazione.
Il processo controlla la cancellazione ogni 128 iterazioni; la UI non riceve
risultati di generazioni precedenti. Le richieste in coda sono limitate a una.
La cache LRU conserva al massimo 32 risultati completi: un ritorno allo stesso
stato può recuperarli senza ripetere la simulazione. Non sono mescolate stime
prodotte per stati diversi. Cache e calcolo sono in memoria, non persistenti.

Un board incompleto o non contiguo, una carta non confermata, conteggio avversari
incerto o duplicati producono `status=waiting` e `message`, senza probabilità.
La dimensione massima del board osservata nel ciclo impedisce che una scomparsa
temporanea diventi preflop; solo sessione o ciclo fisico nuovi azzerano questo
vincolo. Correzioni di identità confermate vengono validate e ricalcolate.
Una lettura assente non viene riempita con una carta storica. Una cattura iniziata
senza evidenza visiva delle carte comuni non può ricostruire carte mai osservate.

I profili FAST/BALANCED/ACCURATE corrispondono a 5.000/50.000/250.000 iterazioni.
I profili maggiori pubblicano snapshot cumulativi a 5.000 e 50.000, poi il finale.
Non sono stime indipendenti concatenate. La UI scarta anche risposte HTTP arrivate
dopo un cambiamento locale delle impostazioni.

Gli header opzionali del POST `/frame` sono `X-Equity-Profile`,
`X-Equity-Opponents` (vuoto = automatico), `X-Equity-Seed` (vuoto = casuale).
Il token/sessione e le regole del server restano quelli esistenti. L'oggetto
`equity` viene aggiunto alla risposta solo quando il servizio è collegato.
L'integrazione principale è nel browser; webcam e riconoscimento offline non
avviano autonomamente il processo ma possono usare l'API matematica.

## Uso, controlli e benchmark

Avviare normalmente `Avvia-Browser-PokerStars.cmd`, ricaricare il pannello,
selezionare la scheda e avviare la scansione. **PROBABILITÀ ED EQUITÀ DELLA MANO**
è sempre aperto sotto Lettura tavolo nella colonna sinistra, che scorre quando
il contenuto supera l'altezza disponibile. Le stime Monte Carlo sono precedute da ≈ e mostrano
l'IC equity; SE e IC delle altre metriche sono nel tooltip dei valori.

Il pannello è in italiano, comprese categorie e profili Veloce/Bilanciato/Accurato.
Il numero di avversari automatico è mostrato con la fonte: riconoscimento visivo
delle coppie coperte confermate, distinto dall'OCR dei testi. La casella "Imposta
gli avversari manualmente" abilita un campo numerico da 1 a 5; disattivandola
si torna al rilevamento automatico. Valori vuoti, frazionari o fuori intervallo
producono attesa senza interrompere la scansione. Il seme casuale facoltativo
è spiegato nella sezione "Ripetibilità della simulazione".

```powershell
.\.venv-training\Scripts\python.exe -m unittest discover -s tests
node --test tests/test_browser_ui.cjs
.\.venv-training\Scripts\python.exe evaluate_browser_layout.py
.\.venv-training\Scripts\python.exe evaluate_browser_layout.py --equity-open --output artifacts/equity-layout
.\.venv-training\Scripts\python.exe benchmark_equity.py --full
```

I test coprono categorie, kicker, asso basso, due tris, confronto con oracolo
indipendente, normalizzazione/duplicati, campionamento congiunto senza duplicati,
split con 2/3/4/6/10 vincitori, identità probabilistiche, varianza frazionaria,
Monte Carlo contro enumerazione esatta, seed, progressione/cancellazione,
letture incomplete, passaggi di street, correzioni confermate, nuova mano,
conteggio manuale, cache e scarto dei risultati del processo obsoleti.
L'integrazione HTTP controlla che il server inoltri dati e impostazioni corretti;
i test JS verificano indisponibilità preflop, rendering e rimozione delle stime.

I benchmark misurano direttamente il motore (esclusi OCR, avvio processo e HTTP)
con As/Kh, board vuoto, flop 2s/7d/Jh e river 2s/7d/Jh/Tc/9c,
seed 2026, uno/tre/cinque avversari e tutti i profili. Il rapporto completo è
`artifacts/equity-benchmark.json`; gli screenshot sono in `artifacts/equity-layout/`.
I tempi sono osservazioni locali, non garanzie di latenza o precisione.

Risultati della verifica finale: **138 test Python superati**, inclusi 19 test
del modulo equity e 8 test della valutazione economica, e **13 test frontend superati**. Il layout è stato verificato
con Edge headless alle finestre richieste 1366×768, 1280×720 e 1100×650,
con dettaglio aperto e chiuso, senza overflow della pagina o della tabella.
Sono prove automatiche e fixture controllate; non costituiscono una sessione
di gioco live completa.

Benchmark completo: 27 scenari, Windows 11, Python 3.12.14, CPU Intel64
Family 6 Model 186. Intervalli misurati fra i casi Monte Carlo descritti sopra:

| Profilo | Iterazioni | Tempo motore |
| --- | ---: | ---: |
| FAST | 5.000 | 0,17–0,67 s |
| BALANCED | 50.000 | 1,49–5,88 s |
| ACCURATE | 250.000 | 6,98–30,07 s |
| River heads-up esatto | 990 distribuzioni | 0,025–0,030 s |

Il primo avvio aggiunge il costo di creazione del processo. Le stime progressive
arrivano al completamento dei primi 5.000 campioni, prima del risultato finale
dei profili maggiori. Il tempo mostrato in UI è il tempo matematico cumulativo,
non la latenza completa di cattura/OCR/HTTP.

## Limiti e ottimizzazioni future

- Modello uniforme: nessun range, stile o deduzione dalle puntate. Una mano
  avversaria reale può essere molto diversa dal modello.
- Piatto comune con quote uguali fra vincitori: niente side pot, rake, chip
  indivisibili o valore monetario. Equity non è valore atteso di una decisione.
- Carte confermate assunte certe su indicazione dell'utente. L'errore del
  riconoscimento non è incluso negli IC e non viene stimato dal motore.
- Gli IC normali sono approssimativi, marginali e non simultanei; per eventi
  rarissimi o conteggi nulli possono essere troppo ottimisti. Non sono una
  confidence sequence per fermarsi opportunisticamente su un risultato.
- L'enumerazione esatta elimina solo l'errore Monte Carlo, non l'incertezza sulle
  carte nascoste o l'errore del modello. Una carta non vista non viene dedotta.
- I tempi ACCURATE possono superare la durata di una street: cancellazione e
  snapshot progressivi mantengono utilizzabili scansione e interfaccia.
- Possibili ottimizzazioni: lookup table del valutatore con licenza verificata,
  cache dei punteggi per board, enumerazione dei soli runout per metriche hero,
  worker compilato e IC più robusti per eventi rari. Nessuna è necessaria per
  usare questa versione e nessuna introduce automazione di gioco.
