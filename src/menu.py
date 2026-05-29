import customtkinter as ctk

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

COLORS = {
    'bg': '#343541',
    'surface': '#444654',
    'primary': '#0b7a5f',
    'primary_hover': '#09654e',
    'secondary': '#565869',
    'secondary_hover': '#6e6f7e',
    'text': '#ececf1',
    'text_muted': '#8e8ea0',
    'border': '#565869',
    'error': '#ef4444'
}

class EpilepticSaverMenu(ctk.CTk):
    def __init__(self, client=None):
        super().__init__()
        self.client = client

        self.title("EPIGUARD")
        
        window_width = 800
        window_height = 600
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2)
        self.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        self.resizable(False, False)
        
        self.result = None

        self.defaults = {
            'blink_detection': "50",
            'eye_tracking': "50",
            'face_freeze': "50",
            'face_asymmetry': "50",
            'seizure_twitch': "50",
            'bpm': "50",
            'face_color': "50"
        }

        self.lift()
        self.attributes('-topmost', True)
        self.after(100, lambda: self.attributes('-topmost', False))
        self.focus_force()

        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=20, pady=20)

        self.show_screen_1()

    def clear_container(self):
        for widget in self.container.winfo_children():
            widget.destroy()

    def show_screen_1(self):
        self.clear_container()

        ctk.CTkLabel(self.container, text="EPIGUARD", 
                    font=("SF Pro Display", 36, "bold"), 
                    text_color=COLORS['text']).pack(pady=(50, 10))
        
        ctk.CTkLabel(self.container, text="Systém monitorovania epileptických záchvatov", 
                    font=("SF Pro Text", 14), 
                    text_color=COLORS['text_muted']).pack(pady=(0, 40))
        
        ctk.CTkLabel(self.container, text="Opíšte príznaky", 
                    font=("SF Pro Text", 16, "bold"), 
                    text_color=COLORS['text'],
                    anchor="w").pack(fill="x", padx=40, pady=(0, 10))

        self.textbox = ctk.CTkTextbox(self.container, height=120, 
                                       font=("SF Pro Text", 15), 
                                       fg_color=COLORS['surface'], 
                                       border_color=COLORS['border'],
                                       border_width=1,
                                       corner_radius=8)
        self.textbox.pack(fill="x", padx=40, pady=(0, 30))

        btn_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        btn_frame.pack(pady=20)

        ctk.CTkButton(btn_frame, text="Pokračovať", 
                     width=180, height=44, 
                     font=("SF Pro Text", 15, "bold"),
                     fg_color=COLORS['primary'], 
                     hover_color=COLORS['primary_hover'],
                     corner_radius=8,
                     command=self.go_to_screen_2).pack(side="left", padx=8)
        
        ctk.CTkButton(btn_frame, text="Zrušiť", 
                     width=120, height=44, 
                     font=("SF Pro Text", 15),
                     fg_color=COLORS['secondary'], 
                     hover_color=COLORS['secondary_hover'],
                     corner_radius=8,
                     command=self.on_cancel).pack(side="left", padx=8)

    def show_screen_2(self):
        self.clear_container()

        ctk.CTkLabel(self.container, text="Nastavenie parametrov", 
                    font=("SF Pro Display", 32, "bold"), 
                    text_color=COLORS['text']).pack(pady=(20, 10))
        
        ctk.CTkLabel(self.container, text="Prispôsobte prahy detekcie (0-100)", 
                    font=("SF Pro Text", 14), 
                    text_color=COLORS['text_muted']).pack(pady=(0, 20))
        
        scrollable_frame = ctk.CTkScrollableFrame(self.container, fg_color="transparent", height=300)
        scrollable_frame.pack(padx=40, pady=10, fill="both", expand=True)
        
        params_container = ctk.CTkFrame(scrollable_frame, fg_color=COLORS['surface'], corner_radius=12)
        params_container.pack(fill="x", pady=5)

        self.entries = {}
        labels = [
            ("Prah žmurkania", "blink_detection"),
            ("Sledovanie očí", "eye_tracking"),
            ("Prah pohybu tváre", "face_freeze"),
            ("Asymetria tváre", "face_asymmetry"),
            ("Záchvaty/Tiky", "seizure_twitch"),
            ("Srdcový tep (BPM)", "bpm"),
            ("Farba tváre", "face_color")
        ]

        for i, (text, key) in enumerate(labels):
            row_frame = ctk.CTkFrame(params_container, fg_color="transparent")
            row_frame.pack(fill="x", padx=30, pady=12)
            
            ctk.CTkLabel(row_frame, text=text, 
                        font=("SF Pro Text", 15), 
                        text_color=COLORS['text'],
                        anchor="w").pack(side="left", fill="x", expand=True)
            
            entry = ctk.CTkEntry(row_frame, width=80, height=36,
                                font=("SF Pro Text", 15), 
                                justify="center",
                                fg_color=COLORS['bg'], 
                                border_color=COLORS['border'],
                                border_width=1,
                                corner_radius=6)
            entry.pack(side="right")
            self.entries[key] = entry
        
        self.update()
        for key, entry in self.entries.items():
            entry.delete(0, "end")
            entry.insert(0, self.defaults[key])

        self.error_label = ctk.CTkLabel(self.container, text="", 
                                       text_color=COLORS['error'], 
                                       font=("SF Pro Text", 13))
        self.error_label.pack(pady=5)

        btn_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        btn_frame.pack(pady=15)

        ctk.CTkButton(btn_frame, text="Spustiť detekciu", 
                     width=200, height=44, 
                     font=("SF Pro Text", 15, "bold"),
                     fg_color=COLORS['primary'], 
                     hover_color=COLORS['primary_hover'],
                     corner_radius=8,
                     command=self.on_submit).pack(side="left", padx=8)
        
        ctk.CTkButton(btn_frame, text="Späť", 
                     width=100, height=44, 
                     font=("SF Pro Text", 15),
                     fg_color=COLORS['secondary'], 
                     hover_color=COLORS['secondary_hover'],
                     corner_radius=8,
                     command=self.show_screen_1).pack(side="left", padx=8)

    def go_to_screen_2(self):
        self.user_text = self.textbox.get("1.0", "end-1c")
        if not self.user_text.strip():
            self.textbox.configure(border_color="red", border_width=2)
            return
        
        ai_response = ""
        if self.client is not None:
            self.client.get_response(self.user_text)
            
        print("AI Response:", ai_response)
        
        try:
            import json
            response_data = json.loads(ai_response)
            
            for key in ['blink_detection', 'eye_tracking', 'face_freeze', 
                       'face_asymmetry', 'seizure_twitch', 'bpm', 'face_color']:
                if key in response_data:
                    self.defaults[key] = str(int(response_data[key] * 100))
                
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Chyba pri parsovaní AI odpovede: {e}")
        
        self.show_screen_2()

    def validate(self, val):
        try:
            num = int(val)
            return 0 <= num <= 100
        except ValueError:
            return False

    def on_submit(self):
        final_values = {}
        for key, entry in self.entries.items():
            val = entry.get()
            if not self.validate(val):
                self.error_label.configure(text=f"Chyba: '{val}' nie je číslo 0-100")
                return
            final_values[key] = int(val)
        
        self.result = {
            'text': self.user_text,
            **final_values
        }
        self.destroy()

    def on_cancel(self):
        self.destroy()

def show_menu_modern(client=None):
    app = EpilepticSaverMenu(client=client)
    app.mainloop()
    return app.result

if __name__ == "__main__":
    print(show_menu_modern())
