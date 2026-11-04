# Modello di riconoscimento degli indici

La webcam usa **LGD Cards Gen 3**, un YOLO11s già addestrato su 52 classi
valore+seme. Il modello individua direttamente gli **indici**, senza richiedere
il contorno completo della carta. Una carta con quattro indici può quindi
produrre quattro rettangoli. I risultati non rappresentano carte uniche.

- Fonte: https://huggingface.co/sroot/lgd-cards-gen3
- Revisione: `b2e9e89cc0138a70fc3ac5661922f99b4e3ae135`
- Licenza dichiarata: **AGPL-3.0**, derivato da Ultralytics YOLO11.
- Provenienza e condizioni: consultare la model card dell'autore alla fonte.
- Pesi ONNX: circa 38 MB, esclusi da Git. Mappa delle 52 classi inclusa.
- Download riproducibile: `python download_model.py`.
- Hash SHA-256 di pesi e mappa: `manifest.json`, verificati prima del caricamento.
- Runtime: OpenCV DNN su CPU, già incluso nelle dipendenze. Nessun servizio cloud,
  nessun caricamento di immagini, nessun checkpoint Python/Pickle eseguito.

La licenza dei pesi è distinta da quella del runtime OpenCV: distribuirli o
offrire un servizio che li usa richiede rispettarne le condizioni AGPL.
Non considerare questo modello come un'opera originale del progetto.

Il modello è un punto di partenza, non una garanzia di lettura di ogni mazzo.
Le metriche pubblicate dall'autore sono relative al suo dataset e non misurano
l'accuratezza su questo progetto. I tre fotogrammi webcam locali mostrano tutti
lo stesso 10 di quadri: non costituiscono una verifica delle altre 51 classi.
