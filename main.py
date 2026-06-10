import customtkinter as ctk

from ui import SyncApp


if __name__ == "__main__":
    root = ctk.CTk()
    SyncApp(root)
    root.mainloop()
