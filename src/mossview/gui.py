#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MossView GUI - Interface Gráfica Interativa para Análise, Simulação e Visualização Mössbauer.
Compatível com NORMOS DOS (MBPLOT, READMCS, WCONVERT, WDIST, WSITE, WSIMDATA, P).
Funcionalidade completa de arrastar e soltar (Drag and Drop) e seleção nativa compatível
com Windows, Linux e macOS.
"""

import sys
import os
from pathlib import Path
from typing import Optional, List
import numpy as np

# Suporte a execução direta do script (ex: python src/mossview/gui.py)
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from mossview.lib import (
        resolve_file_path,
        locate_associated_files,
        parse_job_file,
        validate_and_filter_param_block,
        parse_mos_file,
        fold_spectrum,
        export_converted_data,
        calculate_velocity_scale,
        MossbauerModel,
        plot_mossbauer,
        load_and_process_spectrum,
        open_file_dialog_native,
        open_in_system_file_manager,
    )
else:
    from .lib import (
        resolve_file_path,
        locate_associated_files,
        parse_job_file,
        validate_and_filter_param_block,
        parse_mos_file,
        fold_spectrum,
        export_converted_data,
        calculate_velocity_scale,
        MossbauerModel,
        plot_mossbauer,
        load_and_process_spectrum,
        open_file_dialog_native,
        open_in_system_file_manager,
    )

import tkinter as tk
from tkinter import filedialog, messagebox

# Tentativa de inicialização com CustomTkinter para visual moderno
try:
    import customtkinter as ctk

    HAS_CUSTOMTKINTER = True
except ImportError:
    HAS_CUSTOMTKINTER = False
    import tkinter as ctk
    from tkinter import font as tkfont

    class _TkCompatFrame(tk.Frame):
        def __init__(self, master=None, **kwargs):
            if "border_width" in kwargs:
                kwargs["borderwidth"] = kwargs.pop("border_width")
            for name in ("corner_radius", "border_color", "fg_color", "hover_color"):
                kwargs.pop(name, None)
            super().__init__(master, **kwargs)

    class _TkCompatLabel(tk.Label):
        def __init__(self, master=None, **kwargs):
            if "text_color" in kwargs:
                kwargs["fg"] = kwargs.pop("text_color")
            kwargs.pop("fg_color", None)
            kwargs.pop("corner_radius", None)
            super().__init__(master, **kwargs)

    class _TkCompatButton(tk.Button):
        def __init__(self, master=None, **kwargs):
            if "fg_color" in kwargs:
                kwargs["bg"] = kwargs.pop("fg_color")
            kwargs.pop("hover_color", None)
            kwargs.pop("corner_radius", None)
            super().__init__(master, **kwargs)

    class _TkCompatCheckBox(tk.Checkbutton):
        def __init__(self, master=None, **kwargs):
            if "text_color" in kwargs:
                kwargs["fg"] = kwargs.pop("text_color")
            if "fg_color" in kwargs:
                kwargs["selectcolor"] = kwargs.pop("fg_color")
            kwargs.pop("hover_color", None)
            kwargs.pop("corner_radius", None)
            super().__init__(master, **kwargs)

    class _TkCompatTextbox(tk.Text):
        def __init__(self, master=None, **kwargs):
            kwargs.pop("corner_radius", None)
            kwargs.pop("fg_color", None)
            kwargs.pop("text_color", None)
            super().__init__(master, **kwargs)

    class _TkCompatOptionMenu(tk.OptionMenu):
        def __init__(self, master, variable, *values, command=None, **kwargs):
            kwargs.pop("corner_radius", None)
            kwargs.pop("fg_color", None)
            kwargs.pop("button_color", None)
            kwargs.pop("button_hover_color", None)
            super().__init__(master, variable, *values, command=command, **kwargs)

    class _TkCompatTabview(tk.Frame):
        def __init__(self, master=None, **kwargs):
            super().__init__(master, **kwargs)
            self._tabs = {}
            self._active_tab = None

        def add(self, name):
            frame = tk.Frame(self)
            self._tabs[name] = frame
            if self._active_tab is None:
                self._active_tab = name
                frame.pack(fill="both", expand=True)
            return frame

        def set(self, name):
            if name not in self._tabs:
                return
            if self._active_tab is not None:
                self._tabs[self._active_tab].pack_forget()
            self._active_tab = name
            self._tabs[name].pack(fill="both", expand=True)

    class _TkCompat:
        CTk = tk.Tk
        CTkFrame = _TkCompatFrame
        CTkScrollableFrame = _TkCompatFrame
        CTkLabel = _TkCompatLabel
        CTkButton = _TkCompatButton
        CTkCheckBox = _TkCompatCheckBox
        CTkTextbox = _TkCompatTextbox
        CTkOptionMenu = _TkCompatOptionMenu
        CTkTabview = _TkCompatTabview
        CTkFont = tkfont.Font

    ctk = _TkCompat()

# Tentativa de suporte nativo a Drag and Drop via TkinterDnD2
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES

    HAS_DND = True
except ImportError:
    HAS_DND = False
    DND_FILES = None

# Matplotlib embedding
import matplotlib

matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

# Definição da classe base com suporte a Drag & Drop
if HAS_CUSTOMTKINTER:
    if HAS_DND:

        class BaseAppWindow(ctk.CTk, TkinterDnD.DnDWrapper):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                try:
                    self.TkdndVersion = TkinterDnD._require(self)
                except Exception:
                    pass

    else:

        class BaseAppWindow(ctk.CTk):
            pass

else:
    if HAS_DND:

        class BaseAppWindow(tk.Tk, TkinterDnD.DnDWrapper):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                try:
                    self.TkdndVersion = TkinterDnD._require(self)
                except Exception:
                    pass

    else:

        class BaseAppWindow(tk.Tk):
            pass


class MossViewGUI(BaseAppWindow):
    """
    Janela Principal do MossView GUI.
    Oferece área de soltar arquivos (Drag & Drop), botão de seleção cross-platform,
    visualização integrada de espectros Mössbauer com Matplotlib e ferramentas analíticas.
    """

    def __init__(self, initial_file: Optional[str] = None):
        super().__init__()

        self.title("MossView - Espectroscopia Mössbauer")
        self.geometry("1240x820")
        self.minsize(980, 680)

        self.logo_image = None
        self.window_icon_image = None
        self._load_brand_images()
        self._set_window_icon()

        if HAS_CUSTOMTKINTER:
            ctk.set_appearance_mode("Dark")
            ctk.set_default_color_theme("blue")

        # Estado da Aplicação
        self.current_file_path: Optional[Path] = None
        self.spectrum_data: Optional[dict] = None
        self.fig: Optional[plt.Figure] = None
        self.canvas: Optional[FigureCanvasTkAgg] = None
        self.toolbar: Optional[NavigationToolbar2Tk] = None

        # Constrói a interface
        self._build_layout()

        # Carrega arquivo inicial se fornecido
        if initial_file:
            self.load_file(initial_file)

    def _load_brand_images(self):
        """Carrega o PNG da marca para uso no cabeçalho e no ícone da janela."""
        try:
            logo_path = Path(__file__).parent / "assets" / "icon" / "mossview-logo.png"
            if not logo_path.exists():
                return

            self.window_icon_image = tk.PhotoImage(file=str(logo_path))
            if HAS_CUSTOMTKINTER:
                from PIL import Image

                pil_logo = Image.open(logo_path)
                self.logo_image = ctk.CTkImage(
                    light_image=pil_logo, dark_image=pil_logo, size=(42, 42)
                )
            else:
                self.logo_image = self.window_icon_image.subsample(4, 4)
        except (OSError, ImportError, tk.TclError):
            self.logo_image = None
            self.window_icon_image = None

    def _set_window_icon(self):
        """Define o PNG da marca como ícone da janela."""
        if self.window_icon_image is not None:
            self.iconphoto(True, self.window_icon_image)

    def _build_layout(self):
        """Monta o grid principal e os componentes visuais."""
        # Top Bar
        self.top_frame = ctk.CTkFrame(self, height=52, corner_radius=0)
        self.top_frame.pack(side="top", fill="x")

        # Logo / Título
        title_label = ctk.CTkLabel(
            self.top_frame,
            text="MossView",
            image=self.logo_image,
            compound="left",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        title_label.pack(side="left", padx=20, pady=8)

        subtitle_label = ctk.CTkLabel(
            self.top_frame,
            text="| Leitura, Análise e Visualização Mössbauer (Substituto NORMOS)",
            font=ctk.CTkFont(size=12, slant="italic"),
            text_color="gray70",
        )
        subtitle_label.pack(side="left", padx=0, pady=8)

        # Alternador de Tema (Dark / Light)
        if HAS_CUSTOMTKINTER:
            self.theme_switch = ctk.CTkOptionMenu(
                self.top_frame,
                values=["Dark", "Light", "System"],
                command=self._on_theme_change,
                width=100,
            )
            self.theme_switch.set("Dark")
            self.theme_switch.pack(side="right", padx=16, pady=8)

        # Botão abrir no gerenciador de arquivos
        self.btn_open_folder = ctk.CTkButton(
            self.top_frame,
            text="📂 Abrir no Explorador",
            width=150,
            command=self.open_current_in_explorer,
        )
        self.btn_open_folder.pack(side="right", padx=10, pady=8)

        # Container Principal Dividido (Esquerda: Controles | Direita: Visualização)
        self.main_container = ctk.CTkFrame(self, corner_radius=0)
        self.main_container.pack(side="top", fill="both", expand=True, padx=8, pady=8)

        # Painel Lateral Esquerdo (Controles e Drag & Drop)
        self.left_panel = ctk.CTkScrollableFrame(
            self.main_container, width=380, corner_radius=8
        )
        self.left_panel.pack(side="left", fill="y", padx=(4, 8), pady=4)

        # Painel Direito (Abas de Gráficos e Resultados)
        self.right_panel = ctk.CTkFrame(self.main_container, corner_radius=8)
        self.right_panel.pack(
            side="right", fill="both", expand=True, padx=(0, 4), pady=4
        )

        self._build_drop_zone()
        self._build_file_info_card()
        self._build_action_buttons()
        self._build_right_tabview()

    def _build_drop_zone(self):
        """Cria a área visual de arrastar e soltar (Drag and Drop) e clique para selecionar."""
        self.drop_frame = ctk.CTkFrame(
            self.left_panel,
            corner_radius=12,
            border_width=2,
            border_color="#3B8ED0" if HAS_CUSTOMTKINTER else "blue",
            fg_color=("gray85", "#20242B"),
        )
        self.drop_frame.pack(fill="x", padx=8, pady=(8, 12), ipady=12)

        # Ícone / Símbolo
        self.drop_icon = ctk.CTkLabel(
            self.drop_frame, text="📥", font=ctk.CTkFont(size=36)
        )
        self.drop_icon.pack(pady=(8, 2))

        # Texto Principal
        self.drop_title = ctk.CTkLabel(
            self.drop_frame,
            text="Arraste o arquivo aqui",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self.drop_title.pack(pady=2)

        # Texto Secundário
        self.drop_sub = ctk.CTkLabel(
            self.drop_frame,
            text="Formatos: .JOB, .MOS, .MCS\nou clique para navegar no Explorador",
            font=ctk.CTkFont(size=12),
            text_color="gray60",
            justify="center",
        )
        self.drop_sub.pack(pady=2)

        # Botão explícito de seleção de arquivo
        self.btn_select = ctk.CTkButton(
            self.drop_frame,
            text="🔍 Selecionar Arquivo",
            command=self.browse_file,
            width=160,
            height=32,
        )
        self.btn_select.pack(pady=(8, 6))

        # Torna toda a área clicável para abrir o Explorador de Arquivos (Windows, Linux, macOS)
        for widget in (self.drop_frame, self.drop_icon, self.drop_title, self.drop_sub):
            widget.bind("<Button-1>", lambda e: self.browse_file())
            try:
                widget.configure(cursor="hand2")
            except Exception:
                pass

        # Efeito visual de hover
        self.drop_frame.bind("<Enter>", self._on_drop_hover_enter)
        self.drop_frame.bind("<Leave>", self._on_drop_hover_leave)

        # Registro de Drag and Drop
        if HAS_DND:
            self._register_dnd(self)
            self._register_dnd(self.drop_frame)
            self._register_dnd(self.drop_icon)
            self._register_dnd(self.drop_title)
            self._register_dnd(self.drop_sub)

    def _register_dnd(self, widget):
        """Registra widget como receptor de Drag and Drop se suportado."""
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_dnd_drop)
        except Exception:
            pass

    def _on_drop_hover_enter(self, event):
        try:
            self.drop_frame.configure(border_color="#1F6AA5")
        except Exception:
            pass

    def _on_drop_hover_leave(self, event):
        try:
            self.drop_frame.configure(border_color="#3B8ED0")
        except Exception:
            pass

    def _on_dnd_drop(self, event):
        """Captura arquivo arrastado para dentro da janela e o processa."""
        try:
            raw_data = event.data
            if not raw_data:
                return

            # Utiliza splitlist do Tkinter para tratar caminhos com espaços
            files = self.tk.splitlist(raw_data)
            if files:
                first_file = files[0].strip()
                if first_file:
                    self.load_file(first_file)
        except Exception as e:
            messagebox.showerror(
                "Erro de Leitura", f"Falha ao processar arquivo arrastado:\n{e}"
            )

    def browse_file(self):
        """
        Abre o Explorador de Arquivos nativo do sistema operacional.
        100% compatível com Windows (Explorer), Linux (GTK/KDE) e macOS (Finder).
        """
        initial_dir = (
            self.current_file_path.parent if self.current_file_path else Path.cwd()
        )
        selected = open_file_dialog_native(
            title="Selecionar Arquivo Mössbauer (.JOB, .MOS, .MCS)",
            initial_dir=initial_dir,
        )
        if selected:
            self.load_file(str(selected))

    def _build_file_info_card(self):
        """Card informativo com os metadados do arquivo carregado."""
        self.info_card = ctk.CTkFrame(self.left_panel, corner_radius=8)
        self.info_card.pack(fill="x", padx=8, pady=4)

        card_title = ctk.CTkLabel(
            self.info_card,
            text="📄 Informações do Arquivo",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        card_title.pack(anchor="w", padx=10, pady=(8, 4))

        self.lbl_file_name = ctk.CTkLabel(
            self.info_card,
            text="Nenhum arquivo carregado",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="gray70",
            anchor="w",
            wraplength=340,
        )
        self.lbl_file_name.pack(fill="x", padx=10, pady=2)

        self.lbl_pair_info = ctk.CTkLabel(
            self.info_card,
            text="Par MOS/JOB: N/A",
            font=ctk.CTkFont(size=11),
            text_color="gray60",
            anchor="w",
            wraplength=340,
        )
        self.lbl_pair_info.pack(fill="x", padx=10, pady=2)

        self.lbl_stats = ctk.CTkLabel(
            self.info_card,
            text="Canais: - | VMAX: - | BKG: - | Chi²: -",
            font=ctk.CTkFont(size=11),
            text_color="gray60",
            anchor="w",
            wraplength=340,
        )
        self.lbl_stats.pack(fill="x", padx=10, pady=(2, 8))

    def _build_action_buttons(self):
        """Monta os controles e botões de ação na barra lateral."""
        self.actions_frame = ctk.CTkFrame(self.left_panel, corner_radius=8)
        self.actions_frame.pack(fill="x", padx=8, pady=6)

        actions_title = ctk.CTkLabel(
            self.actions_frame,
            text="⚙️ Opções & Ações NORMOS",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        actions_title.pack(anchor="w", padx=10, pady=(8, 6))

        # Checkbox Folding
        self.chk_fold_var = tk.BooleanVar(value=False)
        self.chk_fold = ctk.CTkCheckBox(
            self.actions_frame,
            text="Dobragem Simétrica (Folding)",
            variable=self.chk_fold_var,
            command=self._on_folding_toggle,
        )
        self.chk_fold.pack(anchor="w", padx=10, pady=4)

        # Botão: Visualizar Espectro (MBPLOT)
        self.btn_plot = ctk.CTkButton(
            self.actions_frame,
            text="📈 Atualizar Gráfico (MBPLOT)",
            command=self.refresh_plot,
            fg_color="#1f77b4",
            hover_color="#185c8c",
        )
        self.btn_plot.pack(fill="x", padx=10, pady=4)

        # Botão: Abrir Pop-out em Janela Externa
        self.btn_popout = ctk.CTkButton(
            self.actions_frame,
            text="🖥️ Abrir em Janela Separada",
            command=self.open_external_plot,
            fg_color="#4a5568",
            hover_color="#2d3748",
        )
        self.btn_popout.pack(fill="x", padx=10, pady=4)

        # Botão: Inspecionar Detector (READMCS)
        self.btn_readmcs = ctk.CTkButton(
            self.actions_frame,
            text="🔍 Inspecionar Detector (READMCS)",
            command=self.show_readmcs_dialog,
            fg_color="#2b6cb0",
            hover_color="#1c4775",
        )
        self.btn_readmcs.pack(fill="x", padx=10, pady=4)

        # Botão: Resumo Físico (WSITE / WDIST)
        self.btn_info = ctk.CTkButton(
            self.actions_frame,
            text="⚛️ Parâmetros Físicos (WSITE/WDIST)",
            command=self.show_physics_info,
            fg_color="#2b6cb0",
            hover_color="#1c4775",
        )
        self.btn_info.pack(fill="x", padx=10, pady=4)

        # Botão: Converter e Exportar (WCONVERT)
        self.btn_export = ctk.CTkButton(
            self.actions_frame,
            text="💾 Exportar Dados (WCONVERT)",
            command=self.export_data_dialog,
            fg_color="#2f855a",
            hover_color="#22543d",
        )
        self.btn_export.pack(fill="x", padx=10, pady=4)

        # Botão: Simulação Teórica (WSIMDATA)
        self.btn_sim = ctk.CTkButton(
            self.actions_frame,
            text="📊 Simular Espectro (WSIMDATA)",
            command=self.run_simulation_dialog,
            fg_color="#6b46c1",
            hover_color="#44337a",
        )
        self.btn_sim.pack(fill="x", padx=10, pady=4)

        # Botão: Validar &PARAM
        self.btn_validate = ctk.CTkButton(
            self.actions_frame,
            text="🛠️ Validar e Corrigir &PARAM",
            command=self.validate_param_dialog,
            fg_color="#c53030",
            hover_color="#9b2c2c",
        )
        self.btn_validate.pack(fill="x", padx=10, pady=(4, 10))

    def _build_right_tabview(self):
        """Monta o painel de abas para exibição do gráfico, dados técnicos e logs."""
        self.tabview = ctk.CTkTabview(self.right_panel)
        self.tabview.pack(fill="both", expand=True, padx=4, pady=4)

        self.tab_plot = self.tabview.add("📈 Espectro Mössbauer")
        self.tab_params = self.tabview.add("📋 Detalhes & Metadados")
        self.tab_log = self.tabview.add("📝 Logs & Diagnóstico")

        # Configura a aba do gráfico
        self.plot_container = ctk.CTkFrame(self.tab_plot, fg_color="transparent")
        self.plot_container.pack(fill="both", expand=True)

        self.placeholder_label = ctk.CTkLabel(
            self.plot_container,
            text="Arraste um arquivo .JOB ou .MOS para a caixa à esquerda,\nou clique para selecionar no Explorador de Arquivos.",
            font=ctk.CTkFont(size=14, slant="italic"),
            text_color="gray60",
        )
        self.placeholder_label.pack(expand=True)

        # Configura a aba de detalhes
        self.text_params = ctk.CTkTextbox(
            self.tab_params, font=ctk.CTkFont(family="Consolas", size=12)
        )
        self.text_params.pack(fill="both", expand=True, padx=6, pady=6)
        self.text_params.insert(
            "0.0",
            "Carregue um arquivo para visualizar os parâmetros físicos e de aquisição.",
        )

        # Configura a aba de logs
        self.text_log = ctk.CTkTextbox(
            self.tab_log, font=ctk.CTkFont(family="Consolas", size=11)
        )
        self.text_log.pack(fill="both", expand=True, padx=6, pady=6)
        self._log("MossView GUI iniciado com sucesso.")

    def _log(self, message: str):
        """Adiciona uma mensagem à aba de log."""
        try:
            self.text_log.insert("end", f"{message}\n")
            self.text_log.see("end")
        except Exception:
            pass

    def _on_theme_change(self, mode: str):
        """Altera o tema visual da janela."""
        if HAS_CUSTOMTKINTER:
            ctk.set_appearance_mode(mode)
            # Redesenha gráfico para casar com o tema se existir
            if self.spectrum_data:
                self.refresh_plot()

    def load_file(self, file_path_str: str):
        """Carrega e processa completamente um arquivo .JOB ou .MOS."""
        try:
            self._log(f"Carregando: {file_path_str}")
            resolved = resolve_file_path(file_path_str)

            if not resolved.exists():
                messagebox.showerror(
                    "Erro", f"Arquivo não encontrado:\n{file_path_str}"
                )
                return

            self.current_file_path = resolved

            # Carrega dados do espectro através do pipeline central
            apply_fold = self.chk_fold_var.get()
            self.spectrum_data = load_and_process_spectrum(
                str(resolved), fold=apply_fold
            )

            # Atualiza o estado da dobragem se foi aplicada automaticamente
            if self.spectrum_data["folding_applied"]:
                self.chk_fold_var.set(True)

            # Atualiza informações na interface
            self._update_info_display()

            # Renderiza gráfico embutido
            self.refresh_plot()

            # Atualiza aba de detalhes
            self._update_details_tab()

            self._log(f"[OK] Espectro carregado com sucesso: {resolved.name}")
            for w in self.spectrum_data.get("warnings", []):
                self._log(f"[AVISO] &PARAM: {w}")

        except Exception as e:
            messagebox.showerror(
                "Erro de Processamento", f"Falha ao carregar espectro:\n{e}"
            )
            self._log(f"[ERRO] {e}")

    def _update_info_display(self):
        """Atualiza os textos do card de informações do arquivo."""
        if not self.spectrum_data:
            return

        resolved = self.spectrum_data["resolved_path"]
        job_p = self.spectrum_data.get("job_path")
        mos_p = self.spectrum_data.get("mos_path")

        self.lbl_file_name.configure(text=f"📄 {resolved.name}")

        pair_str = f"MOS: {mos_p.name if mos_p else 'N/A'}"
        if job_p:
            pair_str += f" | JOB: {job_p.name}"
        self.lbl_pair_info.configure(text=pair_str)

        counts = self.spectrum_data["counts"]
        vmax = self.spectrum_data["vmax"]
        bkg = self.spectrum_data["job_info"].get("bkg") or np.max(counts)
        chi2 = self.spectrum_data["job_info"].get("chi2")
        chi2_str = f"{chi2:.2f}" if chi2 is not None else "N/A"

        stats_text = (
            f"Canais: {len(counts)} | "
            f"Vmax: ±{vmax:.2f} mm/s | "
            f"BKG: {int(bkg):,} | "
            f"Chi²: {chi2_str}"
        )
        self.lbl_stats.configure(text=stats_text)

    def _on_folding_toggle(self):
        """Trata o clique no checkbox de dobragem (folding)."""
        if self.current_file_path:
            self.load_file(str(self.current_file_path))

    def refresh_plot(self):
        """Renderiza ou atualiza o gráfico científico embutido na aba principal."""
        if not self.spectrum_data:
            return

        try:
            # Oculta o placeholder
            self.placeholder_label.pack_forget()

            # Remove canvas e toolbar antigos se existirem
            if self.canvas is not None:
                self.canvas.get_tk_widget().destroy()
                self.canvas = None
            if self.toolbar is not None:
                self.toolbar.destroy()
                self.toolbar = None

            # Cria nova figura Matplotlib
            has_residuals = self.spectrum_data.get("y_theo") is not None
            has_distribution = (
                self.spectrum_data.get("model") is not None
                and self.spectrum_data["model"].hyperfine_distribution is not None
            )

            # Ajusta tamanho relativo da figura
            figsize = (9.5, 6.0) if has_residuals else (9.5, 5.2)
            self.fig = plt.Figure(figsize=figsize, dpi=100)

            # Renderiza utilizando a rotina científica unificada MBPLOT
            plot_mossbauer(
                velocity=self.spectrum_data["velocity"],
                counts=self.spectrum_data["counts"],
                title=self.spectrum_data["title"],
                job_name=(
                    self.spectrum_data["job_path"].name
                    if self.spectrum_data.get("job_path")
                    else "Nenhum"
                ),
                mos_name=self.spectrum_data["mos_path"].name,
                y_theo=self.spectrum_data["y_theo"],
                subspectra=self.spectrum_data["subspectra"],
                model=self.spectrum_data["model"],
                show_gui=False,
                return_fig=True,
                fig=self.fig,
            )

            # Embarca a figura no Tkinter Canvas
            self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_container)
            self.canvas.draw()

            # Adiciona barra de ferramentas de navegação (Zoom, Pan, Salvar)
            self.toolbar = NavigationToolbar2Tk(self.canvas, self.plot_container)
            self.toolbar.update()
            self.canvas.get_tk_widget().pack(fill="both", expand=True)

            self.tabview.set("📈 Espectro Mössbauer")
        except Exception as e:
            messagebox.showerror(
                "Erro de Plotagem", f"Falha ao renderizar gráfico:\n{e}"
            )
            self._log(f"[ERRO PLOT] {e}")

    def open_external_plot(self):
        """Abre o espectro em uma janela independente e completa do Matplotlib."""
        if not self.spectrum_data:
            messagebox.showinfo("Aviso", "Nenhum espectro carregado para exibir.")
            return

        try:
            plot_mossbauer(
                velocity=self.spectrum_data["velocity"],
                counts=self.spectrum_data["counts"],
                title=self.spectrum_data["title"],
                job_name=(
                    self.spectrum_data["job_path"].name
                    if self.spectrum_data.get("job_path")
                    else "Nenhum"
                ),
                mos_name=self.spectrum_data["mos_path"].name,
                y_theo=self.spectrum_data["y_theo"],
                subspectra=self.spectrum_data["subspectra"],
                model=self.spectrum_data["model"],
                show_gui=True,
                dpi=150,
            )
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir janela externa:\n{e}")

    def _update_details_tab(self):
        """Preenche a aba de detalhes com o relatório dos parâmetros físicos e detector."""
        if not self.spectrum_data:
            return

        info = self.spectrum_data.get("job_info", {})
        meta = self.spectrum_data.get("meta", {})
        counts = self.spectrum_data.get("counts", [])

        lines = []
        lines.append("=" * 70)
        lines.append(" MOSSVIEW - RELATÓRIO TÉCNICO E METADADOS DO ESPECTRO")
        lines.append("=" * 70)
        lines.append(
            f"Arquivo Principal   : {self.spectrum_data['resolved_path'].name}"
        )
        lines.append(
            f"Caminho Completo    : {self.spectrum_data['resolved_path'].resolve()}"
        )
        lines.append(f"Arquivo .MOS        : {self.spectrum_data['mos_path'].name}")
        if self.spectrum_data.get("job_path"):
            lines.append(f"Arquivo .JOB        : {self.spectrum_data['job_path'].name}")
        lines.append(f"Título              : {info.get('title') or 'N/A'}")
        lines.append(f"VMAX (Velocidade)   : {info.get('vmax')} mm/s")
        lines.append(f"Canais Carregados   : {len(counts)}")
        lines.append(f"Modo Triangular     : {info.get('triang')}")
        lines.append(f"Chi-quadrado        : {info.get('chi2') or 'N/A'}")

        # Metadados MCS
        lines.append("\n" + "-" * 70)
        lines.append(" AQUISIÇÃO E DETECTOR (READMCS)")
        lines.append("-" * 70)
        if meta.get("time"):
            t_sec = meta["time"]
            lines.append(
                f"Tempo de Medida     : {t_sec:.1f} s ({t_sec/3600.0:.2f} horas)"
            )
            if t_sec > 0:
                lines.append(f"Taxa de Contagem    : {np.sum(counts)/t_sec:.2f} CPS")
        if meta.get("device"):
            lines.append(
                f"Dispositivo MCA     : #{meta['device']} (Firmware: {meta.get('firmware')})"
            )
        if meta.get("mode"):
            lines.append(f"Modo de Aquisição   : {meta['mode']}")

        total_c = np.sum(counts)
        lines.append(f"Contagens Totais    : {int(total_c):,}")
        lines.append(f"Média / Canal       : {np.mean(counts):.1f}")
        lines.append(f"Máxima Contagem     : {int(np.max(counts)):,}")
        lines.append(f"Mínima Contagem     : {int(np.min(counts)):,}")
        depth = (
            ((np.max(counts) - np.min(counts)) / np.max(counts)) * 100.0
            if np.max(counts) > 0
            else 0
        )
        lines.append(f"Efeito de Absorção  : {depth:.2f}%")

        # Sítios cristalinos
        sites = info.get("sites", [])
        lines.append("\n" + "-" * 70)
        lines.append(f" SÍTIOS CRISTALINOS DISCRETOS (WSITE) : {len(sites)} sítio(s)")
        lines.append("-" * 70)
        for s in sites:
            t_name = (
                "Singleto"
                if s["lines"] == 1
                else "Dubleto" if s["lines"] == 2 else "Sexteto"
            )
            rel_str = (
                f"{s['rel_area']:.2f}%" if s.get("rel_area") is not None else "N/A"
            )
            lines.append(f" Sítio #{s['index']} ({t_name}):")
            lines.append(
                f"   Área Subespectro  : {s['area']:.5f} mm/s (Relativa: {rel_str})"
            )
            lines.append(f"   Isomer Shift (IS) : {s['is']:+.5f} mm/s")
            lines.append(f"   Quadrupole Split  : {s['qs']:+.5f} mm/s")
            lines.append(f"   Largura (FWHM)    : {s['fwhm']:.5f} mm/s")
            if s.get("bhf", 0) > 0:
                lines.append(f"   Campo Hiperfino   : {s['bhf']:.2f} Tesla")

        # Distribuição P(B)
        dist = info.get("distribution")
        if dist and dist.get("active"):
            pct_str = (
                f"{dist['rel_area_pct']:.2f}%"
                if dist.get("rel_area_pct") is not None
                else "N/A"
            )
            lines.append("\n" + "-" * 70)
            lines.append(" DISTRIBUIÇÃO CONTÍNUA DE CAMPO HIPERFINO (WDIST)")
            lines.append("-" * 70)
            lines.append(
                f"   Campo Médio <Bhf> : {dist['bhf_avg']:.2f} +/- {dist['bhf_std']:.2f} Tesla"
            )
            lines.append(
                f"   Área da Distr.    : {dist['area']:.5f} mm/s (Relativa: {pct_str})"
            )
            lines.append(
                f"   Faixa de Campo    : {dist['bhf_start']:.2f} a {dist['bhf_start'] + dist['nsb']*dist['dtb']:.2f} Tesla"
            )
            lines.append(
                f"   Passos da Grade   : {dist['nsb']} passos de {dist['dtb']:.2f} Tesla"
            )
            lines.append(f"   IS Médio          : {dist['iso']:+.5f} mm/s")
            lines.append(f"   QS Médio          : {dist['qua']:+.5f} mm/s")
            lines.append(f"   Largura Intrínseca: {dist['wid']:.5f} mm/s")

        lines.append("=" * 70)

        self.text_params.delete("0.0", "end")
        self.text_params.insert("0.0", "\n".join(lines))

    def show_readmcs_dialog(self):
        """Muda para a aba de detalhes e foca na seção do READMCS."""
        if not self.spectrum_data:
            messagebox.showinfo("Aviso", "Selecione um arquivo de dados .MOS primeiro.")
            return
        self.tabview.set("📋 Detalhes & Metadados")

    def show_physics_info(self):
        """Muda para a aba de detalhes e exibe os parâmetros físicos."""
        if not self.spectrum_data:
            messagebox.showinfo("Aviso", "Selecione um arquivo .JOB ou .MOS primeiro.")
            return
        self.tabview.set("📋 Detalhes & Metadados")

    def export_data_dialog(self):
        """Abre diálogo para exportar dados colunares (.LST, .CSV, .DAT)."""
        if not self.spectrum_data:
            messagebox.showinfo("Aviso", "Nenhum dado disponível para exportação.")
            return

        default_name = self.spectrum_data["mos_path"].stem + ".lst"
        filetypes = [
            ("Arquivo de Colunas LST (*.lst)", "*.lst"),
            ("Arquivo CSV Delimitado (*.csv)", "*.csv"),
            ("Arquivo de Dados DAT (*.dat)", "*.dat"),
            ("Todos os arquivos (*.*)", "*.*"),
        ]

        out_path = filedialog.asksaveasfilename(
            parent=self,
            title="Exportar Espectro Mössbauer Formatado (WCONVERT)",
            initialfile=default_name,
            filetypes=filetypes,
        )

        if not out_path:
            return

        out_p = Path(out_path)
        fmt = out_p.suffix.lstrip(".").lower() or "lst"

        try:
            export_converted_data(
                output_path=out_p,
                velocity=self.spectrum_data["velocity"],
                counts=self.spectrum_data["counts"],
                y_theo=self.spectrum_data.get("y_theo"),
                subspectra=self.spectrum_data.get("subspectra"),
                metadata=self.spectrum_data.get("job_info"),
                fmt=fmt,
            )
            messagebox.showinfo(
                "Sucesso", f"Espectro exportado com sucesso para:\n{out_p}"
            )
            self._log(f"[OK WCONVERT] Arquivo exportado: {out_p}")
        except Exception as e:
            messagebox.showerror(
                "Erro de Exportação", f"Falha ao exportar arquivo:\n{e}"
            )

    def run_simulation_dialog(self):
        """Gera simulação sintética do espectro teórico a partir do .JOB."""
        if not self.spectrum_data or not self.spectrum_data.get("job_path"):
            messagebox.showinfo(
                "Aviso", "É necessário ter um arquivo .JOB associado para simulação."
            )
            return

        job_p = self.spectrum_data["job_path"]
        default_name = f"{job_p.stem}_simulated.lst"

        out_path = filedialog.asksaveasfilename(
            parent=self,
            title="Salvar Espectro Simulado (WSIMDATA)",
            initialfile=default_name,
            filetypes=[("Arquivo LST (*.lst)", "*.lst"), ("Todos os arquivos", "*.*")],
        )

        if not out_path:
            return

        try:
            job_info = self.spectrum_data["job_info"]
            vmax = job_info.get("vmax", 10.0)
            velocity = calculate_velocity_scale(512, vmax)
            model = MossbauerModel.from_job_info(job_info)
            y_theo, subspectra = model.compute_spectrum(velocity)

            noise = np.random.normal(0, np.sqrt(y_theo))
            sim_counts = np.clip(y_theo + noise, a_min=0, a_max=None)

            export_converted_data(
                Path(out_path),
                velocity,
                sim_counts,
                y_theo=y_theo,
                subspectra=subspectra,
                metadata=job_info,
                fmt="lst",
            )
            messagebox.showinfo("Sucesso", f"Espectro simulado salvo em:\n{out_path}")
            self._log(f"[OK WSIMDATA] Simulação salva em: {out_path}")
        except Exception as e:
            messagebox.showerror("Erro de Simulação", f"Falha ao gerar simulação:\n{e}")

    def validate_param_dialog(self):
        """Valida e corrige discrepâncias no bloco &PARAM."""
        if not self.spectrum_data or not self.spectrum_data.get("job_path"):
            messagebox.showinfo(
                "Aviso", "Nenhum arquivo .JOB carregado para validação."
            )
            return

        job_p = self.spectrum_data["job_path"]
        try:
            raw_content = self.spectrum_data["job_info"].get("raw_content", "")
            _, updated_path, warnings = validate_and_filter_param_block(
                job_p, raw_content
            )

            if warnings:
                msg = (
                    "Discrepâncias detectadas e corrigidas no bloco &PARAM:\n\n"
                    + "\n".join(f"• {w}" for w in warnings)
                )
                msg += f"\n\nArquivo atualizado salvo em:\n{updated_path.name}"
                messagebox.showwarning("Validação &PARAM", msg)
                self._log(f"[AVISO] Inconsistências corrigidas: {updated_path}")
                # Recarrega o arquivo atualizado
                self.load_file(str(updated_path))
            else:
                messagebox.showinfo(
                    "Validação &PARAM",
                    "Bloco &PARAM validado com sucesso!\nNenhuma discrepância encontrada.",
                )
                self._log(
                    "[OK] Bloco &PARAM validado. Nenhuma discrepância encontrada."
                )
        except Exception as e:
            messagebox.showerror("Erro de Validação", f"Falha ao validar &PARAM:\n{e}")

    def open_current_in_explorer(self):
        """Abre o arquivo atual no gerenciador de arquivos nativo do SO."""
        target = self.current_file_path or Path.cwd()
        open_in_system_file_manager(target)
        self._log(f"Abrindo pasta no gerenciador de arquivos: {target}")


def main(initial_file: Optional[str] = None):
    """Ponto de entrada da interface gráfica MossView."""
    target = None
    if initial_file:
        target = initial_file
    elif len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        target = sys.argv[1]

    app = MossViewGUI(initial_file=target)
    app.mainloop()


if __name__ == "__main__":
    main()
