"""Small Tk preview that also works with opencv-python-headless."""
from card_detector import annotate, cv2


class LivePreview:
    def __init__(self, title='Riconoscimento carte - Webcam'):
        try:
            import tkinter as tk
            from tkinter import ttk
            from PIL import Image, ImageTk
            self.root = tk.Tk()
        except Exception as error:
            raise RuntimeError('Anteprima non disponibile. Installa Python con Tk oppure usa --no-preview.') from error
        self.Image, self.ImageTk = Image, ImageTk
        self.tk = tk
        self.closed = False
        self.save_requested = False
        self.root.title(title)
        self.root.minsize(640, 480)
        self.root.geometry('1000x760')
        self.root.protocol('WM_DELETE_WINDOW', self.request_close)
        self.root.bind('<Escape>', lambda event: self.request_close())
        self.status = tk.StringVar(value='Avvio fotocamera...')
        ttk.Label(self.root, textvariable=self.status, font=('Segoe UI', 12)).pack(padx=12, pady=8)
        ttk.Label(self.root, text='Mostra bene valore e seme, senza riflessi. '
                  'Verde = lettura confermata; giallo = lettura incerta.').pack(padx=12, pady=4)
        self.image_label = ttk.Label(self.root, anchor='center')
        self.image_label.pack(fill='both', expand=True, padx=8, pady=8)
        controls = ttk.Frame(self.root)
        controls.pack(pady=8)
        ttk.Button(controls, text='Salva fotogramma', command=self.request_save).pack(side='left', padx=8)
        ttk.Button(controls, text='Chiudi (Esc)', command=self.request_close).pack(side='left', padx=8)
        self.saved_status = tk.StringVar(value='Salva un fotogramma per controllare il risultato e raccogliere esempi.')
        ttk.Label(self.root, textvariable=self.saved_status).pack(pady=4)
        self.root.update()

    def request_close(self):
        self.closed = True

    def request_save(self):
        self.save_requested = True

    def show(self, frame, result):
        if self.closed:
            return False
        image = self.Image.fromarray(cv2.cvtColor(annotate(frame, result), cv2.COLOR_BGR2RGB))
        image.thumbnail((max(320, self.root.winfo_width()-24), max(240, self.root.winfo_height()-160)))
        photo = self.ImageTk.PhotoImage(image)
        self.image_label.configure(image=photo)
        self.image_label.image = photo
        names = list(dict.fromkeys(c['card'] for c in result['cards'] if c['accepted']))
        indices = result.get('detection_kind') == 'card_index'
        if names:
            description = ', '.join(names)
        elif result['cards']:
            description = 'lettura incerta, avvicina valore e seme'
        else:
            description = ('nessun indice: avvicina la carta e mostra valore e seme' if indices else
                           'nessun contorno: avvicina la carta e lascia visibili i 4 angoli')
        counter_label = 'Indici' if indices else 'Sagome'
        self.status.set(f"Codici: {description} | {counter_label}: {len(result['cards'])} | "
                        f"Elaborazione: {result['processing_ms']:.0f} ms")
        try:
            self.root.update()
        except self.tk.TclError:
            self.closed = True
        return not self.closed

    def close(self):
        try:
            self.root.destroy()
        except self.tk.TclError:
            pass

    def saved(self, name):
        self.saved_status.set(f'Salvato: {name}')
