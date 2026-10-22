#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MossView CLI - Interface de Linha de Comando para Análise, Simulação e Visualização Mössbauer.
Compatível com NORMOS DOS (MBPLOT, READMCS, WCONVERT, WDIST, WSITE, WSIMDATA, P).
"""

import sys
import os
import argparse
from pathlib import Path

# Suporte a execução direta do script (ex: python src/mossview/cli.py)
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from mossview.lib import (
        resolve_file_path,
        locate_associated_files,
        parse_job_file,
        validate_and_filter_param_block,
        run_readmcs_cli,
        run_convert_cli,
        run_sim_cli,
        run_info_cli,
        run_plot_flow,
    )
else:
    from .lib import (
        resolve_file_path,
        locate_associated_files,
        parse_job_file,
        validate_and_filter_param_block,
        run_readmcs_cli,
        run_convert_cli,
        run_sim_cli,
        run_info_cli,
        run_plot_flow,
    )


def run_interactive_cli(target_file: str = None):
    """
    Substituto interpretado em Python do utilitário interativo P.EXE e menu do MBPLOT.
    Permite operar o MossView através de um menu interativo de opções no terminal.
    """
    print("\n" + "=" * 70)
    print(" MossView Console Interativo (Compatível com P.EXE e MBPLOT.EXE)")
    print("=" * 70)

    current_file = target_file
    while True:
        print(f"\nArquivo Atual: {current_file if current_file else 'Nenhum'}")
        print("  [1] Selecionar/Alterar arquivo (.JOB ou .MOS)")
        print("  [2] Visualizar Espectro na Tela (MBPLOT)")
        print("  [3] Inspecionar Metadados do Detector (READMCS)")
        print("  [4] Resumo Físico dos Parâmetros de Ajuste (WSITE/WDIST)")
        print("  [5] Converter e Exportar para Colunas .LST / .CSV (WCONVERT)")
        print("  [6] Simular Espectro Teórico (WSIMDATA)")
        print("  [7] Validar e Corrigir Bloco &PARAM")
        print("  [8] Abrir Interface Gráfica (GUI)")
        print("  [Q] Sair")

        choice = input("\nEscolha uma opção: ").strip().upper()

        if choice == 'Q':
            print("Encerrando console interativo. Até logo!")
            break

        if choice == '1':
            new_f = input("Digite o caminho do arquivo (.job ou .mos): ").strip()
            if new_f:
                current_file = new_f

        elif choice == '2':
            if not current_file:
                print("[!] Selecione um arquivo primeiro (opção 1).")
                continue
            run_plot_flow(current_file, show_gui=True)

        elif choice == '3':
            if not current_file:
                print("[!] Selecione um arquivo primeiro (opção 1).")
                continue
            res = resolve_file_path(current_file)
            mos_p, _, _ = locate_associated_files(res)
            if mos_p and mos_p.exists():
                run_readmcs_cli(mos_p)
            else:
                print("[ERRO] Arquivo de dados .MOS não encontrado.")

        elif choice == '4':
            if not current_file:
                print("[!] Selecione um arquivo primeiro (opção 1).")
                continue
            res = resolve_file_path(current_file)
            _, job_p, _ = locate_associated_files(res)
            if job_p and job_p.exists():
                run_info_cli(job_p)
            else:
                print("[ERRO] Arquivo .JOB associado não encontrado.")

        elif choice == '5':
            if not current_file:
                print("[!] Selecione um arquivo primeiro (opção 1).")
                continue
            fmt = input("Formato de saída (lst/csv/dat) [padrão: lst]: ").strip() or 'lst'
            run_convert_cli(Path(current_file), fmt=fmt)

        elif choice == '6':
            if not current_file:
                print("[!] Selecione um arquivo primeiro (opção 1).")
                continue
            res = resolve_file_path(current_file)
            _, job_p, _ = locate_associated_files(res)
            if job_p and job_p.exists():
                run_sim_cli(job_p)
            else:
                print("[ERRO] Arquivo .JOB associado não encontrado para simulação.")

        elif choice == '7':
            if not current_file:
                print("[!] Selecione um arquivo primeiro (opção 1).")
                continue
            res = resolve_file_path(current_file)
            _, job_p, job_info = locate_associated_files(res)
            if job_p and job_p.exists():
                raw_content = job_info.get('raw_content', '')
                _, updated_path, warnings = validate_and_filter_param_block(job_p, raw_content)
                if warnings:
                    print("\n[AVISO] Inconsistências corrigidas no &PARAM:")
                    for w in warnings:
                        print(f"  -> {w}")
                    print(f"[OK] Arquivo atualizado salvo em: {updated_path}\n")
                else:
                    print("[OK] Bloco &PARAM validado. Nenhuma inconsistência encontrada.")
            else:
                print("[ERRO] Arquivo .JOB não encontrado para validação.")

        elif choice == '8':
            try:
                if __package__ is None or __package__ == "":
                    from mossview.gui import main as gui_main
                else:
                    from .gui import main as gui_main
                gui_main(current_file)
            except Exception as e:
                print(f"[ERRO] Não foi possível iniciar a interface gráfica: {e}")


def main():
    """
    Ponto de entrada do CLI MossView.
    Mantém 100% de compatibilidade com chamadas anteriores:
        mossview arquivo.job
        mossview arquivo.mos
    E disponibiliza os novos subcomandos inspirados no NORMOS DOS:
        mossview plot [ARQUIVO] [--save] [--no-gui] [--fold]
        mossview readmcs [ARQUIVO]
        mossview convert [ARQUIVO] [--output OUT] [--format lst|csv|dat]
        mossview sim [JOB] [--output OUT]
        mossview info [JOB]
        mossview validate [JOB]
        mossview interactive [ARQUIVO]
        mossview gui [ARQUIVO]
    """
    # Verificação de compatibilidade retroativa: se o primeiro argumento for um arquivo existente
    # ou não for um dos subcomandos reservados, trata diretamente como arquivo de espectro.
    subcommands = {'plot', 'readmcs', 'convert', 'sim', 'info', 'validate', 'interactive', 'gui', '-i', '--interactive'}

    if len(sys.argv) > 1 and sys.argv[1] not in subcommands and not sys.argv[1].startswith('-'):
        # Execução padrão retrocompatível: mossview <caminho_arquivo>
        target_file = sys.argv[1]
        run_plot_flow(target_file, show_gui=True)
        return

    parser = argparse.ArgumentParser(
        prog="mossview",
        description="MossView - Sistema Moderno em Python para Análise, Simulação e Plotagem Mössbauer (Substituto do NORMOS DOS)"
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Comandos disponíveis")

    # Subcomando: plot
    p_plot = subparsers.add_parser("plot", help="Renderiza o espectro Mössbauer (MBPLOT)")
    p_plot.add_argument("file", help="Arquivo .JOB ou .MOS")
    p_plot.add_argument("--save", "-s", action="store_true", help="Salva a imagem em disco")
    p_plot.add_argument("--output", "-o", type=str, default=None, help="Caminho do arquivo de imagem de saída")
    p_plot.add_argument("--no-gui", action="store_true", help="Não abre a janela interativa do Matplotlib")
    p_plot.add_argument("--fold", action="store_true", help="Aplica dobragem simétrica (folding) do espectro")
    p_plot.add_argument("--dpi", type=int, default=150, help="Resolução DPI da imagem (padrão: 150)")

    # Subcomando: readmcs
    p_mcs = subparsers.add_parser("readmcs", help="Inspeciona arquivos MCS/MOS e exibe metadados de aquisição (READMCS)")
    p_mcs.add_argument("file", help="Arquivo .MOS ou .MCS")

    # Subcomando: convert
    p_conv = subparsers.add_parser("convert", help="Converte espectro para formato de colunas LST/CSV/DAT (WCONVERT)")
    p_conv.add_argument("file", help="Arquivo .JOB ou .MOS")
    p_conv.add_argument("--output", "-o", type=str, default=None, help="Arquivo de saída")
    p_conv.add_argument("--format", "-f", choices=['lst', 'csv', 'dat', 'plt'], default='lst', help="Formato de exportação")
    p_conv.add_argument("--fold", action="store_true", help="Aplica dobragem (folding) antes da conversão")

    # Subcomando: sim
    p_sim = subparsers.add_parser("sim", help="Simula espectro Mössbauer a partir dos parâmetros de &PARAM (WSIMDATA)")
    p_sim.add_argument("job", help="Arquivo .JOB de entrada")
    p_sim.add_argument("--output", "-o", type=str, default=None, help="Arquivo .LST de saída")
    p_sim.add_argument("--channels", "-c", type=int, default=512, help="Número de canais da simulação (padrão: 512)")

    # Subcomando: info
    p_info = subparsers.add_parser("info", help="Exibe resumo dos parâmetros físicos de ajuste (WSITE/WDIST)")
    p_info.add_argument("job", help="Arquivo .JOB de entrada")

    # Subcomando: validate
    p_val = subparsers.add_parser("validate", help="Valida e corrige discrepâncias no bloco &PARAM")
    p_val.add_argument("job", help="Arquivo .JOB de entrada")

    # Subcomando: interactive
    p_inter = subparsers.add_parser("interactive", help="Console interativo em terminal (P.EXE)")
    p_inter.add_argument("file", nargs="?", default=None, help="Arquivo inicial opcional")

    # Subcomando: gui
    p_gui = subparsers.add_parser("gui", help="Inicia a interface gráfica de usuário (MossView GUI)")
    p_gui.add_argument("file", nargs="?", default=None, help="Arquivo inicial opcional para abrir na GUI")

    # Se nenhum argumento for passado, abre o modo interativo
    if len(sys.argv) == 1:
        run_interactive_cli()
        return

    args = parser.parse_args()

    if args.subcommand == "plot":
        out_p = Path(args.output) if args.output else None
        run_plot_flow(args.file, output_image_path=out_p, show_gui=not args.no_gui, fold=args.fold, dpi=args.dpi)

    elif args.subcommand == "readmcs":
        target = resolve_file_path(args.file)
        run_readmcs_cli(target)

    elif args.subcommand == "convert":
        out_p = Path(args.output) if args.output else None
        run_convert_cli(Path(args.file), output_path=out_p, fold=args.fold, fmt=args.format)

    elif args.subcommand == "sim":
        out_p = Path(args.output) if args.output else None
        run_sim_cli(Path(args.job), output_path=out_p, channels=args.channels)

    elif args.subcommand == "info":
        run_info_cli(Path(args.job))

    elif args.subcommand == "validate":
        resolved = resolve_file_path(args.job)
        job_info = parse_job_file(resolved)
        raw_content = job_info.get('raw_content', '')
        _, updated_path, warnings = validate_and_filter_param_block(resolved, raw_content)
        if warnings:
            print("\n[AVISO] Inconsistências corrigidas no &PARAM:")
            for w in warnings:
                print(f"  -> {w}")
            print(f"[OK] Arquivo atualizado salvo em: {updated_path}\n")
        else:
            print("[OK] Bloco &PARAM validado com sucesso. Nenhuma discrepância encontrada.")

    elif args.subcommand == "gui":
        try:
            if __package__ is None or __package__ == "":
                from mossview.gui import main as gui_main
            else:
                from .gui import main as gui_main
            gui_main(args.file)
        except Exception as e:
            print(f"[ERRO] Falha ao iniciar a interface gráfica: {e}")

    elif args.subcommand in ("interactive", None):
        target = args.file if hasattr(args, 'file') else None
        run_interactive_cli(target)


if __name__ == "__main__":
    main()
